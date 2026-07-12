from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import portfolio_dashboard as dashboard
from app.ui import manage
from portfolio.history import MemoryPortfolioHistoryStore, build_history_record
from portfolio.holdings import build_portfolio_metrics
from portfolio.storage import MemoryPortfolioStore, PortfolioStoreError, serialize_portfolio_payload


class SessionState(dict):
    __setattr__ = dict.__setitem__

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class FlakyLoadStore(MemoryPortfolioStore):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0
        self.save_calls = 0

    def get_portfolio(self, owner_id: str, portfolio_name: str):
        self.get_calls += 1
        if self.get_calls == 1:
            raise PortfolioStoreError("temporary load failure")
        return super().get_portfolio(owner_id, portfolio_name)

    def save_portfolio(self, owner_id: str, portfolio_name: str, payload_json):
        self.save_calls += 1
        return super().save_portfolio(owner_id, portfolio_name, payload_json)


class UnverifiableStore(MemoryPortfolioStore):
    def get_portfolio(self, owner_id: str, portfolio_name: str):
        return None


def _holding(ticker: str = "005930") -> dict[str, object]:
    is_korea = ticker.isdigit()
    return {
        "ticker": ticker,
        "display_name": "삼성전자" if ticker == "005930" else ticker,
        "market": "KR" if is_korea else "US",
        "currency": "KRW" if is_korea else "USD",
        "quantity": 10,
        "avg_price": 70_000,
        "current_price": 75_000,
        "previous_close": 74_000,
    }


def _payload(*, ticker: str = "005930") -> dict[str, object]:
    return serialize_portfolio_payload(
        [_holding(ticker)],
        usd_krw=1_350,
        cash_krw=1_000_000,
        cash_usd=100,
    )


def _state() -> SessionState:
    return SessionState(
        is_authenticated=True,
        portfolio_name="main",
        portfolio_name_input="main",
        portfolio_transactions=[],
        cash_ledger_entries=[],
        target_allocations=[],
        journal_notes=[],
        holdings_rows=[],
        cash_krw=0.0,
        cash_usd=0.0,
        usd_krw=1_350.0,
        fx_rate_date=None,
        fx_as_of_timestamp=None,
        fx_source="manual",
        fx_status="manual",
        fx_error_message=None,
    )


def _install_streamlit(monkeypatch, state: SessionState) -> None:
    fake = SimpleNamespace(session_state=state)
    monkeypatch.setattr(dashboard, "st", fake)
    monkeypatch.setattr(manage, "st", fake)
    dashboard._mark_portfolio_clean()


