from datetime import datetime, timezone

import pandas as pd
import pytest

from portfolio.pricing import (
    FallbackFxProvider,
    FallbackQuoteProvider,
    KoreaInvestmentQuoteProvider,
    OpenErApiFxProvider,
    PriceProviderError,
    ProviderFxRate,
    ProviderQuote,
    TTLFxCache,
    TTLQuoteCache,
    YahooChartFxProvider,
    YFinanceFxProvider,
    YFinanceIntradayPriceProvider,
    YFinanceQuoteProvider,
    build_alpha_vantage_provider,
    build_kis_quote_provider,
    parse_kis_domestic_futures_intraday_response,
    parse_kis_domestic_quote_response,
    parse_kis_overseas_quote_response,
    parse_kis_token_response,
    parse_alpha_vantage_currency_exchange_response,
    parse_alpha_vantage_global_quote_response,
    parse_open_er_api_usd_krw_response,
    parse_yahoo_chart_usd_krw_response,
    parse_yfinance_history_frame,
    parse_yfinance_intraday_frame,
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
    assert quote.price_date.isoformat() == "2026-06-30"


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


def test_yfinance_intraday_frame_parsing_downsamples_close_prices():
    frame = pd.DataFrame(
        {"Close": [100, 101, 102, 103, 104]},
        index=pd.to_datetime(["2026-06-30 09:30", "2026-06-30 09:31", "2026-06-30 09:32", "2026-06-30 09:33", "2026-06-30 09:34"]),
    )

    prices = parse_yfinance_intraday_frame("AAPL", frame, max_points=3)

    assert prices == (100.0, 102.0, 104.0)


def test_yfinance_intraday_provider_tries_korea_suffix_candidates():
    calls = []

    def history_loader(symbol, *, period, interval, timeout_seconds):
        calls.append((symbol, period, interval, timeout_seconds))
        if symbol.endswith(".KS"):
            return pd.DataFrame({"Close": []})
        return pd.DataFrame({"Close": [70000, 70100, 70200]}, index=pd.to_datetime(["2026-06-30 09:00", "2026-06-30 09:01", "2026-06-30 09:02"]))

    provider = YFinanceIntradayPriceProvider(history_loader=history_loader)

    intraday = provider.get_intraday_prices("005930", market="KR")

    assert [call[0] for call in calls] == ["005930.KS", "005930.KQ"]
    assert intraday.symbol == "005930"
    assert intraday.prices == (70000.0, 70100.0, 70200.0)


def test_yfinance_fx_provider_uses_krw_equals_symbol():
    calls = []

    def history_loader(symbol, *, period, interval, timeout_seconds):
        calls.append((symbol, period, interval, timeout_seconds))
        return pd.DataFrame({"Close": [1375.25, 1380.5]}, index=pd.to_datetime(["2026-06-29", "2026-06-30"]))

    provider = YFinanceFxProvider(history_loader=history_loader)

    rate = provider.get_exchange_rate("usd", "krw")

    assert calls == [("KRW=X", "5d", "1d", 10.0)]
    assert rate.from_currency == "USD"
    assert rate.to_currency == "KRW"
    assert rate.rate == pytest.approx(1380.5)
    assert rate.rate_date.isoformat() == "2026-06-30"


def test_yahoo_chart_fx_response_uses_latest_valid_close():
    rate = parse_yahoo_chart_usd_krw_response(
        {
            "chart": {
                "result": [
                    {
                        "indicators": {
                            "quote": [
                                {
                                    "close": [None, 1377.25, 1381.5],
                                }
                            ]
                        },
                        "timestamp": [1782777600, 1782864000, 1782950400],
                    }
                ],
                "error": None,
            }
        }
    )

    assert rate.from_currency == "USD"
    assert rate.to_currency == "KRW"
    assert rate.rate == pytest.approx(1381.5)
    assert rate.provider == "yahoo-chart"
    assert rate.as_of_timestamp is not None


def test_yahoo_chart_fx_provider_uses_short_timeout_loader():
    calls = []

    def response_loader(url, timeout_seconds):
        calls.append((url, timeout_seconds))
        return {
            "chart": {
                "result": [
                    {
                        "indicators": {
                            "quote": [
                                {
                                    "close": [1380.0],
                                }
                            ]
                        }
                    }
                ],
                "error": None,
            }
        }

    provider = YahooChartFxProvider(response_loader=response_loader, timeout_seconds=3.0)
    rate = provider.get_exchange_rate("usd", "krw")

    assert calls == [("https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?range=5d&interval=1d", 3.0)]
    assert rate.rate == pytest.approx(1380.0)
    assert rate.provider == "yahoo-chart"


def test_open_er_api_fx_response_parsing_uses_krw_rate():
    rate = parse_open_er_api_usd_krw_response(
        {
            "result": "success",
            "base_code": "USD",
            "rates": {"KRW": 1388.25},
        }
    )

    assert rate.from_currency == "USD"
    assert rate.to_currency == "KRW"
    assert rate.rate == pytest.approx(1388.25)
    assert rate.provider == "open-er-api"


def test_open_er_api_fx_provider_uses_short_timeout_loader():
    calls = []

    def response_loader(url, timeout_seconds):
        calls.append((url, timeout_seconds))
        return {
            "result": "success",
            "base_code": "USD",
            "rates": {"KRW": 1387.5},
        }

    provider = OpenErApiFxProvider(response_loader=response_loader, timeout_seconds=3.0)
    rate = provider.get_exchange_rate("usd", "krw")

    assert calls == [("https://open.er-api.com/v6/latest/USD", 3.0)]
    assert rate.rate == pytest.approx(1387.5)
    assert rate.provider == "open-er-api"


def test_fallback_fx_provider_uses_next_provider_after_failure():
    fallback = FallbackFxProvider([FailingProvider(), FakeProvider()])

    rate = fallback.get_exchange_rate("USD", "KRW")

    assert rate.rate == pytest.approx(1380.5)
    assert rate.provider == "fake"


def test_yfinance_fx_provider_rejects_unsupported_pair():
    provider = YFinanceFxProvider(history_loader=lambda *args, **kwargs: pd.DataFrame())

    with pytest.raises(PriceProviderError, match="USD/KRW"):
        provider.get_exchange_rate("EUR", "KRW")


def test_kis_token_response_parsing_uses_expiry_text():
    now = datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc)
    token, expires_at = parse_kis_token_response(
        {
            "access_token": "token-value",
            "access_token_token_expired": "2026-07-09 09:00:00",
        },
        now=now,
    )

    assert token == "token-value"
    assert expires_at.tzinfo is not None
    assert expires_at > now


