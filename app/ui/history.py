from __future__ import annotations

import streamlit as st

from portfolio.history import HistoryPeriod, PortfolioHistoryStore, PortfolioHistoryStoreError

from .styles import plot_total_value_history

PERIOD_OPTIONS: dict[str, HistoryPeriod] = {
    "1주": "1w",
    "1개월": "1m",
    "3개월": "3m",
    "전체": "all",
}


def render_history_tab(
    *,
    owner_id: str | None,
    portfolio_name: str,
    history_store: PortfolioHistoryStore | None,
) -> None:
    st.subheader("총자산 추이")
    st.caption("이 차트는 저장된 실제 스냅샷 기반 총자산 추이입니다. 거래내역과 입출금 기록이 없으므로 투자성과 수익률로 해석하지 않습니다.")
    if history_store is None or owner_id is None:
        st.info("Supabase 설정이 없으면 자산추이 탭을 사용할 수 없습니다.")
        return
    label = st.segmented_control("기간", options=list(PERIOD_OPTIONS.keys()), default="1개월")
    period = PERIOD_OPTIONS[str(label)]
    try:
        records = history_store.list_history(owner_id, portfolio_name, period=period)
    except PortfolioHistoryStoreError as exc:
        st.warning(f"자산 이력을 불러올 수 없습니다: {exc}")
        return
    fig = plot_total_value_history(records, period="all")
    if fig is None:
        st.info("총자산 추이는 스냅샷이 2개 이상 쌓인 뒤 표시됩니다. 이력은 v0.6 배포 이후부터 기록됩니다.")
        return
    st.plotly_chart(fig, use_container_width=True)
