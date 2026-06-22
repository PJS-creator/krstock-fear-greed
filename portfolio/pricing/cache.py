from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Callable

from .base import ProviderQuote


@dataclass(frozen=True)
class _CacheEntry:
    quote: ProviderQuote
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
        cached_quote = self.get(symbol)
        if cached_quote is not None:
            return cached_quote
        quote = fetcher(symbol)
        self.set(symbol, quote)
        return quote
