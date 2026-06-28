from __future__ import annotations

import streamlit as st

from portfolio.historical_holdings import HistoricalScheduleStore
from portfolio.history import HistoryPeriod, PortfolioHistoryRecord, PortfolioHistoryStore, PortfolioHistoryStoreError

from .charts import plot_total_value_history
from .components import render_plotly_chart
from .historical_reconstruction import render_historical_reconstruction_tab

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
    historical_schedule_store: HistoricalScheduleStore | None = None,
    current_cash_krw: float = 0.0,
    current_cash_usd: float = 0.0,
    current_usd_krw: float = 1380.0,
    is_authenticated: bool = False,
) -> None:
    actual_tab, reconstructed_tab = st.tabs(["실제 기록", "과거 보유현황 재구성"])
    with actual_tab:
        _render_actual_history(owner_id=owner_id, portfolio_name=portfolio_name, history_store=history_store)
    with reconstructed_tab:
        render_historical_reconstruction_tab(
            owner_id=owner_id,
            schedule_store=historical_schedule_store,
            current_cash_krw=current_cash_krw,
            current_cash_usd=current_cash_usd,
            current_usd_krw=current_usd_krw,
            is_authenticated=is_authenticated,
        )


def _render_actual_history(
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
