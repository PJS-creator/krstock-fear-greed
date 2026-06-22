from datetime import datetime, timezone

import pytest

from portfolio.pricing import (
    PriceProviderError,
    ProviderQuote,
    TTLQuoteCache,
    build_fmp_provider,
    parse_fmp_quote_response,
    update_us_quotes,
)
from portfolio.pricing.service import is_fmp_update_target


def _row(**overrides):
    row = {
        "market": "US",
        "symbol": "AAPL",
        "name": "Apple",
        "currency": "USD",
        "quantity": "2",
        "avg_price": "100",
        "current_price": "120",
        "previous_close": "118",
        "target_weight": "0.5",
        "strategy_tag": "Core",
    }
    row.update(overrides)
    return row


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_quote(self, symbol: str) -> ProviderQuote:
        self.calls.append(symbol)
        return ProviderQuote(
            symbol=symbol.upper(),
            price=155.5,
            previous_close=150.0,
            provider="fake",
            fetched_at=datetime.now(timezone.utc),
        )


class FailingProvider:
    def get_quote(self, symbol: str) -> ProviderQuote:
        raise PriceProviderError("temporary provider outage")


def test_fmp_provider_response_parsing():
    quote = parse_fmp_quote_response(
        "AAPL",
        [
            {
                "symbol": "AAPL",
                "price": 193.42,
                "previousClose": 190.25,
            }
        ],
    )

    assert quote.symbol == "AAPL"
    assert quote.price == pytest.approx(193.42)
    assert quote.previous_close == pytest.approx(190.25)
    assert quote.provider == "fmp"


def test_fmp_provider_rejects_unusable_response():
    with pytest.raises(PriceProviderError, match="previousClose"):
        parse_fmp_quote_response("AAPL", [{"symbol": "AAPL", "price": 193.42}])


def test_missing_api_key_does_not_fail_and_keeps_manual_quotes():
    rows = [_row(symbol="MSFT"), _row(market="KR", symbol="005930", currency="KRW")]

    provider = build_fmp_provider(None)
    updated_rows, statuses = update_us_quotes(rows, provider, cache=TTLQuoteCache())

    assert provider is None
    assert updated_rows[0]["current_price"] == 120.0
    assert updated_rows[0]["previous_close"] == 118.0
    assert statuses[0].status == "missing_api_key"
    assert statuses[1].status == "manual"


def test_fmp_failure_keeps_existing_quote():
    rows = [_row(symbol="MSFT", current_price="120", previous_close="118")]

    updated_rows, statuses = update_us_quotes(rows, FailingProvider(), cache=TTLQuoteCache())

    assert updated_rows[0]["current_price"] == 120.0
    assert updated_rows[0]["previous_close"] == 118.0
    assert statuses[0].status == "failed"
    assert "기존 입력 가격을 유지" in statuses[0].message


def test_only_usd_us_rows_are_auto_update_targets():
    rows = [
        _row(market="US", symbol="AAPL", currency="USD"),
        _row(market="USA", symbol="MSFT", currency="USD"),
        _row(market="KR", symbol="005930", currency="KRW"),
        _row(market="US", symbol="KRWUSD", currency="KRW"),
    ]
    provider = FakeProvider()

    updated_rows, statuses = update_us_quotes(rows, provider, cache=TTLQuoteCache())

    assert [status.status for status in statuses] == ["updated", "updated", "manual", "manual"]
    assert provider.calls == ["AAPL", "MSFT"]
    assert updated_rows[0]["current_price"] == pytest.approx(155.5)
    assert updated_rows[1]["previous_close"] == pytest.approx(150.0)
    assert updated_rows[2]["current_price"] == 120.0
    assert updated_rows[3]["previous_close"] == 118.0


def test_krw_kr_rows_are_excluded_from_auto_update_targets():
    assert not is_fmp_update_target(_row(market="KR", symbol="005930", currency="KRW"))


def test_quote_cache_prevents_repeated_provider_calls():
    rows = [_row(symbol="AAPL")]
    provider = FakeProvider()
    cache = TTLQuoteCache(ttl_seconds=600)

    update_us_quotes(rows, provider, cache=cache)
    update_us_quotes(rows, provider, cache=cache)

    assert provider.calls == ["AAPL"]
