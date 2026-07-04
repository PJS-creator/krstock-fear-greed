from __future__ import annotations

from portfolio.cash_ledger import calculate_cash_balances, create_cash_ledger_entries_for_trade, create_cash_movement_entry, serialize_cash_ledger_rows
from portfolio.rebalancing import default_target_allocations_from_portfolio
from portfolio.transactions import normalize_transaction_rows, transactions_to_holdings

import streamlit as st

from .data_portability import render_data_portability_tools
from .holdings import render_holdings_editor

SAMPLE_PORTFOLIO_ACTIVE_KEY = "sample_portfolio_active"
ONBOARDING_MODE_KEY = "onboarding_mode"


def _has_user_portfolio_data() -> bool:
    return bool(
        st.session_state.get("portfolio_transactions")
        or st.session_state.get("cash_ledger_entries")
        or st.session_state.get("holdings_rows")
        or st.session_state.get("target_allocations")
        or float(st.session_state.get("cash_krw") or 0.0)
        or float(st.session_state.get("cash_usd") or 0.0)
    )


def _sample_transactions() -> list[dict[str, object]]:
    return normalize_transaction_rows(
        [
            {
                "external_id": "sample-kr-005930",
                "transaction_type": "buy",
                "ticker": "005930",
                "market": "KR",
                "currency": "KRW",
                "display_name": "삼성전자",
                "unit_price": 70000,
                "quantity": 10,
                "fee": 1000,
                "tax": 0,
                "occurred_at": "2026-01-10",
                "note": "샘플 데이터",
            },
            {
                "external_id": "sample-us-aapl",
                "transaction_type": "buy",
                "ticker": "AAPL",
                "market": "US",
                "currency": "USD",
                "display_name": "Apple",
                "unit_price": 180,
                "quantity": 4,
                "fee": 1,
                "tax": 0,
                "occurred_at": "2026-01-12",
                "note": "샘플 데이터",
            },
            {
                "external_id": "sample-us-nvda",
                "transaction_type": "buy",
                "ticker": "NVDA",
                "market": "US",
                "currency": "USD",
                "display_name": "NVIDIA",
                "unit_price": 900,
                "quantity": 2,
                "fee": 1,
                "tax": 0,
                "occurred_at": "2026-01-12",
                "note": "샘플 데이터",
            },
        ]
    )


def _apply_sample_portfolio() -> None:
    transactions = _sample_transactions()
    holdings = transactions_to_holdings(transactions)
    sample_prices = {
        ("KR", "005930"): (78000, 77000),
        ("US", "AAPL"): (195, 192),
        ("US", "NVDA"): (980, 970),
    }
    priced_holdings = []
    for row in holdings:
        current_price, previous_close = sample_prices.get((str(row["market"]), str(row["ticker"])), (row.get("avg_price"), row.get("avg_price")))
        priced_holdings.append(
            {
                **row,
                "current_price": current_price,
                "previous_close": previous_close,
                "quote_status": "manual",
                "source": "sample",
                "provider": "sample",
                "note": "샘플 포트폴리오",
            }
        )
    krw_opening = create_cash_movement_entry(
        event_type="opening_balance",
        currency="KRW",
        amount=5_000_000,
        event_date="2026-01-01",
        memo="샘플 시작 원화 현금",
    )
    krw_opening["external_id"] = "sample-cash-krw"
    usd_opening = create_cash_movement_entry(
        event_type="opening_balance",
        currency="USD",
        amount=5_000,
        event_date="2026-01-01",
        memo="샘플 시작 달러 현금",
        fx_rate_to_krw=1380,
    )
    usd_opening["external_id"] = "sample-cash-usd"
    ledger_rows = [krw_opening, usd_opening]
    for transaction in transactions:
        ledger_rows.extend(create_cash_ledger_entries_for_trade(transaction, portfolio_id="main"))
    cash_ledger = serialize_cash_ledger_rows(ledger_rows)
    balances = calculate_cash_balances(cash_ledger)
    st.session_state.portfolio_transactions = transactions
    st.session_state.holdings_rows = priced_holdings
    st.session_state.cash_ledger_entries = cash_ledger
    st.session_state.cash_krw = float(balances["KRW"])
    st.session_state.cash_usd = float(balances["USD"])
    st.session_state.usd_krw = 1380.0
    st.session_state.target_allocations = default_target_allocations_from_portfolio(
        priced_holdings,
        cash_krw=st.session_state.cash_krw,
        cash_usd=st.session_state.cash_usd,
        usd_krw=st.session_state.usd_krw,
    )
    st.session_state[SAMPLE_PORTFOLIO_ACTIVE_KEY] = True
    st.session_state[ONBOARDING_MODE_KEY] = ""


def clear_sample_portfolio() -> None:
    for key, value in {
        "portfolio_transactions": [],
        "holdings_rows": [],
        "cash_ledger_entries": [],
        "target_allocations": [],
        "cash_krw": 0.0,
        "cash_usd": 0.0,
        "usd_krw": 1380.0,
        "price_update_statuses": [],
        SAMPLE_PORTFOLIO_ACTIVE_KEY: False,
        ONBOARDING_MODE_KEY: "",
    }.items():
        st.session_state[key] = value


def render_onboarding(*, portfolio_snapshot: dict[str, object]) -> None:
    sample_active = bool(st.session_state.get(SAMPLE_PORTFOLIO_ACTIVE_KEY))
    if sample_active:
        st.warning("샘플 포트폴리오로 둘러보는 중입니다. 이 데이터는 실제 투자 기록이 아니며 자동 저장하지 않습니다.")
        if st.button("샘플 데이터 삭제", type="secondary"):
            clear_sample_portfolio()
            st.rerun()
        return
    if _has_user_portfolio_data():
        return

    st.subheader("처음 시작하기")
    st.caption("처음 로그인한 사용자가 바로 포트폴리오를 만들 수 있도록 가장 쉬운 시작 방식을 선택하세요.")
    col1, col2, col3 = st.columns(3)
    if col1.button("샘플 포트폴리오로 둘러보기", use_container_width=True):
        _apply_sample_portfolio()
        st.rerun()
    if col2.button("현재 보유종목만 빠르게 입력", use_container_width=True):
        st.session_state[ONBOARDING_MODE_KEY] = "holdings"
        st.rerun()
    if col3.button("거래/현금 CSV 업로드", use_container_width=True):
        st.session_state[ONBOARDING_MODE_KEY] = "csv"
        st.rerun()

    mode = st.session_state.get(ONBOARDING_MODE_KEY)
    if mode == "holdings":
        render_holdings_editor()
    elif mode == "csv":
        render_data_portability_tools(portfolio_snapshot=portfolio_snapshot)
