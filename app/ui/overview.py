from __future__ import annotations

import streamlit as st

from portfolio.diagnostics import calculate_diagnostics
from portfolio.holdings import PortfolioMetrics

from .styles import compact_krw, full_krw, pct, plot_allocation, plot_contribution, plot_currency_exposure


def render_overview(metrics: PortfolioMetrics) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("총자산", compact_krw(metrics.total_value_krw), help=full_krw(metrics.total_value_krw))
    col2.metric(
        "오늘 변동",
        compact_krw(metrics.day_change_krw),
        delta=pct(metrics.day_change_pct) if metrics.day_change_pct is not None else None,
        help=full_krw(metrics.day_change_krw),
    )
    cash_weight = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else None
    col3.metric("총현금", compact_krw(metrics.cash_total_krw), delta=pct(cash_weight), help=full_krw(metrics.cash_total_krw))
    col4.metric("USD 노출도", pct(metrics.usd_exposure_pct), help=full_krw(metrics.usd_exposure_krw))

    if metrics.total_pnl_krw is not None and metrics.cost_basis_coverage > 0:
        st.caption(
            f"원가 정보 범위: {pct(metrics.cost_basis_coverage)} · "
            f"원가 정보가 있는 종목 기준 총손익 {full_krw(metrics.total_pnl_krw)}, 총수익률 {pct(metrics.total_pnl_pct)}"
        )
    else:
        st.caption("평균 매수가가 없어 총손익과 총수익률은 표시하지 않습니다.")

    st.subheader("자산 구성")
    chart_col1, chart_col2 = st.columns(2)
    allocation = plot_allocation(metrics)
    if allocation is None:
        chart_col1.info("종목별 자산 비중 차트는 평가 가능한 종목이 2개 이상일 때 표시됩니다.")
    else:
        chart_col1.plotly_chart(allocation, use_container_width=True)

    exposure = plot_currency_exposure(metrics)
    if exposure is None:
        chart_col2.info("통화별 노출도 차트는 KRW/USD 노출 데이터가 있을 때 표시됩니다.")
    else:
        chart_col2.plotly_chart(exposure, use_container_width=True)

    st.subheader("오늘 변동 기여도")
    contribution = plot_contribution(metrics)
    if contribution is None:
        st.info("전일 종가와 최근 제공 가격이 있는 종목이 있어야 변동 기여도를 표시합니다.")
    else:
        st.plotly_chart(contribution, use_container_width=True)

    st.subheader("자산 진단")
    diagnostic_cols = st.columns(3)
    for index, item in enumerate(calculate_diagnostics(metrics)):
        with diagnostic_cols[index % 3]:
            st.metric(item.label, item.value)
            st.caption(item.message)
