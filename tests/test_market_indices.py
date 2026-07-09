from datetime import datetime, timezone

from portfolio.market_indices import (
    DEFAULT_MARKET_INDEX_SPECS,
    DEFAULT_MARKET_WARNING_SPECS,
    MarketIndexProviderError,
    MarketIndexQuote,
    MarketIndexSpec,
    MarketWarningSpec,
    failed_market_index_quote,
    failed_market_warning_signal,
    fetch_market_indices,
    fetch_market_warning_signals,
    parse_yahoo_chart_market_index_response,
    parse_yahoo_chart_market_warning_response,
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


def _warning_payload(closes: list[float]) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "meta": {"regularMarketTime": 1783483200},
                    "timestamp": [1783483200 + index * 3600 for index in range(len(closes))],
                    "indicators": {"quote": [{"close": closes}]},
                }
            ],
            "error": None,
        }
    }


def test_default_market_indices_include_requested_six_indices():
    assert [(spec.label, spec.display_symbol or spec.symbol) for spec in DEFAULT_MARKET_INDEX_SPECS] == [
        ("코스피", "^KS11"),
        ("코스닥", "^KQ11"),
        ("나스닥", "^IXIC"),
        ("필라델피아 반도체", "SOX"),
        ("미국 바이오", "SPSIBI"),
        ("금 지수", "XAU/USD"),
    ]


def test_default_market_warning_specs_track_kospi_and_nasdaq_futures():
    assert [(spec.label, spec.display_symbol or spec.symbol) for spec in DEFAULT_MARKET_WARNING_SPECS] == [
        ("KOSPI 200 선물", "KOS"),
        ("NASDAQ 100 선물", "NQ=F"),
    ]


def test_parse_market_warning_response_flags_buy_blocked_on_upper_band_breakout():
    quote = parse_yahoo_chart_market_warning_response(
        MarketWarningSpec("NASDAQ 100 선물", "NQ=F"),
        _warning_payload([100.0] * 179 + [120.0]),
    )

    assert quote.status == "buy_blocked"
    assert quote.trigger == "상단 이탈"
    assert quote.blocks_buy
    assert quote.upper_band is not None


def test_parse_market_warning_response_flags_sell_blocked_on_lower_band_breakout():
    quote = parse_yahoo_chart_market_warning_response(
        MarketWarningSpec("NASDAQ 100 선물", "NQ=F"),
        _warning_payload([100.0] * 179 + [80.0]),
    )

    assert quote.status == "sell_blocked"
    assert quote.trigger == "하단 이탈"
    assert quote.blocks_sell
    assert quote.lower_band is not None


def test_parse_market_warning_response_handles_insufficient_intraday_data():
    quote = parse_yahoo_chart_market_warning_response(
        MarketWarningSpec("KOSPI 200 선물", "KOS=F", "KOS"),
        _warning_payload([100.0] * 20),
    )

    assert quote.status == "insufficient"
    assert quote.value == 100.0
    assert "180" in str(quote.error_message)


def test_fetch_market_warning_signals_preserves_failed_rows():
    class FailingProvider:
        def get_signal(self, spec):
            raise MarketIndexProviderError("boom")

    rows = fetch_market_warning_signals([MarketWarningSpec("NASDAQ 100 선물", "NQ=F")], provider=FailingProvider())

    assert rows[0].label == "NASDAQ 100 선물"
    assert rows[0].status == "failed"
    assert rows[0].value is None
    assert "boom" in str(rows[0].error_message)


def test_failed_market_index_quote_has_safe_display_fields():
    quote = failed_market_index_quote(MarketIndexSpec("코스닥", "^KQ11"), "network")

    assert isinstance(quote.fetched_at, datetime)
    assert quote.fetched_at.tzinfo == timezone.utc
    assert quote.status == "failed"
    assert quote.change_pct is None


def test_failed_market_warning_signal_has_safe_display_fields():
    signal = failed_market_warning_signal(MarketWarningSpec("KOSPI 200 선물", "KOS=F", "KOS"), "network")

    assert isinstance(signal.fetched_at, datetime)
    assert signal.fetched_at.tzinfo == timezone.utc
    assert signal.status == "failed"
    assert signal.trigger == "조회 실패"

