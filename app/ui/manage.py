from __future__ import annotations

from io import BytesIO
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

STORAGE_UNCONFIGURED_MESSAGE = "저장소가 설정되지 않아 CSV 방식만 사용할 수 있습니다"


def _holdings_csv(rows: list[dict[str, object]]) -> str:
    frame = pd.DataFrame(normalize_holding_rows(rows), columns=HOLDING_COLUMNS)
    return frame.to_csv(index=False)


def _read_csv(uploaded_file) -> list[dict[str, object]]:
    frame = pd.read_csv(BytesIO(uploaded_file.getvalue()), dtype=str)
    return normalize_holding_rows(frame.to_dict("records"))


@st.cache_data(ttl=60, show_spinner=False)
def _list_portfolios_cached(_store: PortfolioStore, owner_id: str) -> list[PortfolioRecord]:
    return _store.list_portfolios(owner_id)


def render_csv_tools() -> None:
    st.subheader("CSV")
    uploaded_file = st.file_uploader("CSV 업로드", type=["csv"])
    if uploaded_file is not None:
        try:
            st.session_state.holdings_rows = _read_csv(uploaded_file)
            st.success("CSV 포트폴리오를 불러왔습니다.")
        except ValueError as exc:
            st.error(f"CSV를 불러올 수 없습니다: {exc}")
    st.download_button(
        "현재 포트폴리오 CSV 다운로드",
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
    if store is None or owner_id is None:
        st.info(STORAGE_UNCONFIGURED_MESSAGE)
        return

    with st.form("portfolio_save_form"):
        portfolio_name = st.text_input("portfolio_name", value=st.session_state.get("portfolio_name", "main"))
        submitted = st.form_submit_button("현재 포트폴리오 저장")
    if submitted:
        clean_name = portfolio_name.strip()
        if not clean_name:
            st.error("portfolio_name을 입력하세요.")
        else:
            try:
                payload = serialize_portfolio_payload(
                    st.session_state.get("holdings_rows", []),
                    usd_krw=st.session_state.get("usd_krw", 1380.0),
                    cash_krw=st.session_state.get("cash_krw", 0.0),
                    cash_usd=st.session_state.get("cash_usd", 0.0),
                )
                store.save_portfolio(owner_id, clean_name, payload)
                st.session_state.portfolio_name = clean_name
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
                st.success(f"{clean_name} 포트폴리오를 저장했습니다.")
            except (PortfolioStoreError, ValueError) as exc:
                st.error(f"포트폴리오를 저장할 수 없습니다: {exc}")

    try:
        records = _list_portfolios_cached(store, owner_id)
    except PortfolioStoreError as exc:
        st.warning(f"저장 목록을 불러올 수 없습니다: {exc}")
        records = []
    if not records:
        st.info("저장된 포트폴리오가 없습니다.")
        return

    labels = {f"{record.portfolio_name} ({(record.updated_at or record.created_at or '')[:10]})": record for record in records}
    selected_label = st.selectbox("저장된 포트폴리오", list(labels.keys()))
    selected = labels[selected_label]
    col1, col2 = st.columns(2)
    if col1.button("선택 포트폴리오 불러오기"):
        try:
            payload = deserialize_portfolio_payload_v2(selected.payload_json)
            cash = payload["cash_balances"]
            st.session_state.portfolio_name = selected.portfolio_name
            st.session_state.holdings_rows = payload["holdings"]
            st.session_state.usd_krw = float(payload["usd_krw"])
            st.session_state.cash_krw = float(cash.get("KRW", 0.0))
            st.session_state.cash_usd = float(cash.get("USD", 0.0))
            st.success(f"{selected.portfolio_name} 포트폴리오를 불러왔습니다.")
            st.rerun()
        except (PortfolioStoreError, ValueError) as exc:
            st.error(f"포트폴리오를 불러올 수 없습니다: {exc}")

    confirm = st.checkbox("선택한 포트폴리오를 삭제합니다", key=f"delete_{selected.portfolio_name}")
    if col2.button("선택 포트폴리오 삭제", disabled=not confirm):
        try:
            if store.delete_portfolio(owner_id, selected.portfolio_name):
                st.cache_data.clear()
                st.success(f"{selected.portfolio_name} 포트폴리오를 삭제했습니다.")
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
