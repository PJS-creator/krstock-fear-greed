import pytest

from app.ui.rebalancing import rebalancing_empty_result_message
from portfolio.rebalancing import is_target_weight_sum_valid, serialize_target_allocations, target_weight_sum
from portfolio.storage import MemoryPortfolioStore, deserialize_portfolio_payload_v2, serialize_portfolio_payload


def test_target_allocations_round_trip_through_snapshot_payload_source_of_truth():
    target_allocations = [
        {"asset_type": "stock", "symbol": "005930", "market": "KR", "currency": "KRW", "display_name": "삼성전자", "target_weight_pct": 60},
        {"asset_type": "cash", "currency": "KRW", "target_weight_pct": 40},
    ]
    payload = serialize_portfolio_payload(
        [],
        usd_krw=1300,
        cash_krw=1_000_000,
        target_allocations=target_allocations,
    )
    store = MemoryPortfolioStore()

    store.save_portfolio("user-a", "main", payload)
    loaded = store.get_portfolio("user-a", "main")

    assert loaded is not None
    reloaded = deserialize_portfolio_payload_v2(loaded.payload_json)
    assert reloaded["target_allocations"] == serialize_target_allocations(target_allocations)


def test_target_allocations_payload_storage_is_owner_scoped():
    store = MemoryPortfolioStore()
    payload_a = serialize_portfolio_payload([], usd_krw=1300, cash_krw=0, target_allocations=[{"asset_type": "cash", "currency": "KRW", "target_weight_pct": 100}])
    payload_b = serialize_portfolio_payload([], usd_krw=1300, cash_krw=0, target_allocations=[{"asset_type": "cash", "currency": "USD", "target_weight_pct": 100}])

    store.save_portfolio("user-a", "main", payload_a)
    store.save_portfolio("user-b", "main", payload_b)

    assert deserialize_portfolio_payload_v2(store.get_portfolio("user-a", "main").payload_json)["target_allocations"][0]["symbol"] == "CASH_KRW"
    assert deserialize_portfolio_payload_v2(store.get_portfolio("user-b", "main").payload_json)["target_allocations"][0]["symbol"] == "CASH_USD"


def test_target_weight_sum_edge_cases():
    assert not is_target_weight_sum_valid(0)
    assert is_target_weight_sum_valid(99.95)
    assert is_target_weight_sum_valid(100)
    assert not is_target_weight_sum_valid(120)
    rows = [
        {"asset_type": "stock", "symbol": "AAPL", "market": "US", "currency": "USD", "target_weight_pct": 60},
        {"asset_type": "cash", "currency": "KRW", "target_weight_pct": 60},
    ]
    assert target_weight_sum(rows) == pytest.approx(120)


def test_rebalancing_zero_asset_state_skips_result_table():
    assert rebalancing_empty_result_message(has_targets=False, total_asset_krw=0, total_target_pct=0)[0] == "목표 비중이 없습니다."
    assert rebalancing_empty_result_message(has_targets=True, total_asset_krw=0, total_target_pct=100)[0] == "총자산이 0원이라 계산할 수 없습니다."
    assert rebalancing_empty_result_message(has_targets=True, total_asset_krw=1_000_000, total_target_pct=0)[0] == "목표 비중을 입력하세요."
    assert rebalancing_empty_result_message(has_targets=True, total_asset_krw=1_000_000, total_target_pct=100) is None
