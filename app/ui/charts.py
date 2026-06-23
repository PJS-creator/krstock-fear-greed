from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import plotly.graph_objects as go

from portfolio.chart_data import currency_exposure_frame
from portfolio.history import HistoryPeriod, PortfolioHistoryRecord, period_start
from portfolio.holdings import PortfolioMetrics

from .formatters import KST, compact_krw, format_kst, full_krw, percentage, signed_krw, signed_percentage
from .theme import CURRENCY_COLORS, DIMENSIONS, SEMANTIC_COLORS, deterministic_color, signed_color


def apply_chart_layout(
    fig: go.Figure,
    *,
    height: int = DIMENSIONS.default_height,
    hovermode: str = "closest",
    showlegend: bool = True,
) -> go.Figure:
    fig.update_layout(
        template="streamlit",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=20, t=28, b=18),
        height=height,
        hovermode=hovermode,
        showlegend=showlegend,
        legend_title_text="",
        font=dict(size=13),
        hoverlabel=dict(align="left"),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(100,116,139,0.18)", zerolinecolor="rgba(100,116,139,0.45)")
    fig.update_yaxes(showgrid=False)
    return fig


def _allocation_source_rows(metrics: PortfolioMetrics) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in metrics.rows:
        if item.market_value_krw is None or item.market_value_krw <= 0:
            continue
        rows.append(
            {
                "ticker": str(item.holding["ticker"]),
                "display_name": str(item.holding["display_name"]),
                "market": str(item.holding["market"]),
                "market_value_krw": item.market_value_krw,
                "weight": item.weight,
                "day_change_krw": item.day_change_krw,
                "day_change_pct": item.day_change_pct,
                "total_pnl_pct": item.total_pnl_pct,
            }
        )
    return sorted(rows, key=lambda row: float(row["market_value_krw"]), reverse=True)


def _collapse_small_allocation_rows(rows: list[dict[str, object]], *, max_slices: int, min_weight: float) -> list[dict[str, object]]:
    if len(rows) <= max_slices and all(float(row["weight"]) >= min_weight for row in rows):
        return rows
    keep: list[dict[str, object]] = []
    other: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if index < max_slices and float(row["weight"]) >= min_weight:
            keep.append(row)
        else:
            other.append(row)
    if other:
        other_value = sum(float(row["market_value_krw"]) for row in other)
        other_day_change = sum(float(row["day_change_krw"] or 0.0) for row in other)
        keep.append(
            {
                "ticker": "기타",
                "display_name": f"{len(other)}개 종목 합산",
                "market": "-",
                "market_value_krw": other_value,
                "weight": other_value / sum(float(row["market_value_krw"]) for row in rows),
                "day_change_krw": other_day_change,
                "day_change_pct": None,
                "total_pnl_pct": None,
            }
        )
    return keep


def plot_allocation(metrics: PortfolioMetrics, *, max_slices: int = 7, min_label_weight: float = 0.03) -> go.Figure | None:
    source_rows = _allocation_source_rows(metrics)
    if not source_rows:
        return None
    rows = _collapse_small_allocation_rows(source_rows, max_slices=max_slices, min_weight=min_label_weight)
    values = [float(row["market_value_krw"]) for row in rows]
    labels = [str(row["ticker"]) for row in rows]
    legend_labels = [f"{row['ticker']} · {row['display_name']}" for row in rows]
    text = [f"{row['ticker']}<br>{percentage(float(row['weight']))}" if float(row["weight"]) >= min_label_weight or row["ticker"] == "기타" else "" for row in rows]
    colors = [SEMANTIC_COLORS["missing"] if row["ticker"] == "기타" else deterministic_color(row["ticker"]) for row in rows]
    customdata = [
        [
            row["ticker"],
            row["display_name"],
            row["market"],
            full_krw(float(row["market_value_krw"])),
            percentage(float(row["weight"])),
            signed_krw(row["day_change_krw"]),
            signed_percentage(row["day_change_pct"]),
            signed_percentage(row["total_pnl_pct"]),
        ]
        for row in rows
    ]
    fig = go.Figure(
        go.Pie(
            labels=legend_labels,
            values=values,
            hole=0.58,
            sort=False,
            text=text,
            textinfo="text",
            textposition="outside",
            customdata=customdata,
            marker=dict(colors=colors, line=dict(color="rgba(148,163,184,0.38)", width=1)),
            hovertemplate=(
                "%{customdata[0]} · %{customdata[1]}<br>"
                "시장 %{customdata[2]}<br>"
                "평가액 %{customdata[3]}<br>"
                "비중 %{customdata[4]}<br>"
                "오늘 변동 %{customdata[5]} (%{customdata[6]})<br>"
                "총수익률 %{customdata[7]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        annotations=[
            dict(
                text=f"투자자산<br><b>{compact_krw(metrics.total_position_value_krw)}</b>",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=13),
            )
        ],
        legend=dict(orientation="h", yanchor="bottom", y=-0.18, xanchor="center", x=0.5),
    )
    return apply_chart_layout(fig, height=DIMENSIONS.tall_height, hovermode="closest")