def test_transient_load_failure_retries_and_blocks_remote_overwrite(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    store = FlakyLoadStore()
    store.save_portfolio("owner-a", "main", _payload())
    store.save_calls = 0

    dashboard._auto_load_account_portfolio("owner-a", store, now=100.0)
    state.holdings_rows = [_holding("MSFT")]
    metrics = dashboard._current_metrics()
    dashboard._auto_save_public_portfolio("owner-a", store, None, None, metrics)

    assert store.save_calls == 0
    assert state[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "error"
    assert "덮어쓰기를 차단" in state[dashboard.PUBLIC_SAVE_STATUS_KEY]

    dashboard._auto_load_account_portfolio("owner-a", store, now=106.0)

    assert store.get_calls == 2
    assert state.holdings_rows[0]["ticker"] == "005930"
    assert state.cash_krw == 1_000_000
    assert state[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "loaded"


def test_legacy_attempt_marker_without_load_state_does_not_skip_hydration(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    state[dashboard.AUTO_LOAD_ATTEMPTED_KEY] = "owner-a:main"
    store = MemoryPortfolioStore()
    store.save_portfolio("owner-a", "main", _payload())

    dashboard._auto_load_account_portfolio("owner-a", store, now=100.0)

    assert state.holdings_rows[0]["ticker"] == "005930"
    assert state[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "loaded"


def test_login_and_logout_clear_load_state_so_next_account_session_reloads(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    state[dashboard.PORTFOLIO_LOAD_STATE_KEY] = {
        "key": "owner-a:main",
        "status": "loaded",
        "attempted_at": 100.0,
    }

    dashboard._authenticate_account(
        dashboard.AccountConfig(
            account_id="user@example.com",
            password="",
            owner_id="owner-a",
            default_portfolio="main",
        )
    )

    assert dashboard.PORTFOLIO_LOAD_STATE_KEY not in state

    state[dashboard.PORTFOLIO_LOAD_STATE_KEY] = {
        "key": "owner-a:main",
        "status": "loaded",
        "attempted_at": 100.0,
    }
    monkeypatch.setattr(dashboard, "delete_remember_cookie", lambda _manager: None)
    dashboard._logout(None)

    assert dashboard.PORTFOLIO_LOAD_STATE_KEY not in state


def test_missing_snapshot_recovers_account_data_from_history_and_persists_it(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    store = MemoryPortfolioStore()
    history_store = MemoryPortfolioHistoryStore()
    metrics = build_portfolio_metrics([_holding()], cash_krw=1_000_000, cash_usd=100, usd_krw=1_350)
    history_store.save_snapshot(
        build_history_record(
            owner_id="owner-a",
            portfolio_name="main",
            event_type="portfolio_save",
            metrics=metrics,
        )
    )

    dashboard._auto_load_account_portfolio(
        "owner-a", store, history_store=history_store, now=100.0
    )

    assert state.holdings_rows[0]["ticker"] == "005930"
    assert state.cash_krw == 1_000_000
    assert state[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "recovered"
    assert dashboard._portfolio_is_dirty()

    dashboard._auto_save_public_portfolio(
        "owner-a", store, None, history_store, dashboard._current_metrics()
    )

    persisted = store.get_portfolio("owner-a", "main")
    assert persisted is not None
    assert persisted.payload_json["holdings"][0]["ticker"] == "005930"
    assert state[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "loaded"
    assert state[dashboard.PUBLIC_SAVE_STATUS_KEY] == "저장됨"


def test_saved_account_portfolio_survives_a_fresh_session(monkeypatch):
    store = MemoryPortfolioStore()
    first_session = _state()
    _install_streamlit(monkeypatch, first_session)
    dashboard._set_portfolio_load_state("owner-a", "main", "missing", attempted_at=100.0)
    first_session.holdings_rows = [_holding()]
    first_session.cash_krw = 1_000_000.0
    first_session.cash_usd = 100.0

    dashboard._auto_save_public_portfolio(
        "owner-a", store, None, None, dashboard._current_metrics()
    )

    assert store.get_portfolio("owner-a", "main") is not None
    assert first_session[dashboard.PUBLIC_SAVE_STATUS_KEY] == "저장됨"

    fresh_session = _state()
    _install_streamlit(monkeypatch, fresh_session)
    dashboard._auto_load_account_portfolio("owner-a", store, now=200.0)

    assert fresh_session.holdings_rows[0]["ticker"] == "005930"
    assert fresh_session.cash_krw == 1_000_000.0
    assert fresh_session.cash_usd == 100.0
    assert fresh_session[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "loaded"


def test_security_metadata_enrichment_updates_loaded_holdings(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    state.holdings_rows = [_holding("AAPL")]
    provider = object()
    monkeypatch.setattr(dashboard, "build_yfinance_security_metadata_provider", lambda: provider)

    def enrich(rows, selected_provider):
        assert selected_provider is provider
        enriched = [dict(row) for row in rows]
        enriched[0].update(
            {
                "sector": "정보기술",
                "metadata_source": "yfinance",
                "metadata_fetched_at": "2026-07-11T00:00:00+00:00",
            }
        )
        return enriched

    monkeypatch.setattr(dashboard, "enrich_holding_metadata", enrich)

    dashboard._enrich_security_metadata_if_needed()

    assert state.holdings_rows[0]["sector"] == "정보기술"
    assert state.holdings_rows[0]["metadata_source"] == "yfinance"


def test_save_is_not_marked_clean_when_read_after_write_cannot_verify(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    state.holdings_rows = [_holding()]
    store = UnverifiableStore()

    with pytest.raises(PortfolioStoreError, match="확인"):
        dashboard._persist_current_portfolio("owner-a", store)

    assert dashboard._portfolio_is_dirty()


def test_owner_never_loads_another_users_snapshot_or_history(monkeypatch):
    state = _state()
    _install_streamlit(monkeypatch, state)
    store = MemoryPortfolioStore()
    store.save_portfolio("owner-b", "main", _payload(ticker="AAPL"))
    history_store = MemoryPortfolioHistoryStore()
    metrics = build_portfolio_metrics([_holding("AAPL")], cash_krw=5_000, cash_usd=0, usd_krw=1_350)
    history_store.save_snapshot(
        build_history_record(
            owner_id="owner-b",
            portfolio_name="main",
            event_type="portfolio_save",
            metrics=metrics,
        )
    )

    dashboard._auto_load_account_portfolio(
        "owner-a", store, history_store=history_store, now=100.0
    )

    assert state.holdings_rows == []
    assert state.cash_krw == 0
    assert state[dashboard.PORTFOLIO_LOAD_STATE_KEY]["status"] == "missing"
