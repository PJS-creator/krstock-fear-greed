from __future__ import annotations

from datetime import date
from typing import Protocol

from .models import HistoricalPriceProviderError


class HistoricalPriceProvider(Protocol):
    def get_close_prices(self, *, market: str, ticker: str, start_date: date, end_date: date) -> dict[date, float]:
        ...

    def get_usd_krw_rates(self, *, start_date: date, end_date: date) -> dict[date, float]:
        ...


class FinanceDataReaderHistoricalPriceProvider:
    def _data_reader(self):
        try:
            import FinanceDataReader as fdr
        except ImportError as exc:
            raise HistoricalPriceProviderError("FinanceDataReader is not installed") from exc
        return fdr.DataReader

    def get_close_prices(self, *, market: str, ticker: str, start_date: date, end_date: date) -> dict[date, float]:
        data_reader = self._data_reader()
        symbol = ticker if market == "KR" else ticker.upper()
        try:
            frame = data_reader(symbol, start_date.isoformat(), end_date.isoformat())
        except Exception as exc:
            raise HistoricalPriceProviderError(f"Failed to fetch historical prices for {market}/{ticker}") from exc
        if frame is None or frame.empty or "Close" not in frame.columns:
            raise HistoricalPriceProviderError(f"No Close price data for {market}/{ticker}")
        prices: dict[date, float] = {}
        for index, row in frame.iterrows():
            close = row.get("Close")
            if close is None:
                continue
            try:
                value = float(close)
            except (TypeError, ValueError):
                continue
            prices[index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])] = value
        return prices

    def get_usd_krw_rates(self, *, start_date: date, end_date: date) -> dict[date, float]:
        data_reader = self._data_reader()
        try:
            frame = data_reader("USD/KRW", start_date.isoformat(), end_date.isoformat())
        except Exception as exc:
            raise HistoricalPriceProviderError("Failed to fetch historical USD/KRW rates") from exc
        if frame is None or frame.empty or "Close" not in frame.columns:
            return {}
        rates: dict[date, float] = {}
        for index, row in frame.iterrows():
            close = row.get("Close")
            if close is None:
                continue
            try:
                value = float(close)
            except (TypeError, ValueError):
                continue
            rates[index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])] = value
        return rates
