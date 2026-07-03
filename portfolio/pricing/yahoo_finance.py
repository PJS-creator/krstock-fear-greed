from __future__ import annotations

import math
import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import PriceProviderError, ProviderFxRate, ProviderIntradayPrices, ProviderQuote
from .korea import normalize_korea_symbol

YFINANCE_PROVIDER_NAME = "yfinance"
YFINANCE_USD_KRW_SYMBOL = "KRW=X"
YAHOO_CHART_FX_PROVIDER_NAME = "yahoo-chart"
YAHOO_CHART_FX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?range=5d&interval=1d"
OPEN_ER_API_FX_PROVIDER_NAME = "open-er-api"
OPEN_ER_API_FX_URL = "https://open.er-api.com/v6/latest/USD"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; krstock-fear-greed/1.0; +https://github.com/PJS-creator/krstock-fear-greed)",
    "Accept": "application/json",
}


def normalize_yfinance_symbol(symbol: object) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        raise ValueError("미국 주식 ticker가 비어 있습니다.")
    return text


def _as_non_negative_float(value: object, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PriceProviderError(f"yfinance {field_name} 값이 숫자가 아닙니다.") from exc
    if not math.isfinite(number):
        raise PriceProviderError(f"yfinance {field_name} 값이 유효하지 않습니다.")
    if number < 0:
        raise PriceProviderError(f"yfinance {field_name} 값이 음수입니다.")
    return number


def _select_close_series(frame: Any):
    if frame is None or not hasattr(frame, "columns"):
        raise PriceProviderError("yfinance 응답 형식이 올바르지 않습니다.")

    columns = frame.columns
    if getattr(columns, "nlevels", 1) > 1:
        for level in range(columns.nlevels):
            if "Close" not in set(columns.get_level_values(level)):
                continue
            close_frame = frame.xs("Close", axis=1, level=level)
            if hasattr(close_frame, "columns"):
                if len(close_frame.columns) == 0:
                    break
                return close_frame.iloc[:, 0]
            return close_frame
        raise PriceProviderError("yfinance 응답에 Close 컬럼이 없습니다.")

    if "Close" not in columns:
        raise PriceProviderError("yfinance 응답에 Close 컬럼이 없습니다.")
    return frame["Close"]


def parse_yfinance_history_frame(symbol: object, frame: Any) -> ProviderQuote:
    normalized_symbol = normalize_yfinance_symbol(symbol)
    close_series = _select_close_series(frame).dropna()
    if close_series.empty:
        raise PriceProviderError("yfinance 응답에 최근 종가 데이터가 없습니다.")
    try:
        close_series = close_series.sort_index()
    except Exception:
        pass

    latest_close = _as_non_negative_float(close_series.iloc[-1], "Close")
    previous_close = latest_close
    if len(close_series) >= 2:
        previous_close = _as_non_negative_float(close_series.iloc[-2], "previous Close")

    return ProviderQuote.now(
        symbol=normalized_symbol,
        price=latest_close,
        previous_close=previous_close,
        provider=YFINANCE_PROVIDER_NAME,
    )


def _downsample_prices(values: list[float], *, max_points: int) -> tuple[float, ...]:
    if max_points <= 0:
        raise ValueError("max_points must be positive")
    if len(values) <= max_points:
        return tuple(values)
    last_index = len(values) - 1
    selected = []
    for index in range(max_points):
        source_index = round(index * last_index / (max_points - 1))
        selected.append(values[source_index])
    return tuple(selected)


def parse_yfinance_intraday_frame(symbol: object, frame: Any, *, max_points: int = 64) -> tuple[float, ...]:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise PriceProviderError("yfinance 분봉 ticker가 비어 있습니다.")
    close_series = _select_close_series(frame).dropna()
    if close_series.empty:
        raise PriceProviderError("yfinance 응답에 당일 분봉 데이터가 없습니다.")
    try:
        close_series = close_series.sort_index()
    except Exception:
        pass
    prices = [_as_non_negative_float(value, "intraday Close") for value in close_series.tolist()]
    return _downsample_prices(prices, max_points=max_points)


class YFinanceQuoteProvider:
    def __init__(
        self,
        *,
        history_loader: Callable[..., Any] | None = None,
        period: str = "5d",
        interval: str = "1d",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._history_loader = history_loader
        self._period = period
        self._interval = interval
        self._timeout_seconds = timeout_seconds

    def _load_history(self, symbol: str):
        if self._history_loader is not None:
            return self._history_loader(
                symbol,
                period=self._period,
                interval=self._interval,
                timeout_seconds=self._timeout_seconds,
            )
        try:
            import yfinance as yf
        except ImportError as exc:
            raise PriceProviderError("yfinance 패키지가 설치되어 있지 않습니다.") from exc

        kwargs = {
            "period": self._period,
            "interval": self._interval,
            "auto_adjust": False,
            "progress": False,
            "threads": False,
            "timeout": self._timeout_seconds,
        }
        try:
            return yf.download(symbol, multi_level_index=False, **kwargs)
        except TypeError:
            return yf.download(symbol, **kwargs)

    def get_quote(self, symbol: str) -> ProviderQuote:
        try:
            normalized_symbol = normalize_yfinance_symbol(symbol)
        except ValueError as exc:
            raise PriceProviderError(str(exc)) from exc
        try:
            frame = self._load_history(normalized_symbol)
        except PriceProviderError:
            raise
        except Exception as exc:
            raise PriceProviderError(f"yfinance 최근 제공 가격 조회 실패: {normalized_symbol}") from exc
        return parse_yfinance_history_frame(normalized_symbol, frame)


def build_yfinance_provider() -> YFinanceQuoteProvider:
    return YFinanceQuoteProvider()


def _intraday_symbol_candidates(symbol: object, market: str | None) -> list[str]:
    market_text = str(market or "").strip().upper()
    if market_text in {"KR", "KRX", "KOSPI", "KOSDAQ"}:
        normalized = normalize_korea_symbol(symbol)
        return [f"{normalized}.KS", f"{normalized}.KQ"]
    return [normalize_yfinance_symbol(symbol)]


class YFinanceIntradayPriceProvider:
    def __init__(
        self,
        *,
        history_loader: Callable[..., Any] | None = None,
        period: str = "1d",
        interval: str = "1m",
        timeout_seconds: float = 10.0,
        max_points: int = 64,
    ) -> None:
        if max_points <= 1:
            raise ValueError("max_points must be greater than 1")
        self._history_loader = history_loader
        self._period = period
        self._interval = interval
        self._timeout_seconds = timeout_seconds
        self._max_points = max_points

    def _load_history(self, symbol: str):
        if self._history_loader is not None:
            return self._history_loader(
                symbol,
                period=self._period,
                interval=self._interval,
                timeout_seconds=self._timeout_seconds,
            )
        try:
            import yfinance as yf
        except ImportError as exc:
            raise PriceProviderError("yfinance 패키지가 설치되어 있지 않습니다.") from exc

        kwargs = {
            "period": self._period,
            "interval": self._interval,
            "auto_adjust": False,
            "progress": False,
            "threads": False,
            "timeout": self._timeout_seconds,
        }
        try:
            return yf.download(symbol, multi_level_index=False, **kwargs)
        except TypeError:
            return yf.download(symbol, **kwargs)

    def get_intraday_prices(self, symbol: str, *, market: str | None = None) -> ProviderIntradayPrices:
        try:
            candidates = _intraday_symbol_candidates(symbol, market)
        except ValueError as exc:
            raise PriceProviderError(str(exc)) from exc

        errors = []
        for candidate in candidates:
            try:
                frame = self._load_history(candidate)
                prices = parse_yfinance_intraday_frame(candidate, frame, max_points=self._max_points)
            except PriceProviderError as exc:
                errors.append(str(exc))
                continue
            except Exception as exc:
                errors.append(str(exc))
                continue
            return ProviderIntradayPrices.now(symbol=str(symbol).strip().upper(), prices=prices, provider=YFINANCE_PROVIDER_NAME)

        suffix = f": {'; '.join(errors)}" if errors else ""
        raise PriceProviderError(f"yfinance 당일 분봉 데이터 조회 실패{suffix}")


def build_yfinance_intraday_provider() -> YFinanceIntradayPriceProvider:
    return YFinanceIntradayPriceProvider()


class YFinanceFxProvider:
    def __init__(
        self,
        *,
        history_loader: Callable[..., Any] | None = None,
        period: str = "5d",
        interval: str = "1d",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._quote_provider = YFinanceQuoteProvider(
            history_loader=history_loader,
            period=period,
            interval=interval,
            timeout_seconds=timeout_seconds,
        )

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        normalized_from = str(from_currency or "").strip().upper()
        normalized_to = str(to_currency or "").strip().upper()
        if (normalized_from, normalized_to) != ("USD", "KRW"):
            raise PriceProviderError("yfinance FX provider는 USD/KRW만 지원합니다.")
        quote = self._quote_provider.get_quote(YFINANCE_USD_KRW_SYMBOL)
        if quote.price <= 0:
            raise PriceProviderError("yfinance USD/KRW 환율 값이 유효하지 않습니다.")
        return ProviderFxRate.now(
            from_currency=normalized_from,
            to_currency=normalized_to,
            rate=quote.price,
            provider=YFINANCE_PROVIDER_NAME,
        )


def build_yfinance_fx_provider() -> YFinanceFxProvider:
    return YFinanceFxProvider()


def parse_yahoo_chart_usd_krw_response(payload: Mapping[str, Any]) -> ProviderFxRate:
    try:
        chart = payload["chart"]
        error = chart.get("error")
        if error:
            raise PriceProviderError(f"Yahoo chart 응답 오류: {error}")
        result = chart["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PriceProviderError("Yahoo chart USD/KRW 응답 형식이 올바르지 않습니다.") from exc

    values = []
    for value in closes:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            values.append(number)
    if not values:
        raise PriceProviderError("Yahoo chart USD/KRW 응답에 유효한 환율 값이 없습니다.")
    return ProviderFxRate.now(from_currency="USD", to_currency="KRW", rate=values[-1], provider=YAHOO_CHART_FX_PROVIDER_NAME)


def parse_open_er_api_usd_krw_response(payload: Mapping[str, Any]) -> ProviderFxRate:
    try:
        result = str(payload.get("result", "")).lower()
        if result and result != "success":
            raise PriceProviderError(f"open.er-api 응답 오류: {payload.get('error-type') or result}")
        base_code = str(payload.get("base_code", "")).upper()
        if base_code != "USD":
            raise PriceProviderError("open.er-api USD 기준 응답이 아닙니다.")
        rate = float(payload["rates"]["KRW"])
    except PriceProviderError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise PriceProviderError("open.er-api USD/KRW 응답 형식이 올바르지 않습니다.") from exc
    if not math.isfinite(rate) or rate <= 0:
        raise PriceProviderError("open.er-api USD/KRW 환율 값이 유효하지 않습니다.")
    return ProviderFxRate.now(from_currency="USD", to_currency="KRW", rate=rate, provider=OPEN_ER_API_FX_PROVIDER_NAME)


class YahooChartFxProvider:
    def __init__(
        self,
        *,
        response_loader: Callable[[str, float], Mapping[str, Any]] | None = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        self._response_loader = response_loader
        self._timeout_seconds = timeout_seconds

    def _load_response(self) -> Mapping[str, Any]:
        if self._response_loader is not None:
            return self._response_loader(YAHOO_CHART_FX_URL, self._timeout_seconds)
        try:
            request = Request(YAHOO_CHART_FX_URL, headers=HTTP_HEADERS)
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PriceProviderError("Yahoo chart USD/KRW 환율 조회 실패") from exc

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        normalized_from = str(from_currency or "").strip().upper()
        normalized_to = str(to_currency or "").strip().upper()
        if (normalized_from, normalized_to) != ("USD", "KRW"):
            raise PriceProviderError("Yahoo chart FX provider는 USD/KRW만 지원합니다.")
        return parse_yahoo_chart_usd_krw_response(self._load_response())


def build_yahoo_chart_fx_provider() -> YahooChartFxProvider:
    return YahooChartFxProvider()


class OpenErApiFxProvider:
    def __init__(
        self,
        *,
        response_loader: Callable[[str, float], Mapping[str, Any]] | None = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        self._response_loader = response_loader
        self._timeout_seconds = timeout_seconds

    def _load_response(self) -> Mapping[str, Any]:
        if self._response_loader is not None:
            return self._response_loader(OPEN_ER_API_FX_URL, self._timeout_seconds)
        try:
            request = Request(OPEN_ER_API_FX_URL, headers=HTTP_HEADERS)
            with urlopen(request, timeout=self._timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PriceProviderError("open.er-api USD/KRW 환율 조회 실패") from exc

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        normalized_from = str(from_currency or "").strip().upper()
        normalized_to = str(to_currency or "").strip().upper()
        if (normalized_from, normalized_to) != ("USD", "KRW"):
            raise PriceProviderError("open.er-api FX provider는 USD/KRW만 지원합니다.")
        return parse_open_er_api_usd_krw_response(self._load_response())


class FallbackFxProvider:
    def __init__(self, providers: list[Any]) -> None:
        if not providers:
            raise ValueError("providers must not be empty")
        self._providers = providers

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        errors = []
        for provider in self._providers:
            try:
                return provider.get_exchange_rate(from_currency, to_currency)
            except PriceProviderError as exc:
                errors.append(str(exc))
        detail = "; ".join(errors) if errors else "사용 가능한 provider가 없습니다."
        raise PriceProviderError(f"USD/KRW 환율 조회 실패: {detail}")


def build_open_er_api_fx_provider() -> OpenErApiFxProvider:
    return OpenErApiFxProvider()


def build_public_fx_provider() -> FallbackFxProvider:
    return FallbackFxProvider([YahooChartFxProvider(), OpenErApiFxProvider()])
