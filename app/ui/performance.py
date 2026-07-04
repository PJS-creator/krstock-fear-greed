from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio.performance import PerformanceAnalysis, calculate_performance_metrics

from .charts import apply_chart_layout, is_all_zero_series
from .components import render_empty_state, render_metric_card, render_plotly_chart
from .formatters import format_number, format_price, full_krw, instrument_label, percentage, signed_krw, signed_percentage
from .theme import DIMENSIONS, SEMANTIC_COLORS


def _analysis_available(transactions: list[dict[str, object]], cash_ledger: list[dict[str, object]], holdings: list[dict[str, object]]) -> bool:
    return bool(transactions or cash_ledger or holdings)


def _render_metric_cards(analysis: PerformanceAnalysis) -> None:
    def tone(value: float) -> str:
        if value > 0:
            return "success"
        if value < 0:
            return "danger"
        return "neutral"

    cards = [
        ("총손익", signed_krw(analysis.total_profit_krw), signed_percentage(analysis.simple_return), tone(analysis.total_profit_krw), "실현손익 + 미실현손익 + 배당/이자 - 수수료/세금입니다."),
        ("실현손익", signed_krw(analysis.realized_pnl_krw), None, tone(analysis.realized_pnl_krw), "매도 거래에서 이동평균단가 기준으로 확정된 손익입니다."),
        ("미실현손익", signed_krw(analysis.unrealized_pnl_krw), None, tone(analysis.unrealized_pnl_krw), "현재 보유 수량의 평가손익입니다."),
        ("배당/이자", signed_krw(analysis.dividend_interest_krw), None, "info", "현금 원장에 입력된 배당과 이자 수익입니다."),
        ("수수료/세금", full_krw(analysis.fees_taxes_krw), None, "warning" if analysis.fees_taxes_krw else "neutral", "사용자가 거래 또는 원장에 입력한 수수료와 세금 합계입니다."),
        ("환율효과", signed_krw(analysis.fx_effect_krw), None, tone(analysis.fx_effect_krw), "USD 종목 손익 중 환율 변화로 설명되는 금액입니다."),
        ("순입금액", signed_krw(analysis.net_deposit_krw), None, "info", "입금, 출금, 시작 잔고, 수동 조정의 KRW 환산 합계입니다."),
        ("입출금 제외 성과", signed_krw(analysis.flow_adjusted_asset_change_krw), signed_percentage(analysis.twr_base_return), tone(analysis.flow_adjusted_asset_change_krw), "현재 총자산에서 순입금액을 뺀 값입니다. TWR 계산을 위한 기초 참고값입니다."),
    ]
    for row_start in range(0, len(cards), 4):
        columns = st.columns(4)
        for column, (title, value, delta, status, help_text) in zip(columns, cards[row_start : row_start + 4]):
            with column:
                render_metric_card(title, value, delta=delta, status=status, help_text=help_text)


def _plot_asset_vs_deposit(analysis: PerformanceAnalysis) -> go.Figure | None:
    if analysis.current_total_value_krw is None:
        return None
    labels = ["총자산", "순입금액", "입출금 제외 성과"]
    values = [
        analysis.current_total_value_krw,
        analysis.net_deposit_krw,
        analysis.flow_adjusted_asset_change_krw or 0.0,
    ]
    if is_all_zero_series(values):
        return None
    colors = [SEMANTIC_COLORS["primary"], SEMANTIC_COLORS["neutral"], SEMANTIC_COLORS["positive"] if values[2] >= 0 else SEMANTIC_COLORS["negative"]]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors, text=[full_krw(value) for value in values], textposition="outside"))
    fig.update_layout(yaxis_title="KRW", margin=dict(l=18, r=18, t=28, b=24))
    fig.update_yaxes(tickformat=",.0f", zeroline=True)
    return apply_chart_layout(fig, height=DIMENSIONS.compact_height, hovermode="closest", showlegend=False)


def _plot_pnl_waterfall(analysis: PerformanceAnalysis) -> go.Figure | None:
    if is_all_zero_series(
        [
            analysis.realized_pnl_krw,
            analysis.unrealized_pnl_krw,
            analysis.dividend_interest_krw,
            analysis.fees_taxes_krw,
            analysis.total_profit_krw,
        ]
    ):
        return None
    fig = go.Figure(
        go.Waterfall(
            x=["실현손익", "미실현손익", "배당/이자", "수수료/세금", "총손익"],
            measure=["relative", "relative", "relative", "relative", "total"],
            y=[
                analysis.realized_pnl_krw,
                analysis.unrealized_pnl_krw,
                analysis.dividend_interest_krw,
                -analysis.fees_taxes_krw,
                analysis.total_profit_krw,
            ],
            text=[
                signed_krw(analysis.realized_pnl_krw),
                signed_krw(analysis.unrealized_pnl_krw),
                signed_krw(analysis.dividend_interest_krw),
                signed_krw(-analysis.fees_taxes_krw),
                signed_krw(analysis.total_profit_krw),
            ],
            textposition="outside",
            connector={"line": {"color": SEMANTIC_COLORS["neutral"]}},
        )
    )
    fig.update_layout(yaxis_title="KRW", margin=dict(l=18, r=18, t=28, b=24), showlegend=False)
    fig.update_yaxes(tickformat=",.0f", zeroline=True)
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="closest", showlegend=False)


