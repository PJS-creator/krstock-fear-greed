from __future__ import annotations

from datetime import date

import pytest

from portfolio.historical_holdings import (
    HistoricalHoldingsError,
    HistoricalPriceProviderError,
    HistoricalReconstructionError,
    MemoryHistoricalScheduleStore,
    build_snapshot_marker_rows,
    build_ticker_value_series,
    cash_snapshots_to_dicts,
    csv_to_rows,
    daily_rows_as_dicts,
    deserialize_schedule_payload,
    holding_rows_as_dicts,
    holding_snapshots_to_dicts,
    normalize_cash_snapshots,
    normalize_holding_snapshots,
    reconstruct_historical_holdings,
    rows_to_csv,
    serialize_schedule_payload,
)
from portfolio.historical_holdings.normalization import CASH_COLUMNS, HOLDINGS_COLUMNS


class FakeHistoricalPriceProvider:
    def __init__(self, prices=None, fx=None, failures=None):
        self.prices = prices or {}
        self.fx = fx or {}
        self.failures = set(failures or [])
        self.calls = []

    def get_close_prices(self, *, market, ticker, start_date, end_date):
        self.calls.append((market, ticker, start_date, end_date))
        if (market, ticker) in self.failures:
            raise HistoricalPriceProviderError(f"boom {market}/{ticker}")
        return {
            current: value
            for current, value in self.prices.get((market, ticker), {}).items()
            if start_date <= current <= end_date
        }

    def get_usd_krw_rates(self, *, start_date, end_date):
        return {current: value for current, value in self.fx.items() if start_date <= current <= end_date}


def _prices():
    return {
        ("KR", "005930"): {
            date(2026, 6, 1): 80000,
            date(2026, 6, 2): 81000,
            date(2026, 6, 8): 82000,
            date(2026, 6, 16): 83000,
        },
        ("KR", "000660"): {
            date(2026, 6, 16): 280000,
        },
        ("US", "MU"): {
            date(2026, 6, 2): 100,
            date(2026, 6, 3): 110,
        },
    }


def test_holding_schedule_normalization_and_inference_preserves_tickers():
    rows = normalize_holding_snapshots(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930.KS", "quantity": "1.5"},
            {"as_of_date": "2026-06-01", "ticker": "mu", "quantity": 2},
        ]
    )

    assert rows[0].ticker == "005930"
    assert rows[0].market == "KR"
    assert rows[0].currency == "KRW"
    assert rows[1].ticker == "MU"
    assert rows[1].market == "US"
    assert rows[1].currency == "USD"


def test_same_date_multiple_tickers_allowed_but_duplicate_ticker_rejected():
    rows = normalize_holding_snapshots(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1},
            {"as_of_date": "2026-06-01", "ticker": "000660", "quantity": 1},
        ]
    )
    assert [row.ticker for row in rows] == ["000660", "005930"]

    with pytest.raises(HistoricalHoldingsError, match="duplicate"):
        normalize_holding_snapshots(
            [
                {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1},
                {"as_of_date": "2026-06-01", "ticker": "KR:005930", "quantity": 2},
            ]
        )


def test_cash_schedule_forward_fill_and_usd_conversion():
    provider = FakeHistoricalPriceProvider(
        prices={("US", "MU"): {date(2026, 6, 2): 100, date(2026, 6, 3): 110}},
        fx={date(2026, 6, 2): 1300, date(2026, 6, 3): 1310},
    )

    result = reconstruct_historical_holdings(
        [{"as_of_date": "2026-06-02", "ticker": "MU", "quantity": 1}],
        [{"as_of_date": "2026-06-02", "cash_krw": 1000, "cash_usd": 2, "usd_krw": 1200}],
        provider,
        end_date="2026-06-03",
    )

    assert result.daily_rows[0].cash_total_krw == 3400
    assert result.daily_rows[1].cash_total_krw == 3400
    assert result.daily_rows[0].position_value_krw == 120000


