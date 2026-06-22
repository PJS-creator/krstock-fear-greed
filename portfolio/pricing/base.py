from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


class PriceProviderError(RuntimeError):
    """Raised when an optional price provider cannot return a usable quote."""


@dataclass(frozen=True)
class ProviderQuote:
    symbol: str
    price: float
    previous_close: float
    provider: str
    fetched_at: datetime

    @classmethod
    def now(cls, *, symbol: str, price: float, previous_close: float, provider: str) -> "ProviderQuote":
        return cls(
            symbol=symbol,
            price=price,
            previous_close=previous_close,
            provider=provider,
            fetched_at=datetime.now(timezone.utc),
        )


class PriceProvider(Protocol):
    def get_quote(self, symbol: str) -> ProviderQuote:
        """Return the latest provider quote for a symbol or raise PriceProviderError."""
