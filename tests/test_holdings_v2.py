import pytest

from portfolio.holdings import (
    QUOTE_STATUS_FAILED,
    QUOTE_STATUS_STALE,
    build_portfolio_metrics,
    merge_quick_rows_with_existing,
    normalize_holding_rows,
)
from portfolio.pricing import PriceProviderError, ProviderQuote, TTLQuoteCache, refresh_holding_quotes


def test_ticker_quantity_quick_rows_create_default_holding():
    rows = normalize_holding_rows([{"ticker": " abc ", "quantity": "1.5"}])

    assert rows[0]["ticker"] == "ABC"
    assert rows[0]["market"] == "US"
    assert rows[0]["currency"] == "USD"
    assert rows[0]["display_name"] == "ABC"
    assert rows[0]["avg_price"] is None


def test_duplicate_ticker_is_rejected():
    with pytest.raises(ValueError, match="duplicate ticker"):
        normalize_holding_rows([{"ticker": "AAA", "quantity": 1}, {"ticker": "aaa", "quantity": 2}])


def test_invalid_ticker_and_quantity_are_rejected():
    with pytest.raises(ValueError, match="ticker"):
        normalize_holding_rows([{"ticker": "", "quantity": 1}])
    with pytest.raises(ValueError, match="quantity"):
        normalize_holding_rows([{"ticker": "AAA", "quantity": -1}])


def test_merge_quick_rows_preserves_existing_quote_metadata():
    existing = [
        {
            "ticker": "AAA",
            "quantity": 1,
            "current_price": 10,
            "previous_close": 9,
            "quote_status": "updated",
        }
    ]
    merged = merge_quick_rows_with_existing([{"ticker": "AAA", "quantity": 2}], existing)

    assert merged[0]["quantity"] == 2.0
    assert merged[0]["current_price"] == 10.0


def test_avg_price_none_excludes_total_pnl_but_keeps_asset_value():
    metrics = build_portfolio_metrics(
        [{"ticker": "AAA", "quantity": 2, "current_price": 10, "previous_close": 9}],
        cash_krw=100,
        cash_usd=1,
        usd_krw=1000,
    )

    assert metrics.total_position_value_krw == 20000
    assert metrics.cash_total_krw == 1100
    assert metrics.total_pnl_krw is None
    assert metrics.total_pnl_pct is None


def test_krw_usd_cash_conversion_and_usd_exposure():
    metrics = build_portfolio_metrics(
        [{"ticker": "AAA", "quantity": 1, "current_price": 10, "previous_close": 9}],
        cash_krw=100,
        cash_usd=2,
        usd_krw=1000,
    )

    assert metrics.cash_total_krw == 2100
    assert metrics.usd_exposure_krw == 12000
    assert metrics.total_value_krw == 12100


class FakeProvider:
    def __init__(self) -> None:
        self.calls = []

    def get_quote(self, symbol):
        self.calls.append(symbol)
        return ProviderQuote.now(symbol=symbol, price=12, previous_close=10, provider="fake")


class FailingProvider:
    def get_quote(self, symbol):
        raise PriceProviderError("provider unavailable")


def test_quote_refresh_updates_only_explicit_call_and_reports_cached():
    provider = FakeProvider()
    cache = TTLQuoteCache()
    rows = [{"ticker": "AAA", "quantity": 1}]

    first_rows, first_statuses = refresh_holding_quotes(rows, provider, cache=cache)
    second_rows, second_statuses = refresh_holding_quotes(first_rows, provider, cache=cache)

    assert provider.calls == ["AAA"]
    assert first_statuses[0].status == "updated"
    assert second_statuses[0].status == "cached"
    assert second_rows[0]["current_price"] == 12


def test_quote_failure_keeps_last_price_as_stale_and_missing_price_as_failed():
    stale_rows, stale_statuses = refresh_holding_quotes(
        [{"ticker": "AAA", "quantity": 1, "current_price": 10, "previous_close": 9}],
        FailingProvider(),
    )
    failed_rows, failed_statuses = refresh_holding_quotes([{"ticker": "BBB", "quantity": 1}], FailingProvider())

    assert stale_rows[0]["current_price"] == 10.0
    assert stale_statuses[0].status == QUOTE_STATUS_STALE
    assert failed_rows[0]["current_price"] is None
    assert failed_statuses[0].status == QUOTE_STATUS_FAILED
