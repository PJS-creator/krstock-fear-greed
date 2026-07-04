from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
    price_date: date | None = None
    as_of_timestamp: datetime | None = None

    @classmethod
    def now(
        cls,
        *,
        symbol: str,
        price: float,
        previous_close: float,
        provider: str,
        price_date: date | None = None,
        as_of_timestamp: datetime | None = None,
    ) -> "ProviderQuote":
        fetched_at = datetime.now(timezone.utc)
        return cls(
            symbol=symbol,
            price=price,
            previous_close=previous_close,
            provider=provider,
            fetched_at=fetched_at,
            price_date=price_date,
            as_of_timestamp=as_of_timestamp or fetched_at,
        )


@dataclass(frozen=True)
class ProviderIntradayPrices:
    symbol: str
    prices: tuple[float, ...]
    provider: str
    fetched_at: datetime

    @classmethod
    def now(cls, *, symbol: str, prices: tuple[float, ...], provider: str) -> "ProviderIntradayPrices":
        return cls(
            symbol=symbol,
            prices=prices,
            provider=provider,
            fetched_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class ProviderFxRate:
    from_currency: str
    to_currency: str
    rate: float
    provider: str
    fetched_at: datetime
    rate_date: date | None = None
    as_of_timestamp: datetime | None = None

    @classmethod
    def now(
        cls,
        *,
        from_currency: str,
        to_currency: str,
        rate: float,
        provider: str,
        rate_date: date | None = None,
        as_of_timestamp: datetime | None = None,
    ) -> "ProviderFxRate":
        fetched_at = datetime.now(timezone.utc)
        return cls(
            from_currency=from_currency.upper(),
            to_currency=to_currency.upper(),
            rate=rate,
            provider=provider,
            fetched_at=fetched_at,
            rate_date=rate_date,
            as_of_timestamp=as_of_timestamp or fetched_at,
        )


class PriceProvider(Protocol):
    def get_quote(self, symbol: str) -> ProviderQuote:
        """Return the latest provider quote for a symbol or raise PriceProviderError."""


class IntradayPriceProvider(Protocol):
    def get_intraday_prices(self, symbol: str, *, market: str | None = None) -> ProviderIntradayPrices:
        """Return today's minute-level prices for a symbol or raise PriceProviderError."""


class FxProvider(Protocol):
    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        """Return the latest provider FX rate or raise PriceProviderError."""
