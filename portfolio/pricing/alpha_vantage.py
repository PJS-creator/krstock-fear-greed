from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .base import PriceProviderError, ProviderQuote

ALPHA_VANTAGE_GLOBAL_QUOTE_URL = "https://www.alphavantage.co/query"


def _raise_if_api_message(payload: dict[str, Any]) -> None:
    for field in ("Note", "Information", "Error Message"):
        if field in payload:
            raise PriceProviderError(f"Alpha Vantage 응답 오류: {payload[field]}")


def _as_non_negative_float(payload: dict[str, Any], field: str) -> float:
    if field not in payload:
        raise PriceProviderError(f"Alpha Vantage Global Quote 응답에 필드가 없습니다: {field}")
    try:
        value = float(payload[field])
    except (TypeError, ValueError) as exc:
        raise PriceProviderError(f"Alpha Vantage Global Quote 필드가 숫자가 아닙니다: {field}") from exc
    if not math.isfinite(value):
        raise PriceProviderError(f"Alpha Vantage Global Quote 필드가 유효한 숫자가 아닙니다: {field}")
    if value < 0:
        raise PriceProviderError(f"Alpha Vantage Global Quote 필드가 음수입니다: {field}")
    return value


def parse_alpha_vantage_global_quote_response(symbol: str, payload: Any) -> ProviderQuote:
    if not isinstance(payload, dict):
        raise PriceProviderError("Alpha Vantage 응답 형식이 올바르지 않습니다.")
    _raise_if_api_message(payload)

    quote_payload = payload.get("Global Quote")
    if not isinstance(quote_payload, dict) or not quote_payload:
        raise PriceProviderError("Alpha Vantage 응답에 Global Quote 데이터가 없습니다.")
    _raise_if_api_message(quote_payload)

    requested_symbol = symbol.strip().upper()
    response_symbol = str(quote_payload.get("01. symbol", "")).strip().upper()
    if not response_symbol:
        raise PriceProviderError("Alpha Vantage Global Quote 응답에 symbol이 없습니다.")
    if response_symbol != requested_symbol:
        raise PriceProviderError(f"Alpha Vantage symbol 불일치: 요청={requested_symbol}, 응답={response_symbol}")

    return ProviderQuote.now(
        symbol=requested_symbol,
        price=_as_non_negative_float(quote_payload, "05. price"),
        previous_close=_as_non_negative_float(quote_payload, "08. previous close"),
        provider="alpha_vantage",
    )


class AlphaVantageQuoteProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = ALPHA_VANTAGE_GLOBAL_QUOTE_URL,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def _quote_url(self, symbol: str) -> str:
        query = urlencode(
            {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol.upper(),
                "apikey": self._api_key,
            }
        )
        return f"{self._base_url}?{query}"

    def get_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise PriceProviderError("symbol is required")
        try:
            with self._opener(self._quote_url(normalized_symbol), timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise PriceProviderError(f"Alpha Vantage quote 요청 실패: {normalized_symbol}: {exc}") from exc
        return parse_alpha_vantage_global_quote_response(normalized_symbol, payload)


def build_alpha_vantage_provider(api_key: str | None) -> AlphaVantageQuoteProvider | None:
    if not api_key:
        return None
    normalized_key = str(api_key).strip()
    if not normalized_key:
        return None
    return AlphaVantageQuoteProvider(normalized_key)
