from datetime import date, datetime, timezone

import pandas as pd
import pytest

from portfolio.holdings import QUOTE_STATUS_FAILED, QUOTE_STATUS_STALE, normalize_holding_rows
from portfolio.pricing import (
    FinanceDataReaderKoreaQuoteProvider,
    PriceProviderError,
    ProviderQuote,
    TTLQuoteCache,
    is_alpha_vantage_target,
    is_korea_update_target,
    is_us_quote_target,
    normalize_korea_symbol,
    parse_finance_data_reader_price_frame,
    refresh_holding_quotes,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("005930", "005930"),
        ("005930.KS", "005930"),
        ("005930.KQ", "005930"),
        ("KR:005930", "005930"),
    ],
)
def test_korea_symbol_normalization(raw, expected):
    assert normalize_korea_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["5930", "ABCDEF", "005930 US", "KR:"])
def test_invalid_korea_symbol_validation(raw):
    with pytest.raises(ValueError, match="6자리"):
        normalize_korea_symbol(raw)


def test_finance_data_reader_frame_parsing_uses_latest_and_previous_close():
    frame = pd.DataFrame(
        {"Close": [70000, 71000, 72000]},
        index=pd.to_datetime(["2026-06-18", "2026-06-19", "2026-06-22"]),
    )

    quote = parse_finance_data_reader_price_frame("005930", frame)

    assert quote.symbol == "005930"
    assert quote.price == 72000
    assert quote.previous_close == 71000
    assert quote.provider == "finance_datareader"


def test_finance_data_reader_single_row_uses_current_price_as_previous_close():
    frame = pd.DataFrame({"Close": [72000]}, index=pd.to_datetime(["2026-06-22"]))

    quote = parse_finance_data_reader_price_frame("005930", frame)

    assert quote.price == 72000
    assert quote.previous_close == 72000


def test_finance_data_reader_provider_uses_recent_window_and_mocked_reader():
    calls = []

    def data_reader(symbol, start):
        calls.append((symbol, start))
        return pd.DataFrame(
            {"Close": [1000, 1100]},
            index=pd.to_datetime(["2026-06-19", "2026-06-22"]),
        )

    provider = FinanceDataReaderKoreaQuoteProvider(
        data_reader=data_reader,
        today_fn=lambda: date(2026, 6, 23),
        lookback_days=14,
    )

    quote = provider.get_quote("005930.KS")

    assert calls == [("005930", "2026-06-09")]
    assert quote.symbol == "005930"
    assert quote.price == 1100
    assert quote.previous_close == 1000


def test_finance_data_reader_failure_is_provider_error():
    def data_reader(symbol, start):
        raise RuntimeError("network unavailable")

    provider = FinanceDataReaderKoreaQuoteProvider(data_reader=data_reader)

    with pytest.raises(PriceProviderError, match="국내 주식"):
        provider.get_quote("005930")


def test_korea_target_routing_and_us_target_routing():
    assert is_korea_update_target({"market": "KR", "currency": "KRW"})
    assert is_korea_update_target({"market": "KOSPI", "currency": "KRW"})
    assert not is_korea_update_target({"market": "US", "currency": "USD"})
    assert is_us_quote_target({"market": "US", "currency": "USD"})
    assert not is_us_quote_target({"market": "KR", "currency": "KRW"})
    assert is_alpha_vantage_target({"market": "US", "currency": "USD"})
    assert not is_alpha_vantage_target({"market": "KR", "currency": "KRW"})


def test_kr_quick_holding_normalizes_symbol_aliases():
    rows = normalize_holding_rows([{"market": "KR", "ticker": "KR:005930", "quantity": "3"}])

    assert rows[0]["ticker"] == "005930"
    assert rows[0]["market"] == "KR"
    assert rows[0]["currency"] == "KRW"
    assert rows[0]["display_name"] == "005930"


class MixedUsProvider:
    def get_quote(self, symbol):
        return ProviderQuote(
            symbol=symbol,
            price=200,
            previous_close=190,
            provider="yfinance",
            fetched_at=datetime.now(timezone.utc),
        )


class MixedKoreaProvider:
    def get_quote(self, symbol):
        if symbol == "000660":
            raise PriceProviderError("mock Korea provider failure")
        return ProviderQuote(
            symbol=symbol,
            price=72000,
            previous_close=71000,
            provider="finance_datareader",
            fetched_at=datetime.now(timezone.utc),
        )

    def get_display_name(self, symbol):
        return {"005930": "삼성전자"}.get(symbol, symbol)


def test_mixed_us_and_kr_refresh_keeps_going_when_one_korea_symbol_fails():
    rows = [
        {"market": "US", "ticker": "AAPL", "quantity": 1},
        {"market": "KR", "ticker": "005930", "quantity": 1},
        {"market": "KR", "ticker": "000660", "quantity": 1, "current_price": 100000, "previous_close": 99000},
    ]

    updated_rows, statuses = refresh_holding_quotes(
        rows,
        MixedUsProvider(),
        korea_provider=MixedKoreaProvider(),
        cache=TTLQuoteCache(),
        request_interval_seconds=0,
    )

    assert [row["quote_status"] for row in updated_rows] == ["updated", "updated", QUOTE_STATUS_STALE]
    assert updated_rows[0]["current_price"] == 200
    assert updated_rows[1]["current_price"] == 72000
    assert updated_rows[1]["display_name"] == "삼성전자"
    assert updated_rows[2]["current_price"] == 100000.0
    assert statuses[2].status == QUOTE_STATUS_STALE


def test_korea_refresh_without_last_price_marks_failed():
    rows = [{"market": "KR", "ticker": "000660", "quantity": 1}]

    updated_rows, statuses = refresh_holding_quotes(
        rows,
        MixedUsProvider(),
        korea_provider=MixedKoreaProvider(),
        cache=TTLQuoteCache(),
    )

    assert updated_rows[0]["current_price"] is None
    assert statuses[0].status == QUOTE_STATUS_FAILED


def test_korea_display_name_lookup_success_and_failure():
    listing = pd.DataFrame({"Code": ["005930"], "Name": ["삼성전자"]})
    provider = FinanceDataReaderKoreaQuoteProvider(
        data_reader=lambda symbol, start: pd.DataFrame({"Close": [1]}),
        listing_loader=lambda market: listing,
    )
    failing_provider = FinanceDataReaderKoreaQuoteProvider(
        data_reader=lambda symbol, start: pd.DataFrame({"Close": [1]}),
        listing_loader=lambda market: (_ for _ in ()).throw(RuntimeError("listing unavailable")),
    )

    assert provider.get_display_name("005930") == "삼성전자"
    assert failing_provider.get_display_name("005930") == "005930"