def plot_contribution(metrics: PortfolioMetrics, *, limit: int = 10, show_all: bool = False) -> go.Figure | None:
    rows = [
        {
            "label": f"{item.holding['ticker']} · {item.holding['display_name']}",
            "ticker": str(item.holding["ticker"]),
            "display_name": str(item.holding["display_name"]),
            "day_change_krw": item.day_change_krw,
            "day_change_pct": item.day_change_pct,
        }
        for item in metrics.rows
        if item.day_change_krw is not None and item.day_change_krw != 0
    ]
    if not rows:
        return None
    selected = sorted(rows, key=lambda row: abs(float(row["day_change_krw"])), reverse=True)
    if not show_all:
        selected = selected[:limit]
    selected = sorted(selected, key=lambda row: float(row["day_change_krw"]))
    x_values = [float(row["day_change_krw"]) for row in selected]
    y_values = [str(row["label"]) for row in selected]
    customdata = [[row["display_name"], full_krw(float(row["day_change_krw"])), signed_percentage(row["day_change_pct"])] for row in selected]
    height = max(DIMENSIONS.compact_height, 110 + len(selected) * DIMENSIONS.row_height)
    fig = go.Figure(
        go.Bar(
            x=x_values,
            y=y_values,
            orientation="h",
            marker_color=[signed_color(value) for value in x_values],
            text=[signed_krw(value) for value in x_values],
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate="%{y}<br>변동액 %{customdata[1]}<br>변동률 %{customdata[2]}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_color="rgba(100,116,139,0.65)", line_width=1)
    fig.update_layout(xaxis_title="오늘 변동액", yaxis_title="", bargap=0.32)
    fig.update_xaxes(tickformat=",.0f")
    return apply_chart_layout(fig, height=height, hovermode="closest", showlegend=False)


def plot_currency_exposure(metrics: PortfolioMetrics) -> go.Figure | None:
    frame = currency_exposure_frame(metrics)
    if frame.empty or len(frame) < 2:
        return None
    total = float(frame["value_krw"].sum())
    if total <= 0:
        return None
    fig = go.Figure()
    for _, row in frame.iterrows():
        currency = "USD" if "USD" in str(row["currency"]) else "KRW"
        value = float(row["value_krw"])
        ratio = value / total
        fig.add_trace(
            go.Bar(
                x=[ratio * 100],
                y=["통화 노출"],
                orientation="h",
                name=str(row["currency"]),
                marker_color=CURRENCY_COLORS[currency],
                text=[percentage(ratio)],
                textposition="inside",
                customdata=[[full_krw(value), percentage(ratio)]],
                hovertemplate="%{fullData.name}<br>KRW 환산 %{customdata[0]}<br>비중 %{customdata[1]}<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack", xaxis_title="비중", yaxis_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_xaxes(range=[0, 100], ticksuffix="%")
    return apply_chart_layout(fig, height=DIMENSIONS.compact_height, hovermode="closest")


def _history_rows(records: Iterable[PortfolioHistoryRecord], period: HistoryPeriod) -> list[dict[str, object]]:
    start = period_start(period, now=datetime.now(timezone.utc))
    rows: list[dict[str, object]] = []
    for record in records:
        captured_at = datetime.fromisoformat(record.captured_at.replace("Z", "+00:00"))
        if start is not None and captured_at < start:
            continue
        captured_at_kst = captured_at.astimezone(KST)
        rows.append(
            {
                "captured_at": captured_at_kst,
                "captured_at_label": format_kst(captured_at_kst),
                "total_value_krw": record.total_value_krw,
                "total_position_value_krw": record.total_position_value_krw,
                "cash_total_krw": record.cash_total_krw,
                "usd_krw": record.usd_krw,
            }
        )
    return sorted(rows, key=lambda row: row["captured_at"])


def plot_total_value_history(records: list[PortfolioHistoryRecord], period: HistoryPeriod = "all") -> go.Figure | None:
    rows = _history_rows(records, period)
    if len(rows) < 2:
        return None
    x_values = [row["captured_at"] for row in rows]
    total_values = [float(row["total_value_krw"]) for row in rows]
    position_values = [float(row["total_position_value_krw"]) for row in rows]
    cash_values = [float(row["cash_total_krw"]) for row in rows]
    customdata = [
        [
            row["captured_at_label"],
            full_krw(float(row["total_value_krw"])),
            full_krw(float(row["total_position_value_krw"])),
            full_krw(float(row["cash_total_krw"])),
            f"{float(row['usd_krw']):,.2f}",
        ]
        for row in rows
    ]
    marker_size = 6 if len(rows) <= 12 else 0
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=total_values,
            name="총자산",
            mode="lines+markers" if marker_size else "lines",
            marker=dict(size=marker_size),
            line=dict(color=SEMANTIC_COLORS["primary"], width=2.4),
            fill="tozeroy",
            fillcolor="rgba(37,99,235,0.12)",
            customdata=customdata,
            hovertemplate=(
                "%{customdata[0]}<br>총자산 %{customdata[1]}<br>"
                "투자자산 %{customdata[2]}<br>총현금 %{customdata[3]}<br>USD/KRW %{customdata[4]}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=position_values,
            name="투자자산",
            mode="lines",
            line=dict(color=SEMANTIC_COLORS["secondary"], width=1.4, dash="dot"),
            hovertemplate="투자자산 ₩%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=cash_values,
            name="총현금",
            mode="lines",
            line=dict(color=SEMANTIC_COLORS["cash"], width=1.2, dash="dot"),
            hovertemplate="총현금 ₩%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="KRW", xaxis_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    fig.update_yaxes(tickformat=",.0f")
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")
