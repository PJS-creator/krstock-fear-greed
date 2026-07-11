from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Any

from .base import PriceProviderError, ProviderQuote
from .korea import normalize_korea_symbol

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ in supported runtimes
    ZoneInfo = None  # type: ignore[assignment]


KIS_PROVIDER_NAME = "korea_investment"
KIS_REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
KIS_VIRTUAL_BASE_URL = "https://openapivts.koreainvestment.com:29443"
KIS_DOMESTIC_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
KIS_OVERSEAS_PRICE_PATH = "/uapi/overseas-price/v1/quotations/price"
KIS_DOMESTIC_FUTURES_TIME_CHART_PATH = "/uapi/domestic-futureoption/v1/quotations/inquire-time-futurechartprice"
KIS_TOKEN_PATH = "/oauth2/tokenP"
KIS_DOMESTIC_TR_ID = "FHKST01010100"
KIS_OVERSEAS_TR_ID = "HHDFS00000300"
KIS_DOMESTIC_FUTURES_TIME_CHART_TR_ID = "FHKIF03020200"
KIS_DEFAULT_US_EXCHANGES = ("NAS", "NYS", "AMS")
KIS_TOKEN_REFRESH_MARGIN_SECONDS = 60
US_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")

ResponseLoader = Callable[[str, str, Mapping[str, str], bytes | None, float], Mapping[str, Any]]


def normalize_kis_us_symbol(symbol: object) -> str:
    text = str(symbol or "").strip().upper()
    if not US_SYMBOL_PATTERN.fullmatch(text):
        raise ValueError("미국 주식 티커 형식이 올바르지 않습니다.")
    return text


def _kis_kst():
    if ZoneInfo is not None:
        try:
            return ZoneInfo("Asia/Seoul")
        except Exception:
            pass
    return timezone(timedelta(hours=9))


def _as_positive_float(value: object, field_name: str) -> float:
    text = str(value or "").strip().replace(",", "")
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise PriceProviderError(f"KIS {field_name} 값이 숫자가 아닙니다.") from exc
    if not math.isfinite(number) or number <= 0:
        raise PriceProviderError(f"KIS {field_name} 값이 유효하지 않습니다.")
    return number


def _parse_yyyymmdd(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _parse_kst_timestamp(date_value: object, time_value: object) -> datetime | None:
    parsed_date = _parse_yyyymmdd(date_value)
    if parsed_date is None:
        return None
    text = "".join(char for char in str(time_value or "").strip() if char.isdigit())
    if len(text) < 6:
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=_kis_kst()).astimezone(timezone.utc)
    text = text[:6]
    try:
        local_time = datetime(
            parsed_date.year,
            parsed_date.month,
            parsed_date.day,
            int(text[:2]),
            int(text[2:4]),
            int(text[4:6]),
            tzinfo=_kis_kst(),
        )
    except ValueError:
        return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=_kis_kst()).astimezone(timezone.utc)
    return local_time.astimezone(timezone.utc)


