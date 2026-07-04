from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st

from portfolio.cash_ledger import calculate_cash_balances
from portfolio.history import PortfolioHistoryStore, build_history_record
from portfolio.holdings import HOLDING_COLUMNS, PortfolioMetrics, normalize_holding_rows
from portfolio.storage import (
    PortfolioRecord,
    PortfolioStore,
    PortfolioStoreError,
    TargetAllocationStore,
    deserialize_portfolio_payload_v2,
    load_target_allocations_prefer_table,
    save_target_allocations_if_available,
    serialize_portfolio_payload,
)
from portfolio.transactions import TRANSACTION_COLUMNS, normalize_transaction_rows, rows_to_csv as transaction_rows_to_csv
from .formatters import format_kst
from .stability import begin_ui_action, finish_ui_action, request_app_rerun

STORAGE_UNCONFIGURED_MESSAGE = "저장소가 설정되지 않아 CSV 방식만 사용할 수 있습니다"
PENDING_PORTFOLIO_NAME_KEY = "pending_portfolio_name"
PENDING_PORTFOLIO_STATE_KEY = "pending_portfolio_state"
STORAGE_STATUS_MESSAGE_KEY = "storage_status_message"


def _holdings_csv(rows: list[dict[str, object]]) -> str:
    frame = pd.DataFrame(normalize_holding_rows(rows), columns=HOLDING_COLUMNS)
    return frame.to_csv(index=False)


def _queue_portfolio_name_update(portfolio_name: str) -> None:
    st.session_state[PENDING_PORTFOLIO_NAME_KEY] = portfolio_name


def _queue_portfolio_state_update(**values: object) -> None:
    pending_state = st.session_state.get(PENDING_PORTFOLIO_STATE_KEY)
    if not isinstance(pending_state, dict):
        pending_state = {}
    pending_state.update(values)
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = pending_state


def _set_storage_status(message: str) -> None:
    st.session_state[STORAGE_STATUS_MESSAGE_KEY] = message


@st.cache_data(ttl=60, show_spinner=False)
def list_portfolios_cached(_store: PortfolioStore, owner_id: str) -> list[PortfolioRecord]:
    return _store.list_portfolios(owner_id)


def queue_portfolio_record_load(
    record: PortfolioRecord,
    *,
    target_allocation_store: TargetAllocationStore | None = None,
) -> None:
    payload = deserialize_portfolio_payload_v2(record.payload_json)
    cash = payload["cash_balances"]
    cash_ledger = list(payload.get("cash_ledger", []))
    fx_metadata = payload.get("fx_metadata") if isinstance(payload.get("fx_metadata"), dict) else {}
    target_allocations = load_target_allocations_prefer_table(
        target_allocation_store,
        record.owner_id,
        record.portfolio_name,
        payload.get("target_allocations", []),
    )
    if cash_ledger:
        ledger_balances = calculate_cash_balances(cash_ledger)
        cash_krw = float(ledger_balances["KRW"])
        cash_usd = float(ledger_balances["USD"])
    else:
        cash_krw = float(cash.get("KRW", 0.0))
        cash_usd = float(cash.get("USD", 0.0))
    _queue_portfolio_state_update(
        portfolio_name=record.portfolio_name,
        portfolio_transactions=payload.get("transactions", []),
        cash_ledger_entries=cash_ledger,
        target_allocations=target_allocations,
        holdings_rows=payload["holdings"],
        usd_krw=float(payload["usd_krw"]),
        cash_krw=cash_krw,
        cash_usd=cash_usd,
        fx_rate_date=fx_metadata.get("rate_date"),
        fx_as_of_timestamp=fx_metadata.get("as_of_timestamp"),
        fx_source=fx_metadata.get("source"),
        fx_status=fx_metadata.get("status"),
        fx_error_message=fx_metadata.get("error_message"),
        fx_fetched_at=fx_metadata.get("fetched_at"),
    )
    _set_storage_status(f"{record.portfolio_name} 포트폴리오를 불러왔습니다.")


