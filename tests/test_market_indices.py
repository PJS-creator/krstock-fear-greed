from datetime import datetime, timezone

from portfolio.market_indices import (
    DEFAULT_MARKET_INDEX_SPECS,
    MarketIndexProviderError,
    MarketIndexQuote,
    MarketIndexSpec,
    failed_market_index_quote,
    fetch_market_indices,
    parse_yahoo_chart_market_index_response,
)


def _payload() -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": 7200.0,
                        "regularMarketPreviousClose": 7142.4,
                        "regularMarketTime": 1783483200,
                    },
                    "timestamp": [1783310400, 1783396800, 1783483200],
                    "indicators": {"quote": [{"close": [7100.0, 7142.4, 7200.0]}]},
                }
            ],
            "error": None,
        }
    }


def test_parse_yahoo_chart_market_index_response_calculates_change():
    quote = parse_yahoo_chart_market_index_response(MarketIndexSpec("코스피", "^KS11"), _payload())

    assert quote.label == "코스피"
    assert quote.symbol == "^KS11"
    assert quote.value == 7200.0
    assert round(quote.change or 0.0, 1) == 57.6
    assert round(quote.change_pct or 0.0, 4) == 0.0081
    assert quote.status == "updated"


def test_parse_yahoo_chart_market_index_response_uses_display_symbol():
    quote = parse_yahoo_chart_market_index_response(MarketIndexSpec("미국 바이오", "^SPSIBI", "SPSIBI"), _payload())

    assert quote.symbol == "SPSIBI"


def test_fetch_market_indices_preserves_failed_index_rows():
    class FailingProvider:
        def get_quote(self, spec):
            raise MarketIndexProviderError("boom")

    rows = fetch_market_indices([MarketIndexSpec("나스닥", "^IXIC")], provider=FailingProvider())

    assert rows[0].label == "나스닥"
    assert rows[0].status == "failed"
    assert rows[0].value is None
    assert "boom" in str(rows[0].error_message)


def test_default_market_indices_include_requested_five_indices():
    assert [(spec.label, spec.display_symbol or spec.symbol) for spec in DEFAULT_MARKET_INDEX_SPECS] == [
        ("코스피", "^KS11"),
        ("코스닥", "^KQ11"),
        ("나스닥", "^IXIC"),
        ("필라델피아 반도체", "SOX"),
        ("미국 바이오", "SPSIBI"),
    ]


def test_failed_market_index_quote_has_safe_display_fields():
    quote = failed_market_index_quote(MarketIndexSpec("코스닥", "^KQ11"), "network")

    assert isinstance(quote.fetched_at, datetime)
    assert quote.fetched_at.tzinfo == timezone.utc
    assert quote.status == "failed"
    assert quote.change_pct is None