def _monthly_frame(analysis: PerformanceAnalysis) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "월": row.month,
                "실현손익": signed_krw(row.realized_pnl_krw),
                "배당/이자": signed_krw(row.dividend_interest_krw),
                "수수료/세금": full_krw(row.fees_taxes_krw),
                "월 손익": signed_krw(row.net_investment_result_krw),
                "외부 순입금": signed_krw(row.external_flow_krw),
                "매수액": full_krw(row.buy_amount_krw),
                "매도액": full_krw(row.sell_amount_krw),
            }
            for row in analysis.monthly_rows
        ]
    )


def _symbol_frame(analysis: PerformanceAnalysis) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "종목": instrument_label({"market": row.market, "ticker": row.ticker, "display_name": row.display_name}),
                "보유수량": format_number(row.quantity, digits=4, trim=True),
                "평균단가": format_price(row.avg_price, row.currency),
                "현재가": format_price(row.current_price, row.currency),
                "실현손익": signed_krw(row.realized_pnl_krw),
                "미실현손익": signed_krw(row.unrealized_pnl_krw),
                "배당": signed_krw(row.dividend_interest_krw),
                "수수료/세금": full_krw(row.fees_taxes_krw),
                "총손익": signed_krw(row.total_pnl_krw),
                "환율효과": signed_krw(row.fx_effect_krw),
                "환율": "추정" if row.estimated_fx else "입력값",
            }
            for row in analysis.rows
        ]
    )


def render_performance_analysis(
    *,
    transactions: list[dict[str, object]],
    cash_ledger: list[dict[str, object]],
    holdings: list[dict[str, object]],
    usd_krw: float,
    current_total_value_krw: float | None,
) -> None:
    st.subheader("성과분석")
    st.caption("투자 조언이나 매수/매도 추천이 아닌 사용자가 입력한 거래·현금 원장 기반 성과 집계입니다.")
    if not _analysis_available(transactions, cash_ledger, holdings):
        render_empty_state(
            "성과분석을 계산할 데이터가 없습니다.",
            "거래 또는 현금 원장을 입력하면 실현손익, 미실현손익, 배당/이자, 수수료/세금을 분리해 볼 수 있습니다.",
        )
        return
    try:
        analysis = calculate_performance_metrics(
            transactions=transactions,
            cash_ledger=cash_ledger,
            holdings=holdings,
            usd_krw=usd_krw,
            current_total_value_krw=current_total_value_krw,
        )
    except ValueError as exc:
        st.warning(f"성과분석을 계산할 수 없습니다: {exc}")
        return

    _render_metric_cards(analysis)
    st.caption("세금 계산은 실제 세무 자문이 아니며, 사용자가 입력한 세금/수수료 값을 기준으로 단순 집계합니다.")
    if analysis.estimated_fx:
        st.warning("일부 USD 거래 또는 원장 항목에 거래 당시 환율이 없어 현재 USD/KRW 환율로 추정했습니다.")

    asset_fig = _plot_asset_vs_deposit(analysis)
    waterfall_fig = _plot_pnl_waterfall(analysis)
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        if asset_fig is not None:
            render_plotly_chart(asset_fig, key="performance_asset_vs_deposit")
        else:
            render_empty_state("자산 변화 차트 데이터가 부족합니다.", "총자산 또는 순입금액이 쌓이면 차트가 표시됩니다.")
    with chart_col2:
        if waterfall_fig is not None:
            render_plotly_chart(waterfall_fig, key="performance_pnl_waterfall")
        else:
            render_empty_state("손익 분해 차트 데이터가 부족합니다.", "손익, 배당, 수수료 또는 세금 기록이 생기면 차트가 표시됩니다.")

    st.subheader("종목별 성과")
    symbol_frame = _symbol_frame(analysis)
    if symbol_frame.empty:
        st.info("종목별 성과를 계산할 거래 또는 보유 종목이 없습니다.")
    else:
        st.dataframe(
            symbol_frame,
            hide_index=True,
            width="stretch",
            height=min(DIMENSIONS.max_table_height, 100 + len(symbol_frame) * DIMENSIONS.row_height),
        )

    st.subheader("월별 집계")
    monthly_frame = _monthly_frame(analysis)
    if monthly_frame.empty:
        st.info("월별 집계를 표시할 거래 또는 현금 원장 항목이 없습니다.")
    else:
        st.dataframe(
            monthly_frame,
            hide_index=True,
            width="stretch",
            height=min(DIMENSIONS.max_table_height, 100 + len(monthly_frame) * DIMENSIONS.row_height),
        )

    st.caption(
        "TWR은 각 입출금 시점의 포트폴리오 평가액이 필요합니다. 현재 화면의 TWR 기초값은 입출금 제외 성과율 참고값이며, "
        f"MWR/IRR 기초값은 {percentage(analysis.mwr_irr) if analysis.mwr_irr is not None else '데이터 부족'}입니다."
    )
