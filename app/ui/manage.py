from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st

from portfolio.history import PortfolioHistoryStore, build_history_record
from portfolio.holdings import HOLDING_COLUMNS, PortfolioMetrics, normalize_holding_rows
from portfolio.storage import (
    PortfolioRecord,
    PortfolioStore,
    PortfolioStoreError,
    deserialize_portfolio_payload_v2,
    serialize_portfolio_payload,
)
from portfolio.transactions import TRANSACTION_COLUMNS, normalize_transaction_rows, rows_to_csv as transaction_rows_to_csv
from .formatters import format_kst

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


def queue_portfolio_record_load(record: PortfolioRecord) -> None:
    payload = deserialize_portfolio_payload_v2(record.payload_json)
    cash = payload["cash_balances"]
    _queue_portfolio_state_update(
        portfolio_name=record.portfolio_name,
        portfolio_transactions=payload.get("transactions", []),
        holdings_rows=payload["holdings"],
        usd_krw=float(payload["usd_krw"]),
        cash_krw=float(cash.get("KRW", 0.0)),
        cash_usd=float(cash.get("USD", 0.0)),
    )
    _set_storage_status(f"{record.portfolio_name} 포트폴리오를 불러왔습니다.")


def render_csv_tools() -> None:
    st.subheader("CSV")
    st.caption("자산 입력은 보유현황 CSV가 아니라 보유자산 탭의 매입/매도 거래 CSV로 일원화했습니다.")
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
            try:
                payload = serialize_portfolio_payload(
                    st.session_state.get("holdings_rows", []),
                    usd_krw=st.session_state.get("usd_krw", 1380.0),
                    cash_krw=st.session_state.get("cash_krw", 0.0),
                    cash_usd=st.session_state.get("cash_usd", 0.0),
                    transactions=st.session_state.get("portfolio_transactions", []),
                )
                store.save_portfolio(owner_id, clean_name, payload)
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
                st.rerun()
            except (PortfolioStoreError, ValueError) as exc:
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
        try:
            queue_portfolio_record_load(selected)
            st.rerun()
        except (PortfolioStoreError, ValueError) as exc:
            st.error(f"포트폴리오를 불러올 수 없습니다: {exc}")

    with st.expander("포트폴리오 이름 변경", expanded=False):
        new_name = st.text_input("새 이름", value=selected.portfolio_name, key=f"rename_{selected.portfolio_name}")
        confirm_rename = st.checkbox("선택한 포트폴리오 이름 변경 확인", key=f"confirm_rename_{selected.portfolio_name}")
        if st.button("이름 변경", disabled=not confirm_rename):
            clean_name = str(new_name or "").strip()
            if not clean_name:
                st.error("새 이름을 입력하세요.")
            else:
                try:
                    store.save_portfolio(owner_id, clean_name, selected.payload_json)
                    if clean_name != selected.portfolio_name:
                        store.delete_portfolio(owner_id, selected.portfolio_name)
                    st.cache_data.clear()
                    _queue_portfolio_name_update(clean_name)
                    _set_storage_status(f"{selected.portfolio_name} → {clean_name} 이름을 변경했습니다.")
                    st.rerun()
                except PortfolioStoreError as exc:
                    st.error(f"포트폴리오 이름을 변경할 수 없습니다: {exc}")

    confirm = st.checkbox("선택한 포트폴리오를 삭제합니다", key=f"delete_{selected.portfolio_name}")
    if col2.button("선택 포트폴리오 삭제", disabled=not confirm):
        try:
            if store.delete_portfolio(owner_id, selected.portfolio_name):
                st.cache_data.clear()
                _set_storage_status(f"{selected.portfolio_name} 포트폴리오를 삭제했습니다.")
                st.rerun()
            else:
                st.error("선택한 포트폴리오를 찾을 수 없습니다.")
        except PortfolioStoreError as exc:
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
        portfolio_name = st.session_state.get("portfolio_name", "main")
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
