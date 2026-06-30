from datetime import datetime, timezone

import pandas as pd
import pytest

from portfolio.pricing import (
    PriceProviderError,
    ProviderFxRate,
    ProviderQuote,
    TTLFxCache,
    TTLQuoteCache,
    YFinanceQuoteProvider,
    build_alpha_vantage_provider,
    parse_alpha_vantage_currency_exchange_response,
    parse_alpha_vantage_global_quote_response,
    parse_yfinance_history_frame,
    refresh_usd_krw,
    update_us_quotes,
)
from portfolio.pricing.service import is_auto_update_target


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
        self.fx_calls: list[tuple[str, str]] = []

    def get_quote(self, symbol: str) -> ProviderQuote:
        self.calls.append(symbol)
        return ProviderQuote(
            symbol=symbol.upper(),
            price=155.5,
            previous_close=150.0,
            provider="fake",
            fetched_at=datetime.now(timezone.utc),
        )

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        self.fx_calls.append((from_currency, to_currency))
        return ProviderFxRate.now(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=1380.5,
            provider="fake",
        )


class FailingProvider:
    def get_quote(self, symbol: str) -> ProviderQuote:
        raise PriceProviderError("temporary provider outage")

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> ProviderFxRate:
        raise PriceProviderError("temporary provider outage")


def test_alpha_vantage_global_quote_response_parsing():
    quote = parse_alpha_vantage_global_quote_response(
        "IBM",
        {
            "Global Quote": {
                "01. symbol": "IBM",
                "05. price": "182.1500",
                "08. previous close": "180.9200",
            }
        },
    )

    assert quote.symbol == "IBM"
    assert quote.price == pytest.approx(182.15)
    assert quote.previous_close == pytest.approx(180.92)
    assert quote.provider == "alpha_vantage"


def test_alpha_vantage_currency_exchange_response_parsing():
    rate = parse_alpha_vantage_currency_exchange_response(
        "USD",
        "KRW",
        {
            "Realtime Currency Exchange Rate": {
                "1. From_Currency Code": "USD",
                "3. To_Currency Code": "KRW",
                "5. Exchange Rate": "1380.5000",
            }
        },
    )

    assert rate.from_currency == "USD"
    assert rate.to_currency == "KRW"
    assert rate.rate == pytest.approx(1380.5)


def test_alpha_vantage_empty_global_quote_is_rejected():
    with pytest.raises(PriceProviderError, match="Global Quote"):
        parse_alpha_vantage_global_quote_response("IBM", {"Global Quote": {}})


def test_alpha_vantage_missing_global_quote_is_rejected():
    with pytest.raises(PriceProviderError, match="Global Quote"):
        parse_alpha_vantage_global_quote_response("IBM", {})


@pytest.mark.parametrize(
    "payload",
    [
        {"Note": "Thank you for using Alpha Vantage. Our standard API rate limit is 25 requests per day."},
        {"Information": "The **demo** API key is for demo purposes only."},
        {"Error Message": "Invalid API call."},
    ],
)
def test_alpha_vantage_rate_limit_and_api_messages_are_rejected(payload):
    with pytest.raises(PriceProviderError, match="Alpha Vantage"):
        parse_alpha_vantage_global_quote_response("IBM", payload)


def test_alpha_vantage_burst_limit_message_is_user_friendly():
    payload = {
        "Information": (
            "Thank you for using Alpha Vantage! Please consider spreading out your free API requests more sparingly "
            "(1 request per second). You may subscribe to any of the premium plans at "
            "https://www.alphavantage.co/premium/ to lift the free key rate limit."
        )
    }

    with pytest.raises(PriceProviderError) as exc_info:
        parse_alpha_vantage_global_quote_response("IBM", payload)

    message = str(exc_info.value)
    assert "요청 간격 제한" in message
    assert "premium" not in message
    assert "https://" not in message


def test_alpha_vantage_symbol_mismatch_is_rejected():
    with pytest.raises(PriceProviderError, match="symbol"):
        parse_alpha_vantage_global_quote_response(
            "IBM",
            {
                "Global Quote": {
                    "01. symbol": "MSFT",
                    "05. price": "182.1500",
                    "08. previous close": "180.9200",
                }
            },
        )


def test_yfinance_history_frame_parsing_uses_latest_and_previous_close():
    frame = pd.DataFrame(
        {"Close": [180.5, 182.25, 181.75]},
        index=pd.to_datetime(["2026-06-26", "2026-06-29", "2026-06-30"]),
    )

    quote = parse_yfinance_history_frame("googl", frame)

    assert quote.symbol == "GOOGL"
    assert quote.price == pytest.approx(181.75)
    assert quote.previous_close == pytest.approx(182.25)
    assert quote.provider == "yfinance"


def test_yfinance_provider_uses_configured_history_loader():
    calls = []

    def history_loader(symbol, *, period, interval, timeout_seconds):
        calls.append((symbol, period, interval, timeout_seconds))
        return pd.DataFrame({"Close": [100, 101]}, index=pd.to_datetime(["2026-06-29", "2026-06-30"]))

    provider = YFinanceQuoteProvider(history_loader=history_loader)

    quote = provider.get_quote(" aapl ")

    assert calls == [("AAPL", "5d", "1d", 10.0)]
    assert quote.symbol == "AAPL"
    assert quote.price == 101


def test_missing_us_provider_does_not_fail_and_keeps_manual_quotes():
    rows = [_row(symbol="MSFT"), _row(market="KR", symbol="005930", currency="KRW")]

    provider = build_alpha_vantage_provider(None)
    updated_rows, statuses = update_us_quotes(rows, provider, cache=TTLQuoteCache())

    assert provider is None
    assert updated_rows[0]["current_price"] == 120.0
    assert updated_rows[0]["previous_close"] == 118.0
    assert statuses[0].status == "missing"
    assert statuses[1].status == "manual"


def test_provider_failure_keeps_existing_quote():
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
    assert not is_auto_update_target(_row(market="KR", symbol="005930", currency="KRW"))


def test_quote_cache_prevents_repeated_provider_calls():
    rows = [_row(symbol="AAPL")]
    provider = FakeProvider()
    cache = TTLQuoteCache(ttl_seconds=600)

    update_us_quotes(rows, provider, cache=cache)
    update_us_quotes(rows, provider, cache=cache)

    assert provider.calls == ["AAPL"]


def test_fx_refresh_uses_cache_and_failure_keeps_manual_rate():
    provider = FakeProvider()
    cache = TTLFxCache(ttl_seconds=600)

    first_rate, first_status = refresh_usd_krw(provider, 1300, cache=cache)
    second_rate, second_status = refresh_usd_krw(provider, 1300, cache=cache)
    failed_rate, failed_status = refresh_usd_krw(FailingProvider(), 1300, cache=TTLFxCache())

    assert first_rate == pytest.approx(1380.5)
    assert second_rate == pytest.approx(1380.5)
    assert provider.fx_calls == [("USD", "KRW")]
    assert first_status.status == "updated"
    assert second_status.status == "cached"
    assert failed_rate == 1300
    assert failed_status.status == "failed"
