from __future__ import annotations

import streamlit as st

from portfolio.history import PortfolioHistoryRecord
from portfolio.holdings import PortfolioMetrics

from .charts import plot_allocation, plot_contribution, plot_currency_exposure
from .components import (
    render_contribution_summary,
    render_cost_basis_note,
    render_diagnostics,
    render_empty_state,
    render_kpi_cards,
    render_plotly_chart,
    render_single_currency_exposure,
)


def render_overview(metrics: PortfolioMetrics, *, history_records: list[PortfolioHistoryRecord] | None = None) -> None:
    if metrics.holdings_count == 0 and metrics.total_value_krw <= 0:
        render_empty_state(
            "분석할 자산이 없습니다.",
            "입금 또는 보유종목을 입력하면 총자산, 자산 비중, 통화 노출, 진단이 표시됩니다.",
        )
        return

    render_kpi_cards(metrics, history_records=history_records)
    render_cost_basis_note(metrics)

    st.subheader("자산 비중")
    st.caption("현금을 포함한 총자산 기준입니다. 통화 노출은 KRW 환산 금액입니다.")
    chart_col1, chart_col2 = st.columns(2)
    allocation = plot_allocation(metrics)
    with chart_col1:
        if allocation is None:
            st.info("평가 가능한 보유 종목이 있으면 종목별 구성 차트가 표시됩니다.")
        else:
            render_plotly_chart(allocation, key="allocation_donut")
    exposure = plot_currency_exposure(metrics)
    with chart_col2:
        if exposure is None:
            render_single_currency_exposure(metrics)
        else:
            render_plotly_chart(exposure, key="currency_exposure")

    st.subheader("오늘 기여도")
    render_contribution_summary(metrics)
    show_all = st.toggle("전체 종목 보기", value=False, key="show_all_contribution") if len(metrics.rows) > 10 else False
    contribution = plot_contribution(metrics, show_all=show_all)
    if contribution is None:
        st.info("오늘 변동 데이터가 없습니다. 전일 종가와 최근 제공 가격이 있는 종목이 쌓이면 표시됩니다.")
    else:
        render_plotly_chart(contribution, key="contribution_chart")

    st.subheader("진단")
    render_diagnostics(metrics)