def render_csv_tools() -> None:
    st.subheader("CSV")
    st.caption("자산 입력은 보유현황 CSV가 아니라 사용자 입력 탭의 매입/매도 거래 CSV로 일원화했습니다.")
    transactions = normalize_transaction_rows(st.session_state.get("portfolio_transactions", []))
    st.download_button(
        "거래내역 CSV 다운로드",
        data=transaction_rows_to_csv(transactions, TRANSACTION_COLUMNS).encode("utf-8-sig"),
        file_name="portfolio_transactions.csv",
        mime="text/csv",
        disabled=not transactions,
    )
    st.download_button(
        "계산된 현재 보유현황 CSV 다운로드",
        data=_holdings_csv(st.session_state.get("holdings_rows", [])),
        file_name="portfolio_v2.csv",
        mime="text/csv",
        disabled=not st.session_state.get("holdings_rows"),
    )


def render_storage_tools(
    *,
    owner_id: str | None,
    store: PortfolioStore | None,
    history_store: PortfolioHistoryStore | None,
    metrics: PortfolioMetrics,
    target_allocation_store: TargetAllocationStore | None = None,
    on_capture: Callable[[str], None] | None = None,
) -> None:
    st.subheader("포트폴리오 저장/불러오기")
    status_message = st.session_state.pop(STORAGE_STATUS_MESSAGE_KEY, None)
    if status_message:
        st.success(status_message)
    if store is None or owner_id is None:
        st.info(STORAGE_UNCONFIGURED_MESSAGE)
        return

    with st.form("portfolio_save_form"):
        portfolio_name = st.text_input("포트폴리오 이름", value=st.session_state.get("portfolio_name", "main"))
        submitted = st.form_submit_button("현재 포트폴리오 저장")
    if submitted:
        clean_name = str(portfolio_name or "").strip()
        if not clean_name:
            st.error("포트폴리오 이름을 입력하세요.")
        else:
            if not begin_ui_action("storage_save_portfolio", payload={"portfolio_name": clean_name}):
                return
            try:
                payload = serialize_portfolio_payload(
                    st.session_state.get("holdings_rows", []),
                    usd_krw=st.session_state.get("usd_krw", 1380.0),
                    cash_krw=st.session_state.get("cash_krw", 0.0),
                    cash_usd=st.session_state.get("cash_usd", 0.0),
                    transactions=st.session_state.get("portfolio_transactions", []),
                    cash_ledger=st.session_state.get("cash_ledger_entries", []),
                    target_allocations=st.session_state.get("target_allocations", []),
                    fx_metadata={
                        "rate_date": st.session_state.get("fx_rate_date"),
                        "as_of_timestamp": st.session_state.get("fx_as_of_timestamp"),
                        "source": st.session_state.get("fx_source"),
                        "status": st.session_state.get("fx_status"),
                        "error_message": st.session_state.get("fx_error_message"),
                        "fetched_at": st.session_state.get("fx_fetched_at"),
                    },
                )
                store.save_portfolio(owner_id, clean_name, payload)
                save_target_allocations_if_available(
                    target_allocation_store,
                    owner_id,
                    clean_name,
                    st.session_state.get("target_allocations", []),
                )
                if history_store is not None:
                    history_store.save_snapshot(
                        build_history_record(
                            owner_id=owner_id,
                            portfolio_name=clean_name,
                            event_type="portfolio_save",
                            metrics=metrics,
                        )
                    )
                if on_capture is not None:
                    on_capture("portfolio_save")
                st.cache_data.clear()
                _queue_portfolio_name_update(clean_name)
                _set_storage_status(f"{clean_name} 포트폴리오를 저장했습니다.")
                request_app_rerun()
            except (PortfolioStoreError, ValueError) as exc:
                finish_ui_action(success=False)
                st.error(f"포트폴리오를 저장할 수 없습니다: {exc}")

    try:
        records = list_portfolios_cached(store, owner_id)
    except PortfolioStoreError as exc:
        st.warning(f"저장 목록을 불러올 수 없습니다: {exc}")
        records = []
    if not records:
        st.info("저장된 포트폴리오가 없습니다.")
        return

    labels = {f"{record.portfolio_name} · {format_kst(record.updated_at or record.created_at, compact=True)}": record for record in records}
    selected_label = st.selectbox("저장된 포트폴리오", list(labels.keys()))
    selected = labels[selected_label]
    col1, col2 = st.columns(2)
    confirm_load = st.checkbox("현재 입력을 선택 포트폴리오로 교체 확인", key=f"load_{selected.portfolio_name}")
    if col1.button("선택 포트폴리오 불러오기", disabled=not confirm_load):
        if not begin_ui_action("storage_load_portfolio", payload={"portfolio_name": selected.portfolio_name}):
            return
        try:
            queue_portfolio_record_load(selected, target_allocation_store=target_allocation_store)
            request_app_rerun()
        except (PortfolioStoreError, ValueError) as exc:
            finish_ui_action(success=False)
            st.error(f"포트폴리오를 불러올 수 없습니다: {exc}")

    with st.expander("포트폴리오 이름 변경", expanded=False):
        new_name = st.text_input("새 이름", value=selected.portfolio_name, key=f"rename_{selected.portfolio_name}")
        confirm_rename = st.checkbox("선택한 포트폴리오 이름 변경 확인", key=f"confirm_rename_{selected.portfolio_name}")
        if st.button("이름 변경", disabled=not confirm_rename):
            clean_name = str(new_name or "").strip()
            if not clean_name:
                st.error("새 이름을 입력하세요.")
            else:
                if not begin_ui_action("storage_rename_portfolio", payload={"from": selected.portfolio_name, "to": clean_name}):
                    return
                try:
                    store.save_portfolio(owner_id, clean_name, selected.payload_json)
                    if clean_name != selected.portfolio_name:
                        store.delete_portfolio(owner_id, selected.portfolio_name)
                    st.cache_data.clear()
                    _queue_portfolio_name_update(clean_name)
                    _set_storage_status(f"{selected.portfolio_name} → {clean_name} 이름을 변경했습니다.")
                    request_app_rerun()
                except PortfolioStoreError as exc:
                    finish_ui_action(success=False)
                    st.error(f"포트폴리오 이름을 변경할 수 없습니다: {exc}")

    confirm = st.checkbox("선택한 포트폴리오를 삭제합니다", key=f"delete_{selected.portfolio_name}")
    if col2.button("선택 포트폴리오 삭제", disabled=not confirm):
        if not begin_ui_action("storage_delete_portfolio", payload={"portfolio_name": selected.portfolio_name}):
            return
        try:
            if store.delete_portfolio(owner_id, selected.portfolio_name):
                st.cache_data.clear()
                _set_storage_status(f"{selected.portfolio_name} 포트폴리오를 삭제했습니다.")
                request_app_rerun()
            else:
                finish_ui_action(success=False)
                st.error("선택한 포트폴리오를 찾을 수 없습니다.")
        except PortfolioStoreError as exc:
            finish_ui_action(success=False)
            st.error(f"포트폴리오를 삭제할 수 없습니다: {exc}")


def render_manual_capture(
    *,
    owner_id: str | None,
    history_store: PortfolioHistoryStore | None,
    metrics: PortfolioMetrics,
) -> None:
    st.subheader("현재 상태 기록")
    if history_store is None or owner_id is None:
        st.info("Supabase 설정이 없으면 자산 이력 기록을 사용할 수 없습니다.")
        return
    if st.button("현재 상태 기록"):
        if not begin_ui_action("manual_history_capture", payload={"portfolio_name": st.session_state.get("portfolio_name", "main")}):
            return
        portfolio_name = st.session_state.get("portfolio_name", "main")
        try:
            history_store.save_snapshot(
                build_history_record(
                    owner_id=owner_id,
                    portfolio_name=portfolio_name,
                    event_type="manual_capture",
                    metrics=metrics,
                )
            )
            st.cache_data.clear()
            st.success("현재 총자산 스냅샷을 기록했습니다.")
        except Exception:
            finish_ui_action(success=False)
            raise
        finish_ui_action(success=True)