def test_historical_fx_fallback_uses_provider_then_current_session_rate():
    provider = FakeHistoricalPriceProvider(
        prices={("US", "MU"): {date(2026, 6, 2): 100}},
        fx={date(2026, 6, 2): 1300},
    )
    result = reconstruct_historical_holdings(
        [{"as_of_date": "2026-06-02", "ticker": "MU", "quantity": 1}],
        [{"as_of_date": "2026-06-02", "cash_usd": 1}],
        provider,
        end_date="2026-06-02",
    )
    assert result.daily_rows[0].usd_krw == 1300

    provider_without_fx = FakeHistoricalPriceProvider(prices={("US", "MU"): {date(2026, 6, 2): 100}})
    fallback = reconstruct_historical_holdings(
        [{"as_of_date": "2026-06-02", "ticker": "MU", "quantity": 1}],
        [{"as_of_date": "2026-06-02", "cash_usd": 1}],
        provider_without_fx,
        end_date="2026-06-02",
        current_usd_krw=1400,
    )
    assert fallback.daily_rows[0].usd_krw == 1400

    with pytest.raises(HistoricalReconstructionError, match="USD/KRW"):
        reconstruct_historical_holdings(
            [{"as_of_date": "2026-06-02", "ticker": "MU", "quantity": 1}],
            [],
            provider_without_fx,
            end_date="2026-06-02",
        )


def test_snapshot_carry_forward_and_missing_ticker_means_holding_ended():
    provider = FakeHistoricalPriceProvider(prices=_prices())
    result = reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 100},
            {"as_of_date": "2026-06-07", "ticker": "005930", "quantity": 200},
            {"as_of_date": "2026-06-16", "ticker": "005930", "quantity": 100},
            {"as_of_date": "2026-06-16", "ticker": "000660", "quantity": 10},
        ],
        [],
        provider,
        end_date="2026-06-16",
    )

    by_date = {row.date: row for row in result.daily_rows}
    assert by_date[date(2026, 6, 1)].position_value_krw == 80000 * 100
    assert by_date[date(2026, 6, 8)].position_value_krw == 82000 * 200
    assert by_date[date(2026, 6, 16)].holdings_count == 2
    assert by_date[date(2026, 6, 16)].position_value_krw == 83000 * 100 + 280000 * 10


def test_non_trading_snapshot_applies_to_next_available_trading_day():
    provider = FakeHistoricalPriceProvider(prices=_prices())
    result = reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 100},
            {"as_of_date": "2026-06-07", "ticker": "005930", "quantity": 200},
        ],
        [],
        provider,
        end_date="2026-06-08",
    )

    assert any(warning.code == "snapshot_next_trading_day" for warning in result.warnings)
    assert {row.date: row.applied_snapshot_date for row in result.daily_rows}[date(2026, 6, 8)] == date(2026, 6, 7)


def test_missing_price_is_not_counted_as_zero():
    provider = FakeHistoricalPriceProvider(prices={("KR", "005930"): {date(2026, 6, 1): 80000, date(2026, 6, 2): 81000}})
    result = reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1},
            {"as_of_date": "2026-06-01", "ticker": "000660", "quantity": 1},
        ],
        [],
        provider,
        end_date="2026-06-02",
    )

    assert result.daily_rows[0].position_value_krw == 80000
    assert result.daily_rows[0].missing_price_count == 1
    assert any(row.ticker == "000660" and row.market_value_krw is None for row in result.holding_rows)
    assert any(warning.code == "missing_price_excluded" and warning.ticker == "000660" for warning in result.warnings)


def test_forward_fill_uses_last_known_price_when_enabled():
    provider = FakeHistoricalPriceProvider(
        prices={
            ("KR", "005930"): {
                date(2026, 6, 1): 80000,
            },
            ("KR", "000660"): {
                date(2026, 6, 2): 280000,
            },
        }
    )

    result = reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1},
            {"as_of_date": "2026-06-01", "ticker": "000660", "quantity": 1},
        ],
        [],
        provider,
        end_date="2026-06-02",
        use_forward_fill_prices=True,
    )

    june_2_005930 = next(row for row in result.holding_rows if row.date == date(2026, 6, 2) and row.ticker == "005930")
    assert june_2_005930.close_price == 80000
    assert june_2_005930.price_status == "forward_filled"

    june_2_000660 = next(row for row in result.holding_rows if row.date == date(2026, 6, 2) and row.ticker == "000660")
    assert june_2_000660.close_price == 280000