def test_kis_domestic_quote_response_parsing():
    quote = parse_kis_domestic_quote_response(
        "005930",
        {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "72000",
                "stck_sdpr": "71000",
                "stck_bsop_date": "20260708",
                "stck_cntg_hour": "103015",
            },
        },
    )

    assert quote.symbol == "005930"
    assert quote.price == pytest.approx(72000)
    assert quote.previous_close == pytest.approx(71000)
    assert quote.provider == "korea_investment"
    assert quote.price_date.isoformat() == "2026-07-08"
    assert quote.as_of_timestamp is not None


def test_kis_overseas_quote_response_parsing():
    quote = parse_kis_overseas_quote_response(
        "googl",
        {
            "rt_cd": "0",
            "output": {
                "last": "180.25",
                "base": "178.50",
                "xymd": "20260707",
                "xhms": "093000",
            },
        },
    )

    assert quote.symbol == "GOOGL"
    assert quote.price == pytest.approx(180.25)
    assert quote.previous_close == pytest.approx(178.5)
    assert quote.provider == "korea_investment"
    assert quote.price_date.isoformat() == "2026-07-07"


def test_kis_provider_uses_domestic_endpoint_and_token_headers():
    calls = []

    def response_loader(method, url, headers, body, timeout_seconds):
        calls.append((method, url, headers, body, timeout_seconds))
        if url.endswith("/oauth2/tokenP"):
            return {"access_token": "token-value", "expires_in": 3600}
        assert "/uapi/domestic-stock/v1/quotations/inquire-price" in url
        assert "FID_INPUT_ISCD=005930" in url
        assert headers["authorization"] == "Bearer token-value"
        assert headers["tr_id"] == "FHKST01010100"
        return {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "72000",
                "stck_sdpr": "71000",
            },
        }

    provider = KoreaInvestmentQuoteProvider(app_key="app-key", app_secret="secret", response_loader=response_loader)
    quote = provider.get_quote("005930")

    assert quote.price == pytest.approx(72000)
    assert [call[0] for call in calls] == ["POST", "GET"]


