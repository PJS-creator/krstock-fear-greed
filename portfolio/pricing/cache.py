from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable

from .base import ProviderFxRate, ProviderQuote


@dataclass(frozen=True)
class _CacheEntry:
    quote: ProviderQuote
    stored_at: float


@dataclass(frozen=True)
class _FxCacheEntry:
    rate: ProviderFxRate
    stored_at: float


class TTLQuoteCache:
    def __init__(self, ttl_seconds: int = 600) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, symbol: str) -> ProviderQuote | None:
        key = symbol.upper()
        entry = self._entries.get(key)
        if entry is None:
            return None
        if monotonic() - entry.stored_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry.quote

    def set(self, symbol: str, quote: ProviderQuote) -> None:
        self._entries[symbol.upper()] = _CacheEntry(quote=quote, stored_at=monotonic())

    def get_or_fetch(self, symbol: str, fetcher: Callable[[str], ProviderQuote]) -> ProviderQuote:
        quote, _ = self.get_or_fetch_with_status(symbol, fetcher)
        return quote

    def get_or_fetch_with_status(self, symbol: str, fetcher: Callable[[str], ProviderQuote]) -> tuple[ProviderQuote, bool]:
        cached_quote = self.get(symbol)
        if cached_quote is not None:
            return cached_quote, True
        quote = fetcher(symbol)
        self.set(symbol, quote)
        return quote, False


class TTLFxCache:
    def __init__(self, ttl_seconds: int = 600) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._entries: dict[tuple[str, str], _FxCacheEntry] = {}

    def get(self, from_currency: str, to_currency: str) -> ProviderFxRate | None:
        key = (from_currency.upper(), to_currency.upper())
        entry = self._entries.get(key)
        if entry is None:
            return None
        if monotonic() - entry.stored_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry.rate

    def set(self, rate: ProviderFxRate) -> None:
        key = (rate.from_currency.upper(), rate.to_currency.upper())
        self._entries[key] = _FxCacheEntry(rate=rate, stored_at=monotonic())

    def get_or_fetch_with_status(
        self,
        from_currency: str,
        to_currency: str,
        fetcher: Callable[[str, str], ProviderFxRate],
    ) -> tuple[ProviderFxRate, bool]:
        cached_rate = self.get(from_currency, to_currency)
        if cached_rate is not None:
            return cached_rate, True
        rate = fetcher(from_currency, to_currency)
        self.set(rate)
        return rate, False
