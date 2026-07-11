from pathlib import Path
from types import SimpleNamespace

import app.portfolio_dashboard as dashboard
from portfolio.historical_holdings.storage import SupabaseHistoricalScheduleStore
from portfolio.history.models import PortfolioHistoryRecord
from portfolio.history.supabase_store import SupabasePortfolioHistoryStore
from portfolio.storage import SupabasePortfolioStore, SupabaseTargetAllocationStore, supabase_config_from_secrets


class _Response:
    def __init__(self, data):
        self.data = data


class _Table:
    def __init__(self):
        self.calls = []
        self.row = None

    def upsert(self, row, *, on_conflict):
        self.calls.append(("upsert", on_conflict))
        self.row = dict(row)
        return self

    def execute(self):
        self.calls.append(("execute", None))
        return _Response([{**(self.row or {}), "created_at": "2026-07-11T00:00:00+00:00"}])


class _Client:
    def __init__(self):
        self.table_instance = _Table()

    def table(self, name):
        self.table_instance.calls.append(("table", name))
        return self.table_instance


def _config():
    return supabase_config_from_secrets(
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable",
            "PORTFOLIO_OWNER_ID": "owner-a",
        }
    )


def test_supabase_stores_can_share_one_authenticated_client():
    client = _Client()
    config = _config()

    stores = [
        SupabasePortfolioStore(config, client=client),
        SupabasePortfolioHistoryStore(config, client=client),
        SupabaseHistoricalScheduleStore(config, client=client),
        SupabaseTargetAllocationStore(config, client=client),
    ]

    assert all(store._client is client for store in stores)


def test_supabase_store_bundle_is_reused_per_streamlit_session(monkeypatch):
    config = _config().with_auth_session(
        owner_id="owner-a",
        access_token="access-a",
        refresh_token="refresh-a",
    )
    clients = []

    def create_client(_config):
        client = object()
        clients.append(client)
        return client

    fake_st = SimpleNamespace(
        session_state={},
        sidebar=SimpleNamespace(warning=lambda _message: None),
    )
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "create_supabase_client", create_client)
    monkeypatch.setattr(dashboard, "build_supabase_store", lambda _config, *, client: ("portfolio", client))
    monkeypatch.setattr(dashboard, "build_supabase_history_store", lambda _config, *, client: ("history", client))
    monkeypatch.setattr(
        dashboard,
        "build_supabase_historical_schedule_store",
        lambda _config, *, client: ("schedule", client),
    )
    monkeypatch.setattr(dashboard, "build_target_allocation_store", lambda _config, *, client: ("targets", client))

    first = dashboard._build_stores(config)
    second = dashboard._build_stores(config)
    fake_st.session_state = {}
    third = dashboard._build_stores(config)

    assert first is second
    assert third is not first
    assert len(clients) == 2


def test_public_auth_store_is_not_shared_between_streamlit_sessions(monkeypatch):
    created = []

    class FakeAuthStore:
        def __init__(self, config):
            self.config = config
            created.append(self)

    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(dashboard, "SupabaseAuthStore", FakeAuthStore)

    first = dashboard._build_public_auth_store(_config())
    second = dashboard._build_public_auth_store(_config())
    fake_st.session_state = {}
    third = dashboard._build_public_auth_store(_config())

    assert first is second
    assert third is not first
    assert len(created) == 2


def test_portfolio_save_uses_one_upsert_without_preload():
    client = _Client()
    store = SupabasePortfolioStore(_config(), client=client)

    saved = store.save_portfolio("owner-a", "main", {"schema_version": 6})

    assert saved.portfolio_name == "main"
    assert client.table_instance.calls == [
        ("table", "portfolio_snapshots"),
        ("upsert", "owner_id,portfolio_name"),
        ("execute", None),
    ]


def test_history_save_uses_atomic_fingerprint_upsert():
    client = _Client()
    store = SupabasePortfolioHistoryStore(_config(), client=client)
    record = PortfolioHistoryRecord(
        owner_id="owner-a",
        portfolio_name="main",
        captured_at="2026-07-11T00:00:00+00:00",
        event_type="portfolio_save",
        total_value_krw=100.0,
        total_position_value_krw=80.0,
        cash_krw=20.0,
        cash_usd=0.0,
        cash_total_krw=20.0,
        usd_krw=1380.0,
        day_change_krw=1.0,
        day_change_pct=0.01,
        holdings_count=1,
        stale_quote_count=0,
        payload_json={},
        fingerprint="fingerprint-a",
    )

    saved = store.save_snapshot(record)

    assert saved.fingerprint == "fingerprint-a"
    assert client.table_instance.calls == [
        ("table", "portfolio_value_history"),
        ("upsert", "owner_id,portfolio_name,fingerprint"),
        ("execute", None),
    ]


def test_expensive_subviews_are_lazy_and_global_cache_flush_is_removed():
    app_source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")
    history_source = Path("app/ui/history.py").read_text(encoding="utf-8")
    portability_source = Path("app/ui/data_portability.py").read_text(encoding="utf-8")
    app_tree = "\n".join(path.read_text(encoding="utf-8") for path in Path("app").rglob("*.py"))

    assert "st.cache_data.clear()" not in app_tree
    assert 'key=HISTORY_VIEW_KEY' in history_source
    assert 'if selected_view == "actual"' in history_source
    assert 'key="data_portability_view"' in portability_source
    assert 'include_intraday=False' in app_source
    assert "PRICE_REFRESH_BUDGET_SECONDS = 24.0" in app_source
