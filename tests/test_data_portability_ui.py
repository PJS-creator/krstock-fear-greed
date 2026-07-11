from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.ui import data_portability
from portfolio.holdings import build_portfolio_metrics


class SessionState(dict):
    __setattr__ = dict.__setitem__

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _install_fake_streamlit(monkeypatch, state: SessionState) -> None:
    fake_streamlit = SimpleNamespace(session_state=state, toast=lambda _message: None)
    monkeypatch.setattr(data_portability, "st", fake_streamlit)
    monkeypatch.setattr(data_portability, "request_app_rerun", lambda: None)


def _buy_row(*, ticker: str = "QURE", market: str = "US", currency: str = "USD") -> dict[str, object]:
    return {
        "transaction_type": "buy",
        "ticker": ticker,
        "market": market,
        "currency": currency,
        "display_name": ticker,
        "unit_price": 41,
        "quantity": 10,
        "fee": 0,
        "tax": 0,
        "occurred_at": "2026-04-13",
    }


def test_transaction_import_rejects_insufficient_cash_without_partial_state(monkeypatch):
    state = SessionState(
        portfolio_name="main",
        portfolio_transactions=[],
        holdings_rows=[],
        cash_ledger_entries=[],
        cash_krw=0.0,
        cash_usd=100.0,
        allow_negative_cash_balance=False,
    )
    original = deepcopy(state)
    _install_fake_streamlit(monkeypatch, state)

    with pytest.raises(ValueError, match="USD 현금 잔고가 부족"):
        data_portability._apply_transaction_import([_buy_row()])

    assert state == original


def test_transaction_import_can_commit_negative_cash_when_explicitly_allowed(monkeypatch):
    state = SessionState(
        portfolio_name="main",
        portfolio_transactions=[],
        holdings_rows=[],
        cash_ledger_entries=[],
        cash_krw=0.0,
        cash_usd=100.0,
        allow_negative_cash_balance=True,
    )
    _install_fake_streamlit(monkeypatch, state)

    data_portability._apply_transaction_import([_buy_row()])

    assert state.cash_usd == -310.0
    assert len(state.portfolio_transactions) == 1
    assert {row["event_type"] for row in state.cash_ledger_entries} == {"opening_balance", "buy_settlement"}
    metrics = build_portfolio_metrics(state.holdings_rows, cash_krw=state.cash_krw, cash_usd=state.cash_usd, usd_krw=1300)
    assert metrics.cash.cash_usd == -310.0


def test_cash_import_rejects_negative_balance_without_partial_state(monkeypatch):
    state = SessionState(
        portfolio_name="main",
        portfolio_transactions=[],
        holdings_rows=[],
        cash_ledger_entries=[
            {"event_date": "2026-04-01", "currency": "KRW", "event_type": "deposit", "amount": "100"}
        ],
        cash_krw=100.0,
        cash_usd=0.0,
        allow_negative_cash_balance=False,
    )
    original = deepcopy(state)
    _install_fake_streamlit(monkeypatch, state)

    with pytest.raises(ValueError, match="KRW 현금 잔고가 부족"):
        data_portability._apply_cash_import(
            [{"event_date": "2026-04-02", "currency": "KRW", "event_type": "withdrawal", "amount": "-200"}]
        )

    assert state == original