def test_price_fetch_failure_keeps_other_tickers():
    provider = FakeHistoricalPriceProvider(
        prices={("KR", "005930"): {date(2026, 6, 1): 80000}},
        failures={("KR", "000660")},
    )
    result = reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1},
            {"as_of_date": "2026-06-01", "ticker": "000660", "quantity": 1},
        ],
        [],
        provider,
        end_date="2026-06-01",
    )

    assert result.failed_tickers == ["KR/000660"]
    assert result.daily_rows[0].priced_count == 1
    assert result.daily_rows[0].missing_price_count == 1


def test_daily_and_holding_rows_export_and_chart_builders():
    provider = FakeHistoricalPriceProvider(prices=_prices())
    result = reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1},
            {"as_of_date": "2026-06-16", "ticker": "000660", "quantity": 1},
        ],
        [],
        provider,
        end_date="2026-06-16",
    )

    assert daily_rows_as_dicts(result.daily_rows)[0]["date"] == "2026-06-01"
    assert holding_rows_as_dicts(result.holding_rows)[0]["ticker"] == "005930"
    assert build_snapshot_marker_rows(result)[0] == {"snapshot_date": "2026-06-01", "applied_date": "2026-06-01"}
    series_row = next(row for row in build_ticker_value_series(result) if row["ticker"] == "005930")
    assert series_row["quantity"] == 1
    assert series_row["close_price"] == 80000


def test_schedule_csv_round_trip_preserves_leading_zero():
    holdings = [{"as_of_date": "2026-06-01", "ticker": "005930", "quantity": "10"}]
    csv_text = rows_to_csv(holdings, HOLDINGS_COLUMNS)
    rows = csv_to_rows(csv_text)

    assert rows[0]["ticker"] == "005930"
    assert normalize_holding_snapshots(rows)[0].ticker == "005930"


def test_cash_csv_round_trip():
    cash = normalize_cash_snapshots(csv_to_rows(rows_to_csv([{"as_of_date": "2026-06-01", "cash_krw": "1"}], CASH_COLUMNS)))

    assert cash[0].cash_krw == 1


def test_schedule_payload_and_memory_store_save_load_delete():
    payload = serialize_schedule_payload(
        [{"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 10}],
        [{"as_of_date": "2026-06-01", "cash_krw": 1000}],
        default_start_date="2026-06-01",
        notes="demo",
    )
    decoded = deserialize_schedule_payload(payload)
    store = MemoryHistoricalScheduleStore()

    saved = store.save_schedule("owner", "demo", payload)
    loaded = store.get_schedule("owner", "demo")

    assert decoded["schema_version"] == 1
    assert saved.schedule_name == "demo"
    assert loaded is not None
    assert loaded.payload_json == payload
    assert [record.schedule_name for record in store.list_schedules("owner")] == ["demo"]
    assert store.delete_schedule("owner", "demo")
    assert store.get_schedule("owner", "demo") is None


def test_schema_version_migration_guard():
    with pytest.raises(Exception, match="schema_version"):
        deserialize_schedule_payload({"schema_version": 999, "holdings_snapshots": [], "cash_snapshots": []})


def test_snapshot_dict_helpers():
    holdings = normalize_holding_snapshots([{"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 1}])
    cash = normalize_cash_snapshots([{"as_of_date": "2026-06-01", "cash_krw": 1}])

    assert holding_snapshots_to_dicts(holdings)[0]["as_of_date"] == "2026-06-01"
    assert cash_snapshots_to_dicts(cash)[0]["as_of_date"] == "2026-06-01"
