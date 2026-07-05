from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from portfolio.cash_ledger import calculate_cash_balances, create_cash_ledger_entries_for_trade, serialize_cash_ledger_rows
from portfolio.data_portability import (
    CASH_LEDGER_IMPORT_COLUMNS,
    TRANSACTION_IMPORT_COLUMNS,
    build_full_export_payload,
    csv_to_rows,
    preview_cash_ledger_import,
    preview_transaction_import,
    rows_to_csv,
)
from portfolio.rebalancing import serialize_target_allocations
from portfolio.symbols import load_korea_listing_records
from portfolio.transactions import normalize_transaction_rows, rows_to_csv as transaction_rows_to_csv, transactions_to_holdings

from .stability import begin_ui_action, finish_ui_action, request_app_rerun
from .theme import DIMENSIONS

TRANSACTION_IMPORT_PREVIEW_KEY = "transaction_import_preview_valid_rows"
CASH_IMPORT_PREVIEW_KEY = "cash_import_preview_valid_rows"


@st.cache_data(show_spinner=False)
def _cached_korea_listing_records() -> list[dict[str, str]]:
    try:
        import FinanceDataReader as fdr

        return load_korea_listing_records(fdr.StockListing)
    except Exception:
        return []


def _preview_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _issues_frame(issues) -> pd.DataFrame:
    return pd.DataFrame(
        [{"행": issue.row_number, "수준": "오류" if issue.level == "error" else "중복", "이유": issue.message} for issue in issues]
    )


def _update_cash_balances_from_ledger() -> None:
    balances = calculate_cash_balances(st.session_state.get("cash_ledger_entries", []))
    st.session_state.cash_krw = float(balances["KRW"])
    st.session_state.cash_usd = float(balances["USD"])


def _apply_transaction_import(rows: list[dict[str, object]]) -> None:
    existing = normalize_transaction_rows(st.session_state.get("portfolio_transactions", []))
    imported = normalize_transaction_rows(rows)
    combined = existing + imported
    st.session_state.portfolio_transactions = normalize_transaction_rows(combined)
    st.session_state.holdings_rows = transactions_to_holdings(
        st.session_state.portfolio_transactions,
        previous_holdings=st.session_state.get("holdings_rows", []),
    )
    ledger_additions = []
    for transaction in imported:
        ledger_additions.extend(
            create_cash_ledger_entries_for_trade(
                transaction,
                portfolio_id=str(st.session_state.get("portfolio_name") or "main"),
            )
        )
    st.session_state.cash_ledger_entries = serialize_cash_ledger_rows(list(st.session_state.get("cash_ledger_entries") or []) + ledger_additions)
    _update_cash_balances_from_ledger()
    st.session_state.pop(TRANSACTION_IMPORT_PREVIEW_KEY, None)
    st.toast("거래 CSV를 반영했습니다.")
    request_app_rerun()


def _apply_cash_import(rows: list[dict[str, object]]) -> None:
    st.session_state.cash_ledger_entries = serialize_cash_ledger_rows(list(st.session_state.get("cash_ledger_entries") or []) + rows)
    _update_cash_balances_from_ledger()
    st.session_state.pop(CASH_IMPORT_PREVIEW_KEY, None)
    st.toast("현금 원장 CSV를 반영했습니다.")
    request_app_rerun()


