from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from portfolio.chart_data import contribution_frame, currency_exposure_frame, holdings_allocation_frame, history_frame
from portfolio.history import HistoryPeriod, PortfolioHistoryRecord
from portfolio.holdings import PortfolioMetrics

PALETTE = {
    "ink": "#17202A",
    "muted": "#6B7280",
    "border": "#D8DEE8",
    "positive": "#188A55",
    "negative": "#C24135",
    "accent": "#2563EB",
    "accent2": "#0F766E",
    "warn": "#B45309",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {
            border: 1px solid #D8DEE8;
            border-radius: 8px;
            padding: 0.9rem 1rem;
            background: #FFFFFF;
        }
        div[data-testid="stMetricLabel"] {color: #4B5563;}
        .small-muted {color: #6B7280; font-size: 0.88rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def compact_krw(value: float | None) -> str:
    if value is None:
        return "미산정"
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 100_000_000:
        return f"{sign}{abs_value / 100_000_000:.2f}억"
    if abs_value >= 10_000:
        return f"{sign}{abs_value / 10_000:.0f}만"
    return f"{value:,.0f}원"


def full_krw(value: float | None) -> str:
    if value is None:
        return "미산정"
    return f"₩{value:,.0f}"


def pct(value: float | None) -> str:
    if value is None:
        return "미산정"
    return f"{value * 100:.2f}%"


def plot_total_value_history(records: list[PortfolioHistoryRecord], period: HistoryPeriod) -> go.Figure | None:
    frame = history_frame(records, period=period)
    if frame.empty or len(frame) < 2:
        return None
    fig = px.area(
        frame,
        x="captured_at",
        y="total_value_krw",
        hover_data={"total_value_krw": ":,.0f", "captured_at": "|%Y-%m-%d %H:%M"},
        labels={"captured_at": "기록 시각", "total_value_krw": "총자산(KRW)"},
    )
    fig.update_traces(line_color=PALETTE["accent"], fillcolor="rgba(37,99,235,0.16)")
    _apply_chart_layout(fig)
    return fig


def plot_allocation(metrics: PortfolioMetrics) -> go.Figure | None:
    frame = holdings_allocation_frame(metrics)
    if frame.empty or len(frame) < 2:
        return None
    fig = px.pie(
        frame,
        names="ticker",
        values="market_value_krw",
        hole=0.55,
        hover_data={"display_name": True, "market_value_krw": ":,.0f", "weight": ":.2%"},
    )
    _apply_chart_layout(fig)
    return fig


def plot_contribution(metrics: PortfolioMetrics) -> go.Figure | None:
    frame = contribution_frame(metrics)
    if frame.empty:
        return None
    frame["color"] = frame["day_change_krw"].apply(lambda value: PALETTE["positive"] if value >= 0 else PALETTE["negative"])
    fig = go.Figure(
        go.Bar(
            x=frame["day_change_krw"],
            y=frame["ticker"],
            orientation="h",
            marker_color=frame["color"],
            customdata=frame[["display_name", "day_change_pct"]],
            hovertemplate="%{y}<br>%{customdata[0]}<br>변동액 ₩%{x:,.0f}<br>변동률 %{customdata[1]:.2%}<extra></extra>",
        )
    )
    _apply_chart_layout(fig)
    fig.update_layout(xaxis_title="오늘 변동(KRW)", yaxis_title="")
    return fig


def plot_currency_exposure(metrics: PortfolioMetrics) -> go.Figure | None:
    frame = currency_exposure_frame(metrics)
    if frame.empty or len(frame) < 2:
        return None
    fig = px.bar(
        frame,
        x="currency",
        y="value_krw",
        color="currency",
        color_discrete_sequence=[PALETTE["accent2"], PALETTE["accent"]],
        labels={"currency": "통화 노출", "value_krw": "KRW 환산"},
    )
    _apply_chart_layout(fig)
    return fig


def _apply_chart_layout(fig: go.Figure) -> None:
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
        legend_title_text="",
        font=dict(family="Arial, sans-serif", size=13, color=PALETTE["ink"]),
        autosize=True,
    )
    fig.update_yaxes(tickformat=",")
    fig.update_xaxes(showgrid=True, gridcolor="rgba(107,114,128,0.16)")


def show_dataframe(frame: pd.DataFrame) -> None:
    st.dataframe(frame, use_container_width=True, hide_index=True)
