from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio.diagnostics import calculate_diagnostics
from portfolio.history import PortfolioHistoryRecord
from portfolio.holdings import PortfolioMetrics
from portfolio.sample_data import sample_portfolio

from .formatters import compact_krw, full_krw, instrument_label, percentage, signed_krw, signed_percentage
from .status import aggregate_price_statuses, build_price_log_rows, present_diagnostic, quote_status_label, split_diagnostics
from .theme import DIMENSIONS, chart_config

PENDING_PORTFOLIO_STATE_KEY = "pending_portfolio_state"


def render_plotly_chart(fig, *, key: str) -> None:
    st.plotly_chart(fig, use_container_width=True, theme=None, config=chart_config(), key=key)


def render_empty_portfolio() -> None:
    st.info(
        "보유 종목이 아직 없습니다. 1) 사용자 입력 탭에서 매입/매도 거래를 입력하고 2) 거래 미리보기 후 반영한 뒤 3) 가격 갱신, 현금·환율 입력, 저장 순서로 진행하세요."
    )
    st.caption("샘플은 기능 확인용 가상 데이터이며 실제 보유 내역이 아닙니다.")
    if st.button("샘플 불러오기", key="load_sample_portfolio"):
        positions, quotes, usd_krw, cash_krw = sample_portfolio()
        rows = []
        for position in positions:
            quote = quotes.get((position.market, position.symbol))
            rows.append(
                {
                    "market": position.market,
                    "ticker": position.symbol,
                    "display_name": position.name,
                    "currency": position.currency,
                    "quantity": position.quantity,
                    "avg_price": position.avg_price,
                    "target_weight": position.target_weight,
                    "strategy_tag": position.strategy_tag,
                    "account_name": position.account_name,
                    "current_price": quote.price if quote else None,
                    "previous_close": quote.previous_close if quote else None,
                    "quote_status": "manual" if quote else "missing",
                    "fetched_at": quote.fetched_at.isoformat() if quote else None,
                    "provider": "sample",
                }
            )
        st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
            "holdings_rows": rows,
            "portfolio_transactions": [],
            "cash_krw": cash_krw,
            "cash_usd": 0.0,
            "usd_krw": usd_krw,
            "fx_status_message": "샘플 USD/KRW 환율",
            "fx_fetched_at": None,
            "mark_clean": False,
        }
        st.rerun()


def _history_chart_data(records: list[PortfolioHistoryRecord] | None) -> list[float] | None:
    if not records or len(records) < 2:
        return None
    return [record.total_value_krw for record in records[-24:]]


def render_kpi_cards(metrics: PortfolioMetrics, *, history_records: list[PortfolioHistoryRecord] | None = None) -> None:
    total_kwargs = {}
    chart_data = _history_chart_data(history_records)
    if chart_data:
        total_kwargs = {"chart_data": chart_data, "chart_type": "line"}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "총자산",
        compact_krw(metrics.total_value_krw),
        help=f"KRW 환산 총자산입니다. 전체 금액: {full_krw(metrics.total_value_krw)}",
        border=True,
        **total_kwargs,
    )
    col2.metric(
        "오늘 변동",
        signed_krw(metrics.day_change_krw),
        delta=signed_percentage(metrics.day_change_pct) if metrics.day_change_pct is not None else None,
        help=f"최근 제공 가격과 전일 종가 차이로 계산합니다. 전체 금액: {full_krw(metrics.day_change_krw)}",
        border=True,
    )
    cash_weight = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else None
    col3.metric(
        "총현금",
        compact_krw(metrics.cash_total_krw),
        delta=f"총자산 대비 {percentage(cash_weight)}" if cash_weight is not None else None,
        delta_color="off",
        help=f"KRW 현금과 USD 현금을 USD/KRW로 환산한 금액입니다. 전체 금액: {full_krw(metrics.cash_total_krw)}",
        border=True,
    )
    col4.metric(
        "USD 노출도",
        percentage(metrics.usd_exposure_pct),
        delta=full_krw(metrics.usd_exposure_krw),
        delta_color="off",
        help="USD 현금과 USD 표시 자산의 KRW 환산 비중입니다.",
        border=True,
    )