def _first_present(output: Mapping[str, Any], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = output.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_output(payload: Mapping[str, Any], context: str) -> Mapping[str, Any]:
    rt_cd = payload.get("rt_cd")
    if rt_cd not in (None, "0", 0):
        message = str(payload.get("msg1") or payload.get("msg_cd") or "알 수 없는 KIS 오류")
        raise PriceProviderError(f"KIS {context} 응답 오류: {message}")
    output = payload.get("output")
    if not isinstance(output, Mapping):
        raise PriceProviderError(f"KIS {context} 응답에 output이 없습니다.")
    return output


def _extract_output_rows(payload: Mapping[str, Any], context: str) -> list[Mapping[str, Any]]:
    rt_cd = payload.get("rt_cd")
    if rt_cd not in (None, "0", 0):
        message = str(payload.get("msg1") or payload.get("msg_cd") or "알 수 없는 KIS 오류")
        raise PriceProviderError(f"KIS {context} 응답 오류: {message}")
    rows = payload.get("output2")
    if rows is None:
        rows = payload.get("output")
    if isinstance(rows, Mapping):
        rows = [rows]
    if not isinstance(rows, list):
        raise PriceProviderError(f"KIS {context} 응답에 분봉 데이터가 없습니다.")
    normalized_rows = [row for row in rows if isinstance(row, Mapping)]
    if not normalized_rows:
        raise PriceProviderError(f"KIS {context} 응답에 유효한 분봉 데이터가 없습니다.")
    return normalized_rows


def parse_kis_domestic_futures_intraday_response(payload: Mapping[str, Any]) -> list[tuple[datetime | None, float]]:
    rows = _extract_output_rows(payload, "국내 선물 60분봉")
    points: list[tuple[datetime | None, float]] = []
    for row in rows:
        price_value = _first_present(
            row,
            (
                "futs_prpr",
                "stck_prpr",
                "stck_clpr",
                "futs_clpr",
                "close",
                "clos",
                "prpr",
            ),
        )
        try:
            close = _as_positive_float(price_value, "futures_close")
        except PriceProviderError:
            continue
        timestamp = _parse_kst_timestamp(
            _first_present(row, ("stck_bsop_date", "bsop_date", "trd_dd", "xymd", "date")),
            _first_present(row, ("stck_cntg_hour", "cntg_hour", "trd_tm", "xhms", "time")),
        )
        points.append((timestamp, close))
    if not points:
        raise PriceProviderError("KIS 국내 선물 60분봉 응답에 유효한 종가가 없습니다.")
    points.sort(key=lambda point: point[0] or datetime.min.replace(tzinfo=timezone.utc))
    return points


def parse_kis_domestic_quote_response(symbol: object, payload: Mapping[str, Any]) -> ProviderQuote:
    normalized_symbol = normalize_korea_symbol(symbol)
    output = _extract_output(payload, "국내 주식 현재가")
    price = _as_positive_float(output.get("stck_prpr"), "stck_prpr")
    previous_value = _first_present(
        output,
        (
            "stck_sdpr",
            "prdy_clpr",
            "stck_prdy_clpr",
            "base",
        ),
    )
    previous_close = _as_positive_float(previous_value if previous_value is not None else price, "previous_close")
    price_date = _parse_yyyymmdd(_first_present(output, ("stck_bsop_date", "bsop_date", "trd_dd")))
    as_of_timestamp = _parse_kst_timestamp(
        _first_present(output, ("stck_bsop_date", "bsop_date", "trd_dd")),
        _first_present(output, ("stck_cntg_hour", "cntg_hour", "trd_tm")),
    )
    return ProviderQuote.now(
        symbol=normalized_symbol,
        price=price,
        previous_close=previous_close,
        provider=KIS_PROVIDER_NAME,
        price_date=price_date,
        as_of_timestamp=as_of_timestamp,
    )


def parse_kis_overseas_quote_response(symbol: object, payload: Mapping[str, Any]) -> ProviderQuote:
    normalized_symbol = normalize_kis_us_symbol(symbol)
    output = _extract_output(payload, "해외 주식 현재가")
    price_value = _first_present(output, ("last", "ovrs_nmix_prpr", "stck_prpr", "price", "close", "last_price"))
    price = _as_positive_float(price_value, "last")
    previous_value = _first_present(
        output,
        (
            "base",
            "prdy_clpr",
            "ovrs_nmix_prdy_clpr",
            "stck_sdpr",
            "prev",
            "prev_close",
        ),
    )
    previous_close = _as_positive_float(previous_value if previous_value is not None else price, "previous_close")
    date_value = _first_present(output, ("xymd", "stck_bsop_date", "trdt", "date"))
    time_value = _first_present(output, ("xhms", "stck_cntg_hour", "trtm", "time"))
    price_date = _parse_yyyymmdd(date_value)
    as_of_timestamp = _parse_kst_timestamp(date_value, time_value)
    return ProviderQuote.now(
        symbol=normalized_symbol,
        price=price,
        previous_close=previous_close,
        provider=KIS_PROVIDER_NAME,
        price_date=price_date,
        as_of_timestamp=as_of_timestamp,
    )


def _default_response_loader(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise PriceProviderError(f"KIS API 요청 실패: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise PriceProviderError("KIS API 응답 형식이 올바르지 않습니다.")
    return payload


def parse_kis_token_response(payload: Mapping[str, Any], *, now: datetime | None = None) -> tuple[str, datetime]:
    token = str(payload.get("access_token") or "").strip()
    if not token:
        message = str(payload.get("error_description") or payload.get("msg1") or "access_token 없음")
        raise PriceProviderError(f"KIS 토큰 발급 실패: {message}")

    now = now or datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=23)
    expires_text = str(payload.get("access_token_token_expired") or "").strip()
    if expires_text:
        try:
            expires_at = datetime.strptime(expires_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_kis_kst()).astimezone(timezone.utc)
        except ValueError:
            pass
    else:
        try:
            expires_in = int(payload.get("expires_in") or 0)
        except (TypeError, ValueError):
            expires_in = 0
        if expires_in > 0:
            expires_at = now + timedelta(seconds=expires_in)
    return token, expires_at


class KoreaInvestmentQuoteProvider:
    provider_name = KIS_PROVIDER_NAME

    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        env: str = "real",
        response_loader: ResponseLoader | None = None,
        timeout_seconds: float = 5.0,
        us_exchanges: tuple[str, ...] = KIS_DEFAULT_US_EXCHANGES,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._app_key = str(app_key or "").strip()
        self._app_secret = str(app_secret or "").strip()
        if not self._app_key or not self._app_secret:
            raise ValueError("KIS app_key and app_secret are required")
        self._env = str(env or "real").strip().lower()
        self._base_url = KIS_VIRTUAL_BASE_URL if self._env in {"virtual", "paper", "vts", "mock"} else KIS_REAL_BASE_URL
        self._response_loader = response_loader or _default_response_loader
        self._timeout_seconds = timeout_seconds
        self._us_exchanges = tuple(exchange.strip().upper() for exchange in us_exchanges if exchange.strip())
        if not self._us_exchanges:
            self._us_exchanges = KIS_DEFAULT_US_EXCHANGES
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._access_token: str | None = None
        self._access_token_expires_at: datetime | None = None
        self._token_lock = Lock()
        self._resolved_exchange_by_symbol: dict[str, str] = {}

    def _url(self, path: str, query: Mapping[str, str] | None = None) -> str:
        url = f"{self._base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        return url

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: Mapping[str, object] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        encoded_body = None
        request_headers = dict(headers or {})
        if body is not None:
            encoded_body = json.dumps(dict(body)).encode("utf-8")
            request_headers.setdefault("content-type", "application/json; charset=utf-8")
        return self._response_loader(method, self._url(path, query), request_headers, encoded_body, self._timeout_seconds)

    def _get_access_token(self) -> str:
        now = self._now_fn()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if (
            self._access_token
            and self._access_token_expires_at is not None
            and self._access_token_expires_at > now + timedelta(seconds=KIS_TOKEN_REFRESH_MARGIN_SECONDS)
        ):
            return self._access_token
        with self._token_lock:
            now = self._now_fn()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if (
                self._access_token
                and self._access_token_expires_at is not None
                and self._access_token_expires_at > now + timedelta(seconds=KIS_TOKEN_REFRESH_MARGIN_SECONDS)
            ):
                return self._access_token
            payload = self._request_json(
                "POST",
                KIS_TOKEN_PATH,
                body={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                },
            )
            token, expires_at = parse_kis_token_response(payload, now=now)
            self._access_token = token
            self._access_token_expires_at = expires_at
            return token

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self._get_access_token()}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def get_quote(self, symbol: str) -> ProviderQuote:
        text = str(symbol or "").strip()
        try:
            domestic_symbol = normalize_korea_symbol(text)
        except ValueError:
            return self._get_overseas_quote(text)
        return self._get_domestic_quote(domestic_symbol)

    def _get_domestic_quote(self, symbol: str) -> ProviderQuote:
        payload = self._request_json(
            "GET",
            KIS_DOMESTIC_PRICE_PATH,
            headers=self._headers(KIS_DOMESTIC_TR_ID),
            query={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
            },
        )
        return parse_kis_domestic_quote_response(symbol, payload)

    def _get_overseas_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = normalize_kis_us_symbol(symbol)
        errors: list[str] = []
        resolved_exchange = self._resolved_exchange_by_symbol.get(normalized_symbol)
        exchanges = tuple(
            dict.fromkeys(
                ([resolved_exchange] if resolved_exchange else []) + list(self._us_exchanges)
            )
        )
        for exchange in exchanges:
            try:
                payload = self._request_json(
                    "GET",
                    KIS_OVERSEAS_PRICE_PATH,
                    headers=self._headers(KIS_OVERSEAS_TR_ID),
                    query={
                        "AUTH": "",
                        "EXCD": exchange,
                        "SYMB": normalized_symbol,
                    },
                )
                quote = parse_kis_overseas_quote_response(normalized_symbol, payload)
                self._resolved_exchange_by_symbol[normalized_symbol] = exchange
                return quote
            except PriceProviderError as exc:
                errors.append(f"{exchange}: {exc}")
        raise PriceProviderError("; ".join(errors) or f"KIS 해외 주식 현재가 조회 실패: {normalized_symbol}")

    def get_domestic_futures_intraday_closes(
        self,
        symbol: str,
        *,
        market_div_code: str = "F",
    ) -> list[tuple[datetime | None, float]]:
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            raise PriceProviderError("KIS 국내 선물 종목코드가 설정되지 않았습니다.")
        payload = self._request_json(
            "GET",
            KIS_DOMESTIC_FUTURES_TIME_CHART_PATH,
            headers=self._headers(KIS_DOMESTIC_FUTURES_TIME_CHART_TR_ID),
            query={
                "FID_COND_MRKT_DIV_CODE": str(market_div_code or "F").strip().upper() or "F",
                "FID_INPUT_ISCD": normalized_symbol,
                "FID_HOUR_CLS_CODE": "1",
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )
        return parse_kis_domestic_futures_intraday_response(payload)


def build_kis_quote_provider(
    app_key: str | None,
    app_secret: str | None,
    *,
    env: str = "real",
    timeout_seconds: float = 5.0,
) -> KoreaInvestmentQuoteProvider | None:
    app_key = str(app_key or "").strip()
    app_secret = str(app_secret or "").strip()
    if not app_key or not app_secret:
        return None
    return KoreaInvestmentQuoteProvider(
        app_key=app_key,
        app_secret=app_secret,
        env=env,
        timeout_seconds=timeout_seconds,
    )
