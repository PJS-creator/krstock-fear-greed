import pytest

from portfolio.rebalancing import calculate_rebalancing_plan, is_negligible_rebalance_delta


def test_small_rebalance_delta_keeps_action_at_hold():
    plan = calculate_rebalancing_plan(
        target_allocations=[
            {"asset_type": "stock", "symbol": "QURE", "market": "US", "currency": "USD", "display_name": "QURE", "target_weight_pct": 50.03},
            {"asset_type": "cash", "currency": "KRW", "target_weight_pct": 49.97},
        ],
        holdings=[
            {"market": "US", "ticker": "QURE", "currency": "USD", "display_name": "QURE", "quantity": 10, "current_price": 10}
        ],
        cash_krw=100_000,
        cash_usd=0,
        usd_krw=1000,
        total_asset_krw=200_000,
    )

    qure = next(row for row in plan.rows if row.symbol == "QURE")

    assert qure.delta_krw == pytest.approx(60)
    assert qure.adjustment_quantity == 0
    assert qure.estimated_adjustment_value_krw == pytest.approx(0)
    assert qure.action == "유지"


def test_rebalance_delta_threshold_uses_amount_or_weight():
    assert is_negligible_rebalance_delta(99_999, 1_000_000_000)
    assert is_negligible_rebalance_delta(400_000, 1_000_000_000)
    assert not is_negligible_rebalance_delta(1_000_000, 100_000_000)