def render_cost_basis_note(metrics: PortfolioMetrics) -> None:
    if metrics.total_pnl_krw is None or metrics.cost_basis_coverage <= 0:
        st.caption("평균 매수가가 없어 총손익과 총수익률은 표시하지 않습니다.")
        return
    st.caption(
        f"원가 정보 범위 {percentage(metrics.cost_basis_coverage)} · "
        f"원가 정보가 있는 종목 기준 총손익 {full_krw(metrics.total_pnl_krw)}, 총수익률 {signed_percentage(metrics.total_pnl_pct)}"
    )


def render_price_update_log(statuses: list[object], holdings_rows: list[dict[str, object]]) -> None:
    if not statuses:
        return
    summary = aggregate_price_statuses(statuses)
    if summary.has_issues:
        st.warning(f"가격 갱신 완료 · {summary.detail_text}")
    else:
        st.success(f"가격 갱신 완료 · {summary.short_text}")
    rows = build_price_log_rows(statuses, holdings_rows)
    with st.expander(f"데이터 업데이트 상세 · 성공 {summary.success} / 캐시 {summary.cached} / 실패 {summary.failed}", expanded=False):
        issue_only = st.checkbox("실패·이전저장값·미조회만 보기", value=summary.has_issues, key="price_log_issue_only")
        visible_rows = [row for row in rows if row["raw_status"] in {"stale", "failed", "missing", "missing_api_key"}] if issue_only else rows
        if not visible_rows:
            st.caption("확인할 실패 항목이 없습니다.")
            return
        frame = pd.DataFrame(visible_rows).drop(columns=["raw_status"])
        st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=min(DIMENSIONS.max_table_height, 90 + len(frame) * DIMENSIONS.row_height),
        )


def render_diagnostics(metrics: PortfolioMetrics) -> None:
    presentations = [
        present_diagnostic(item, priced_count=metrics.priced_count, holdings_count=metrics.holdings_count)
        for item in calculate_diagnostics(metrics)
    ]
    primary, details = split_diagnostics(presentations)
    cols = st.columns(3)
    for index, item in enumerate(primary):
        with cols[index % 3]:
            st.metric(
                item.label,
                item.value,
                delta=item.severity_label,
                delta_color="off",
                help=item.help_text,
                border=True,
            )
    if details:
        with st.expander("세부 진단", expanded=False):
            for item in details:
                st.metric(item.label, item.value, delta=item.severity_label, delta_color="off", help=item.help_text, border=True)


def render_single_currency_exposure(metrics: PortfolioMetrics) -> None:
    if metrics.total_value_krw <= 0:
        st.info("통화 노출도는 평가 가능한 자산이 있을 때 표시됩니다.")
        return
    usd_pct = metrics.usd_exposure_pct
    krw_pct = 1 - usd_pct
    dominant = "USD" if usd_pct >= krw_pct else "KRW"
    value = usd_pct if dominant == "USD" else krw_pct
    st.metric(
        "통화 노출",
        f"{dominant} {percentage(value)}",
        delta=full_krw(metrics.usd_exposure_krw if dominant == "USD" else metrics.total_value_krw - metrics.usd_exposure_krw),
        delta_color="off",
        help="통화가 하나뿐이거나 한쪽 노출만 있을 때는 차트 대신 요약으로 표시합니다.",
        border=True,
    )


def render_contribution_summary(metrics: PortfolioMetrics) -> None:
    rows = [row for row in metrics.rows if row.day_change_krw is not None and row.day_change_krw != 0]
    if not rows:
        return
    best = max(rows, key=lambda row: row.day_change_krw or 0.0)
    worst = min(rows, key=lambda row: row.day_change_krw or 0.0)
    col1, col2 = st.columns(2)
    col1.metric(
        "최대 상승 기여",
        instrument_label(best.holding),
        delta=signed_krw(best.day_change_krw),
        help=instrument_label(best.holding, include_ticker=True),
        border=True,
    )
    col2.metric(
        "최대 하락 기여",
        instrument_label(worst.holding),
        delta=signed_krw(worst.day_change_krw),
        help=instrument_label(worst.holding, include_ticker=True),
        border=True,
    )


def status_label(status: object) -> str:
    return quote_status_label(status)
