from __future__ import annotations

import streamlit as st

from portfolio.history import HistoryPeriod, PortfolioHistoryRecord, PortfolioHistoryStore, PortfolioHistoryStoreError

from .charts import plot_total_value_history
from .components import render_plotly_chart

PERIOD_OPTIONS: dict[str, HistoryPeriod] = {
    "1주": "1w",
    "1개월": "1m",
    "3개월": "3m",
    "전체": "all",
}


@st.cache_data(ttl=60, show_spinner=False)
def _list_history_cached(
    _history_store: PortfolioHistoryStore,
    owner_id: str,
    portfolio_name: str,
    period: HistoryPeriod,
) -> list[PortfolioHistoryRecord]:
    return _history_store.list_history(owner_id, portfolio_name, period=period)


def render_history_tab(
    *,
    owner_id: str | None,
    portfolio_name: str,
    history_store: PortfolioHistoryStore | None,
) -> None:
    st.subheader("총자산 추이")
    st.caption("저장된 스냅샷 기반 총자산 변화입니다. 거래내역과 입출금 기록이 없으므로 투자성과 수익률로 해석하지 않습니다.")
    if history_store is None or owner_id is None:
        st.info("Supabase 설정이 없으면 자산추이 탭을 사용할 수 없습니다.")
        return
    label = st.radio("기간", options=list(PERIOD_OPTIONS.keys()), index=1, horizontal=True, key="history_period")
    period = PERIOD_OPTIONS[str(label)]
    try:
        records = _list_history_cached(history_store, owner_id, portfolio_name, period)
    except PortfolioHistoryStoreError as exc:
        st.warning(f"자산 이력을 불러올 수 없습니다: {exc}")
        return
    fig = plot_total_value_history(records, period=period)
    if fig is None:
        st.info("자산 기록이 2개 이상 쌓이면 추이가 표시됩니다. 저장 또는 현재 상태 기록을 사용해 스냅샷을 남길 수 있습니다.")
        return
    render_plotly_chart(fig, key=f"history_chart_{period}")
