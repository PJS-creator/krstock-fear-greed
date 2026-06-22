from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import urlopen

from .base import PriceProviderError, ProviderQuote

DEFAULT_FMP_BASE_URL = "https://financialmodelingprep.com/api/v3/quote"


def _as_float(payload: dict[str, Any], field: str) -> float:
    if field not in payload:
        raise PriceProviderError(f"FMP response missing field: {field}")
    try:
        value = float(payload[field])
    except (TypeError, ValueError) as exc:
        raise PriceProviderError(f"FMP response field is not numeric: {field}") from exc
    if not math.isfinite(value):
        raise PriceProviderError(f"FMP response field is not finite: {field}")
    if value < 0:
        raise PriceProviderError(f"FMP response field is negative: {field}")
    return value


def _first_quote_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        if not payload:
            raise PriceProviderError("FMP response did not include quote data")
        quote_payload = payload[0]
    elif isinstance(payload, dict):
        quote_payload = payload
    else:
        raise PriceProviderError("FMP response has unexpected shape")
    if not isinstance(quote_payload, dict):
        raise PriceProviderError("FMP quote entry has unexpected shape")
    if "Error Message" in quote_payload:
        raise PriceProviderError(str(quote_payload["Error Message"]))
    return quote_payload


def parse_fmp_quote_response(symbol: str, payload: Any) -> ProviderQuote:
    quote_payload = _first_quote_payload(payload)
    price = _as_float(quote_payload, "price")
    previous_close = _as_float(quote_payload, "previousClose")
    response_symbol = str(quote_payload.get("symbol") or symbol).upper()
    requested_symbol = symbol.upper()
    if response_symbol and response_symbol != requested_symbol:
        raise PriceProviderError(f"FMP response symbol mismatch: expected {requested_symbol}, got {response_symbol}")
    return ProviderQuote.now(
        symbol=requested_symbol,
        price=price,
        previous_close=previous_close,
        provider="fmp",
    )


class FMPQuoteProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_FMP_BASE_URL,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def _quote_url(self, symbol: str) -> str:
        query = urlencode({"apikey": self._api_key})
        return f"{self._base_url}/{quote(symbol.upper())}?{query}"

    def get_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise PriceProviderError("symbol is required")
        try:
            with self._opener(self._quote_url(normalized_symbol), timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise PriceProviderError(f"FMP quote request failed for {normalized_symbol}: {exc}") from exc
        return parse_fmp_quote_response(normalized_symbol, payload)


def build_fmp_provider(api_key: str | None) -> FMPQuoteProvider | None:
    if not api_key:
        return None
    normalized_key = str(api_key).strip()
    if not normalized_key:
        return None
    return FMPQuoteProvider(normalized_key)
