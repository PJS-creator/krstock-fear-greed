from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest

from portfolio.storage import MemoryPortfolioStore, PortfolioConflictError
from portfolio.storage.supabase_store import SupabasePortfolioStore, SupabaseStorageConfig


def test_only_one_writer_can_replace_a_loaded_version():
    store = MemoryPortfolioStore()
    initial = store.save_portfolio("owner", "main", {"writer": "initial"})
    barrier = Barrier(2)

    def save(writer):
        barrier.wait()
        try:
            return store.save_portfolio_if_unchanged(
                "owner", "main", {"writer": writer}, expected_updated_at=initial.updated_at,
            )
        except PortfolioConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ("desktop", "mobile")))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert store.get_portfolio("owner", "main").payload_json == winners[0].payload_json


@pytest.mark.parametrize("next_clock", ["2026-09-08T00:00:00+00:00", "2026-09-07T00:00:00+00:00"])
def test_memory_version_advances_when_clock_stalls_or_moves_back(monkeypatch, next_clock):
    monkeypatch.setattr("portfolio.storage.memory_store._utc_now_iso", lambda: "2026-09-08T00:00:00+00:00")
    store = MemoryPortfolioStore()
    initial = store.save_portfolio("owner", "main", {"value": 1})
    monkeypatch.setattr("portfolio.storage.memory_store._utc_now_iso", lambda: next_clock)
    saved = store.save_portfolio_if_unchanged(
        "owner", "main", {"value": 2}, expected_updated_at=initial.updated_at,
    )
    assert saved.updated_at > initial.updated_at
    with pytest.raises(PortfolioConflictError):
        store.save_portfolio_if_unchanged(
            "owner", "main", {"value": 3}, expected_updated_at=initial.updated_at,
        )


def test_new_account_insert_cannot_overwrite_existing_row():
    store = MemoryPortfolioStore()
    store.save_portfolio_if_unchanged("a", "main", {"value": 1}, expected_updated_at=None)
    with pytest.raises(PortfolioConflictError):
        store.save_portfolio_if_unchanged("a", "main", {"value": 2}, expected_updated_at=None)
    store.save_portfolio_if_unchanged("b", "main", {"value": 3}, expected_updated_at=None)
    assert store.get_portfolio("a", "main").payload_json == {"value": 1}


def test_supabase_update_filters_version_owner_and_name_without_upsert():
    class Query:
        def __init__(self):
            self.filters = {}
        def update(self, row):
            self.row = row
            return self
        def eq(self, key, value):
            self.filters[key] = value
            return self
        def execute(self):
            return SimpleNamespace(data=[])

    query = Query()
    config = SupabaseStorageConfig("https://example.supabase.co", None, "owner", publishable_key="public-test")
    store = SupabasePortfolioStore(config, client=SimpleNamespace(table=lambda _: query))
    with pytest.raises(PortfolioConflictError):
        store.save_portfolio_if_unchanged("owner", "main", {}, expected_updated_at="old-version")
    assert query.filters == {"owner_id": "owner", "portfolio_name": "main", "updated_at": "old-version"}
