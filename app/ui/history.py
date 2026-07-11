from __future__ import annotations

import streamlit as st

from portfolio.historical_holdings import HistoricalScheduleStore
from portfolio.history import HistoryPeriod, PortfolioHistoryRecord, PortfolioHistoryStore, PortfolioHistoryStoreError

from .charts import plot_total_value_history
from .components import render_empty_state, render_plotly_chart
from .historical_reconstruction import render_historical_reconstruction_tab
from .performance import render_performance_analysis
from .risk import render_risk_analysis

PERIOD_OPTIONS: dict[str, HistoryPeriod] = {
    "1주": "1w",
    "1개월": "1m",
    "3개월": "3m",
    "전체": "all",
}
HISTORY_VIEW_KEY = "history_analysis_view"
HISTORY_VIEW_LABELS = {
    "actual": "실제 기록",
    "performance": "성과분석",
    "risk": "리스크분석",
    "reconstructed": "과거 보유현황 재구성",
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
    current_holdings_rows: list[dict[str, object]] | None = None,
    current_cash_krw: float = 0.0,
    current_cash_usd: float = 0.0,
    current_usd_krw: float = 1380.0,
    current_transactions: list[dict[str, object]] | None = None,
    current_cash_ledger: list[dict[str, object]] | None = None,
    current_total_value_krw: float | None = None,
    is_authenticated: bool = False,
) -> None:
    with st.container(key="history_analysis_tabs"):
        selected_view = st.radio(
            "자산추이 화면",
            list(HISTORY_VIEW_LABELS),
            format_func=HISTORY_VIEW_LABELS.get,
            key=HISTORY_VIEW_KEY,
            horizontal=True,
            label_visibility="collapsed",
        )

    if selected_view == "actual":
        _render_actual_history(owner_id=owner_id, portfolio_name=portfolio_name, history_store=history_store)
    elif selected_view == "performance":
        render_performance_analysis(
            transactions=list(current_transactions or []),
            cash_ledger=list(current_cash_ledger or []),
            holdings=list(current_holdings_rows or []),
            usd_krw=current_usd_krw,
            current_total_value_krw=current_total_value_krw,
        )
    elif selected_view == "risk":
        records = None
        load_error = None
        if history_store is not None and owner_id is not None:
            try:
                records = _list_history_cached(history_store, owner_id, portfolio_name, "all")
            except PortfolioHistoryStoreError as exc:
                load_error = str(exc)
        render_risk_analysis(history_records=records, load_error=load_error)
    else:
        render_historical_reconstruction_tab(
            owner_id=owner_id,
            schedule_store=historical_schedule_store,
            current_holdings_rows=list(current_holdings_rows or []),
            current_cash_krw=current_cash_krw,
            current_cash_usd=current_cash_usd,
            current_usd_krw=current_usd_krw,
            is_authenticated=is_authenticated,
        )


def clear_history_cache() -> None:
    _list_history_cached.clear()


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
        render_empty_state(
            "아직 기록된 자산 변화가 없습니다.",
            "자산 기록이 2개 이상 쌓이고 값이 0원이 아니면 총자산 추이가 표시됩니다.",
        )
        return
    render_plotly_chart(fig, key=f"history_chart_{period}")
