from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from .base import PriceProviderError, ProviderFxRate, ProviderQuote

YFINANCE_PROVIDER_NAME = "yfinance"
YFINANCE_USD_KRW_SYMBOL = "KRW=X"


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