def _render_transaction_import() -> None:
    st.subheader("거래 CSV")
    st.download_button(
        "거래 CSV 템플릿 다운로드",
        data=rows_to_csv(
            [
                {
                    "external_id": "sample-buy-001",
                    "transaction_type": "매입",
                    "ticker_or_name": "삼성전자",
                    "unit_price": "72300",
                    "quantity": "10",
                    "fee": "1000",
                    "tax": "0",
                    "occurred_at": date.today().isoformat(),
                    "note": "예시 매입",
                }
            ],
            TRANSACTION_IMPORT_COLUMNS,
        ).encode("utf-8-sig"),
        file_name="transactions_template.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("거래 CSV 업로드", type=["csv"], key="portable_transaction_csv")
    if uploaded is not None and st.button("거래 CSV 검증", type="primary"):
        preview = preview_transaction_import(
            csv_to_rows(uploaded.getvalue()),
            existing_transactions=st.session_state.get("portfolio_transactions", []),
            korea_listing_records=_cached_korea_listing_records(),
        )
        st.session_state[TRANSACTION_IMPORT_PREVIEW_KEY] = preview.valid_rows
        st.session_state["transaction_import_preview_display"] = preview.rows
        st.session_state["transaction_import_preview_issues"] = preview.issues
    rows = list(st.session_state.get("transaction_import_preview_display", []))
    issues = list(st.session_state.get("transaction_import_preview_issues", []))
    valid_rows = list(st.session_state.get(TRANSACTION_IMPORT_PREVIEW_KEY, []))
    if rows:
        st.caption(f"미리보기: 저장 가능 {len(valid_rows)}행 · 오류/중복 {len(issues)}행")
        st.dataframe(_preview_frame(rows), hide_index=True, width="stretch", height=min(DIMENSIONS.max_table_height, 100 + len(rows) * DIMENSIONS.row_height))
    if issues:
        st.warning("오류 또는 중복 행은 저장하지 않습니다.")
        st.dataframe(_issues_frame(issues), hide_index=True, width="stretch")
    if rows and st.button("저장 가능한 거래만 가져오기", disabled=not valid_rows):
        if begin_ui_action("import_transactions_csv", payload=valid_rows):
            try:
                _apply_transaction_import(valid_rows)
            except Exception:
                finish_ui_action(success=False)
                raise


def _render_cash_import() -> None:
    st.subheader("현금 원장 CSV")
    st.download_button(
        "현금 원장 CSV 템플릿 다운로드",
        data=rows_to_csv(
            [
                {
                    "external_id": "sample-deposit-001",
                    "event_date": date.today().isoformat(),
                    "currency": "KRW",
                    "event_type": "deposit",
                    "amount": "1000000",
                    "fx_rate_to_krw": "",
                    "memo": "예시 입금",
                },
                {
                    "external_id": "sample-usd-001",
                    "event_date": date.today().isoformat(),
                    "currency": "USD",
                    "event_type": "deposit",
                    "amount": "1000",
                    "fx_rate_to_krw": "1380",
                    "memo": "예시 달러 입금",
                },
            ],
            CASH_LEDGER_IMPORT_COLUMNS,
        ).encode("utf-8-sig"),
        file_name="cash_ledger_template.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("현금 원장 CSV 업로드", type=["csv"], key="portable_cash_csv")
    if uploaded is not None and st.button("현금 원장 CSV 검증", type="primary"):
        preview = preview_cash_ledger_import(
            csv_to_rows(uploaded.getvalue()),
            existing_cash_ledger=st.session_state.get("cash_ledger_entries", []),
        )
        st.session_state[CASH_IMPORT_PREVIEW_KEY] = preview.valid_rows
        st.session_state["cash_import_preview_display"] = preview.rows
        st.session_state["cash_import_preview_issues"] = preview.issues
    rows = list(st.session_state.get("cash_import_preview_display", []))
    issues = list(st.session_state.get("cash_import_preview_issues", []))
    valid_rows = list(st.session_state.get(CASH_IMPORT_PREVIEW_KEY, []))
    if rows:
        st.caption(f"미리보기: 저장 가능 {len(valid_rows)}행 · 오류/중복 {len(issues)}행")
        st.dataframe(_preview_frame(rows), hide_index=True, width="stretch", height=min(DIMENSIONS.max_table_height, 100 + len(rows) * DIMENSIONS.row_height))
    if issues:
        st.warning("오류 또는 중복 행은 저장하지 않습니다.")
        st.dataframe(_issues_frame(issues), hide_index=True, width="stretch")
    if rows and st.button("저장 가능한 원장만 가져오기", disabled=not valid_rows):
        if begin_ui_action("import_cash_ledger_csv", payload=valid_rows):
            try:
                _apply_cash_import(valid_rows)
            except Exception:
                finish_ui_action(success=False)
                raise


def _render_exports(portfolio_snapshot: dict[str, object]) -> None:
    st.subheader("내보내기")
    transactions = normalize_transaction_rows(st.session_state.get("portfolio_transactions", []))
    cash_ledger = serialize_cash_ledger_rows(st.session_state.get("cash_ledger_entries", []))
    target_allocations = serialize_target_allocations(st.session_state.get("target_allocations", []))
    full_payload = build_full_export_payload(
        holdings=st.session_state.get("holdings_rows", []),
        transactions=transactions,
        cash_ledger=cash_ledger,
        target_allocations=target_allocations,
        portfolio_snapshot=portfolio_snapshot,
    )
    col1, col2, col3 = st.columns(3, gap="small")
    col1.download_button(
        "전체 데이터 JSON 내보내기",
        data=json.dumps(full_payload, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
        file_name="portfolio_full_export.json",
        mime="application/json",
    )
    col2.download_button(
        "거래 CSV 내보내기",
        data=transaction_rows_to_csv(transactions, TRANSACTION_IMPORT_COLUMNS).encode("utf-8-sig"),
        file_name="transactions_export.csv",
        mime="text/csv",
        disabled=not transactions,
    )
    col3.download_button(
        "현금 원장 CSV 내보내기",
        data=rows_to_csv(cash_ledger, CASH_LEDGER_IMPORT_COLUMNS).encode("utf-8-sig"),
        file_name="cash_ledger_export.csv",
        mime="text/csv",
        disabled=not cash_ledger,
    )
    if target_allocations:
        st.download_button(
            "목표 비중 CSV 내보내기",
            data=pd.DataFrame(target_allocations).to_csv(index=False).encode("utf-8-sig"),
            file_name="target_allocations_export.csv",
            mime="text/csv",
        )


def render_data_portability_tools(*, portfolio_snapshot: dict[str, object]) -> None:
    st.subheader("CSV 가져오기/내보내기")
    st.caption("저장 전 미리보기와 검증을 거칩니다. 오류 또는 중복으로 표시된 행은 저장하지 않습니다.")
    import_tab, export_tab = st.tabs(["가져오기", "내보내기"])
    with import_tab:
        _render_transaction_import()
        _render_cash_import()
    with export_tab:
        _render_exports(portfolio_snapshot)
