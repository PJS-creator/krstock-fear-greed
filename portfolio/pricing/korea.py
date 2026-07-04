from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .base import PriceProviderError, ProviderQuote

KOREA_SYMBOL_PATTERN = re.compile(r"^\d{6}$")
KOREA_PROVIDER_NAME = "finance_datareader"


def normalize_korea_symbol(symbol: object) -> str:
    text = str(symbol or "").strip().upper()
    if text.startswith("KR:"):
        text = text[3:]
    for suffix in (".KS", ".KQ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    if not KOREA_SYMBOL_PATTERN.fullmatch(text):
        raise ValueError("한국 종목코드는 6자리 숫자여야 합니다. 예: 005930")
    return text


def _as_non_negative_float(value: object, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PriceProviderError(f"FinanceDataReader {field_name} 값이 숫자가 아닙니다.") from exc
    if not math.isfinite(number):
        raise PriceProviderError(f"FinanceDataReader {field_name} 값이 유효하지 않습니다.")
    if number < 0:
        raise PriceProviderError(f"FinanceDataReader {field_name} 값이 음수입니다.")
    return number


def _index_date(value: object):
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            return value.date()
        if hasattr(value, "date"):
            return value.date()
    except Exception:
        return None
    return None


def _index_timestamp(value: object) -> datetime | None:
    try:
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
    except Exception:
        return None
    return None


def parse_finance_data_reader_price_frame(symbol: object, frame: Any) -> ProviderQuote:
    normalized_symbol = normalize_korea_symbol(symbol)
    if frame is None or not hasattr(frame, "columns"):
        raise PriceProviderError("FinanceDataReader 응답 형식이 올바르지 않습니다.")
    if "Close" not in frame.columns:
        raise PriceProviderError("FinanceDataReader 응답에 Close 컬럼이 없습니다.")

    close_series = frame["Close"].dropna()
    if close_series.empty:
        raise PriceProviderError("FinanceDataReader 응답에 최근 종가 데이터가 없습니다.")
    try:
        close_series = close_series.sort_index()
    except Exception:
        pass

    latest_close = _as_non_negative_float(close_series.iloc[-1], "Close")
    latest_index = close_series.index[-1] if hasattr(close_series, "index") and len(close_series.index) else None
    # FinanceDataReader가 최신 행 하나만 반환하면 전일 종가를 확정할 수 없다.
    # 이 경우 일간 변동을 0으로 표시하도록 previous_close=current_price 정책을 사용한다.
    previous_close = latest_close
    if len(close_series) >= 2:
        previous_close = _as_non_negative_float(close_series.iloc[-2], "previous Close")

    return ProviderQuote.now(
        symbol=normalized_symbol,
        price=latest_close,
        previous_close=previous_close,
        provider=KOREA_PROVIDER_NAME,
        price_date=_index_date(latest_index),
        as_of_timestamp=_index_timestamp(latest_index),
    )


class FinanceDataReaderKoreaQuoteProvider:
    def __init__(
        self,
        *,
        data_reader: Callable[..., Any] | None = None,
        listing_loader: Callable[[str], Any] | None = None,
        today_fn: Callable[[], date] = date.today,
        lookback_days: int = 14,
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        self._data_reader = data_reader
        self._listing_loader = listing_loader
        self._today_fn = today_fn
        self._lookback_days = lookback_days
        self._name_cache: dict[str, str] = {}

    def _load_finance_datareader(self):
        try:
            import FinanceDataReader as fdr
        except ImportError as exc:
            raise PriceProviderError("FinanceDataReader 패키지가 설치되어 있지 않습니다.") from exc
        if self._data_reader is None:
            self._data_reader = fdr.DataReader
        if self._listing_loader is None:
            self._listing_loader = fdr.StockListing

    def _get_data_reader(self) -> Callable[..., Any]:
        if self._data_reader is None:
            self._load_finance_datareader()
        if self._data_reader is None:
            raise PriceProviderError("FinanceDataReader DataReader를 사용할 수 없습니다.")
        return self._data_reader

    def _get_listing_loader(self) -> Callable[[str], Any]:
        if self._listing_loader is None:
            self._load_finance_datareader()
        if self._listing_loader is None:
            raise PriceProviderError("FinanceDataReader StockListing을 사용할 수 없습니다.")
        return self._listing_loader

    def get_quote(self, symbol: str) -> ProviderQuote:
        try:
            normalized_symbol = normalize_korea_symbol(symbol)
        except ValueError as exc:
            raise PriceProviderError(str(exc)) from exc
        start = (self._today_fn() - timedelta(days=self._lookback_days)).isoformat()
        try:
            frame = self._get_data_reader()(normalized_symbol, start)
        except Exception as exc:
            raise PriceProviderError(f"국내 주식 최근 제공 가격 조회 실패: {normalized_symbol}") from exc
        return parse_finance_data_reader_price_frame(normalized_symbol, frame)

    def get_display_name(self, symbol: str) -> str:
        try:
            normalized_symbol = normalize_korea_symbol(symbol)
        except ValueError:
            return str(symbol or "").strip().upper()
        if normalized_symbol in self._name_cache:
            return self._name_cache[normalized_symbol]
        display_name = normalized_symbol
        try:
            listing = self._get_listing_loader()("KRX")
            code_column = "Code" if "Code" in listing.columns else "Symbol"
            if code_column in listing.columns and "Name" in listing.columns:
                codes = listing[code_column].astype(str).str.zfill(6)
                matches = listing[codes == normalized_symbol]
                if not matches.empty:
                    candidate = str(matches.iloc[0]["Name"]).strip()
                    if candidate:
                        display_name = candidate
        except Exception:
            display_name = normalized_symbol
        self._name_cache[normalized_symbol] = display_name
        return display_name


def build_korea_quote_provider() -> FinanceDataReaderKoreaQuoteProvider:
    return FinanceDataReaderKoreaQuoteProvider()