def test_kis_provider_tries_us_exchange_candidates_until_success():
    urls = []

    def response_loader(method, url, headers, body, timeout_seconds):
        urls.append(url)
        if url.endswith("/oauth2/tokenP"):
            return {"access_token": "token-value", "expires_in": 3600}
        if "EXCD=NAS" in url:
            return {"rt_cd": "1", "msg1": "not found"}
        assert "EXCD=NYS" in url
        assert headers["tr_id"] == "HHDFS00000300"
        return {
            "rt_cd": "0",
            "output": {
                "last": "41.25",
                "base": "40.00",
            },
        }

    provider = KoreaInvestmentQuoteProvider(
        app_key="app-key",
        app_secret="secret",
        response_loader=response_loader,
        us_exchanges=("NAS", "NYS"),
    )
    quote = provider.get_quote("QURE")
    second_quote = provider.get_quote("QURE")

    assert quote.symbol == "QURE"
    assert quote.price == pytest.approx(41.25)
    assert second_quote.price == pytest.approx(41.25)
    assert sum(url.endswith("/oauth2/tokenP") for url in urls) == 1
    assert sum("EXCD=NAS" in url for url in urls) == 1
    assert sum("EXCD=NYS" in url for url in urls) == 2


def test_kis_domestic_futures_intraday_response_parsing_sorts_points():
    points = parse_kis_domestic_futures_intraday_response(
        {
            "rt_cd": "0",
            "output2": [
                {"stck_bsop_date": "20260708", "stck_cntg_hour": "100000", "futs_prpr": "382.50"},
                {"stck_bsop_date": "20260708", "stck_cntg_hour": "090000", "futs_prpr": "381.25"},
            ],
        }
    )

    assert [point[1] for point in points] == [381.25, 382.50]
    assert all(point[0] is not None for point in points)


def test_kis_provider_uses_domestic_futures_intraday_endpoint():
    calls = []

    def response_loader(method, url, headers, body, timeout_seconds):
        calls.append((method, url, headers, body, timeout_seconds))
        if url.endswith("/oauth2/tokenP"):
            return {"access_token": "token-value", "expires_in": 3600}
        assert "/uapi/domestic-futureoption/v1/quotations/inquire-time-futurechartprice" in url
        assert "FID_COND_MRKT_DIV_CODE=F" in url
        assert "FID_INPUT_ISCD=101W9000" in url
        assert headers["authorization"] == "Bearer token-value"
        assert headers["tr_id"] == "FHKIF03020200"
        return {
            "rt_cd": "0",
            "output2": [
                {"stck_bsop_date": "20260708", "stck_cntg_hour": "090000", "futs_prpr": "381.25"},
                {"stck_bsop_date": "20260708", "stck_cntg_hour": "100000", "futs_prpr": "382.50"},
            ],
        }

    provider = KoreaInvestmentQuoteProvider(app_key="app-key", app_secret="secret", response_loader=response_loader)
    points = provider.get_domestic_futures_intraday_closes("101W9000")

    assert [point[1] for point in points] == [381.25, 382.50]
    assert [call[0] for call in calls] == ["POST", "GET"]


def test_kis_builder_returns_none_without_credentials():
    assert build_kis_quote_provider("", "secret") is None
    assert build_kis_quote_provider("app-key", "") is None


def test_fallback_quote_provider_uses_next_provider_after_failure():
    fallback = FallbackQuoteProvider([FailingProvider(), FakeProvider()])

    quote = fallback.get_quote("MSFT")

    assert quote.price == pytest.approx(155.5)
    assert quote.provider == "fake"


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
    assert first_status.source == "fake"
    assert first_status.as_of_timestamp is not None
    assert failed_rate == 1300
    assert failed_status.status == "failed"
    assert failed_status.error_message == "temporary provider outage"
