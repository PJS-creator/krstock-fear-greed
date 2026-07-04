import pytest

from portfolio.rebalancing import (
    calculate_rebalancing_plan,
    default_target_allocations_from_portfolio,
    is_target_weight_sum_valid,
    normalize_target_allocations,
    target_weight_sum,
)


def test_rebalancing_plan_calculates_value_gaps_and_stock_quantities():
    plan = calculate_rebalancing_plan(
        target_allocations=[
            {"asset_type": "stock", "symbol": "005930", "market": "KR", "currency": "KRW", "display_name": "삼성전자", "target_weight_pct": 40},
            {"asset_type": "stock", "symbol": "QURE", "market": "US", "currency": "USD", "display_name": "QURE", "target_weight_pct": 30},
            {"asset_type": "cash", "currency": "USD", "target_weight_pct": 30},
        ],
        holdings=[
            {"market": "KR", "ticker": "005930", "currency": "KRW", "display_name": "삼성전자", "quantity": 300, "current_price": 100_000},
            {"market": "US", "ticker": "QURE", "currency": "USD", "display_name": "QURE", "quantity": 400, "current_price": 100},
        ],
        cash_krw=0,
        cash_usd=30_000,
        usd_krw=1000,
        total_asset_krw=100_000_000,
    )

    rows = {row.symbol: row for row in plan.rows}

    assert plan.weight_sum_ok
    assert rows["005930"].current_value_krw == pytest.approx(30_000_000)
    assert rows["005930"].target_value_krw == pytest.approx(40_000_000)
    assert rows["005930"].delta_krw == pytest.approx(10_000_000)
    assert rows["005930"].adjustment_quantity == 100

    assert rows["QURE"].current_value_krw == pytest.approx(40_000_000)
    assert rows["QURE"].target_value_krw == pytest.approx(30_000_000)
    assert rows["QURE"].delta_krw == pytest.approx(-10_000_000)
    assert rows["QURE"].adjustment_quantity == -100

    assert rows["CASH_USD"].current_value_krw == pytest.approx(30_000_000)
    assert rows["CASH_USD"].target_value_krw == pytest.approx(30_000_000)
    assert rows["CASH_USD"].delta_krw == pytest.approx(0)


def test_target_weight_sum_validation_allows_small_rounding_error():
    rows = normalize_target_allocations(
        [
            {"asset_type": "stock", "symbol": "AAPL", "market": "US", "currency": "USD", "target_weight_pct": 33.34},
            {"asset_type": "cash", "currency": "KRW", "target_weight_pct": 33.33},
            {"asset_type": "cash", "currency": "USD", "target_weight_pct": 33.33},
        ]
    )

    assert target_weight_sum(rows) == pytest.approx(100.0)
    assert is_target_weight_sum_valid(100.09)
    assert not is_target_weight_sum_valid(99.8)


def test_cash_only_mode_scales_increases_to_available_cash():
    plan = calculate_rebalancing_plan(
        target_allocations=[
            {"asset_type": "stock", "symbol": "AAPL", "market": "US", "currency": "USD", "target_weight_pct": 100},
            {"asset_type": "cash", "currency": "KRW", "target_weight_pct": 0},
        ],
        holdings=[
            {"market": "US", "ticker": "AAPL", "currency": "USD", "display_name": "Apple", "quantity": 1, "current_price": 100}
        ],
        cash_krw=50_000,
        cash_usd=0,
        usd_krw=1000,
        total_asset_krw=150_000,
        mode="cash_only",
    )

    row = next(row for row in plan.rows if row.symbol == "AAPL")

    assert row.delta_krw == pytest.approx(50_000)
    assert row.adjustment_quantity == 0
    assert row.estimated_adjustment_value_krw == pytest.approx(0)


def test_default_target_allocations_include_holdings_and_cash():
    rows = default_target_allocations_from_portfolio(
        [{"market": "KR", "ticker": "005930", "currency": "KRW", "display_name": "삼성전자", "quantity": 10, "current_price": 70_000}],
        cash_krw=300_000,
        cash_usd=0,
        usd_krw=1300,
        total_asset_krw=1_000_000,
    )

    by_symbol = {row["symbol"]: row for row in rows}

    assert by_symbol["005930"]["target_weight_pct"] == pytest.approx(70)
    assert by_symbol["CASH_KRW"]["target_weight_pct"] == pytest.approx(30)
    assert by_symbol["CASH_USD"]["target_weight_pct"] == pytest.approx(0)
