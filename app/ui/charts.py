from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import math
from typing import Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio.chart_data import currency_exposure_frame
from portfolio.historical_holdings import ReconstructionResult, build_ticker_value_series
from portfolio.history import HistoryPeriod, PortfolioHistoryRecord, period_start
from portfolio.holdings import PortfolioMetrics
from portfolio.transactions import transaction_cashflow_rows

from .formatters import (
    APP_FONT_FAMILY,
    KST,
    compact_krw,
    format_kst,
    format_number,
    format_price,
    full_krw,
    instrument_label,
    percentage,
    signed_krw,
    signed_percentage,
)
from .theme import CURRENCY_COLORS, DIMENSIONS, SEMANTIC_COLORS, deterministic_color, get_active_theme, signed_color


def sanitize_chart_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    clean = df.copy()
    clean = clean.replace([math.inf, -math.inf], pd.NA)
    return clean.dropna(how="all")


def is_all_zero_series(series: Iterable[object]) -> bool:
    values: list[float] = []
    for value in series:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            values.append(number)
    return bool(values) and all(abs(value) < 1e-12 for value in values)


def has_chart_data(df_or_series: object, required_columns: list[str] | None = None) -> bool:
    if df_or_series is None:
        return False
    if isinstance(df_or_series, pd.DataFrame):
        frame = sanitize_chart_df(df_or_series)
        if frame.empty:
            return False
        if required_columns and any(column not in frame.columns for column in required_columns):
            return False
        numeric = frame[required_columns] if required_columns else frame.select_dtypes(include="number")
        if numeric.empty:
            return True
        values = [value for value in numeric.to_numpy().ravel() if pd.notna(value)]
        return bool(values) and not is_all_zero_series(values)
    if isinstance(df_or_series, pd.Series):
        clean = pd.to_numeric(df_or_series.replace([math.inf, -math.inf], pd.NA), errors="coerce").dropna()
        return not clean.empty and not is_all_zero_series(clean)
    try:
        values = list(df_or_series)  # type: ignore[arg-type]
    except TypeError:
        return False
    return bool(values) and not is_all_zero_series(values)


def format_krw_axis(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.1f}억"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.0f}만"
    return f"{number:,.0f}원"


def format_pct_axis(value: object) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return ""


def apply_plotly_theme(fig: go.Figure, theme_tokens: dict[str, str] | None = None) -> go.Figure:
    theme = get_active_theme()
    tokens = theme_tokens or theme.tokens()
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=APP_FONT_FAMILY, color=tokens["text"]),
        hoverlabel=dict(
            align="left",
            bgcolor=theme.chart_hover_bg,
            bordercolor=theme.chart_hover_border,
            font=dict(family=APP_FONT_FAMILY, size=13, color="#FFFFFF"),
        ),
    )
    fig.update_xaxes(gridcolor=tokens["chart_grid"], zerolinecolor=theme.chart_zero, tickfont=dict(color=tokens["chart_axis"]), automargin=True)
    fig.update_yaxes(gridcolor=tokens["chart_grid"], zerolinecolor=theme.chart_zero, tickfont=dict(color=tokens["chart_axis"]), automargin=True)
    return fig


def render_empty_chart_state(title: str, message: str, cta_label: str | None = None, cta_key: str | None = None) -> bool:
    from .components import render_empty_state

    clicked, _ = render_empty_state(title, message, primary_label=cta_label, primary_key=cta_key)
    return clicked


def apply_chart_layout(
    fig: go.Figure,
    *,
    height: int = DIMENSIONS.default_height,
    hovermode: str = "closest",
    showlegend: bool = True,
) -> go.Figure:
    theme = get_active_theme()
    apply_plotly_theme(fig, theme.tokens())
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=20, t=28, b=18),
        height=height,
        hovermode=hovermode,
        showlegend=showlegend,
        legend_title_text="",
        font=dict(family=APP_FONT_FAMILY, size=15, color=theme.text),
        hoverlabel=dict(
            align="left",
            bgcolor=theme.chart_hover_bg,
            bordercolor=theme.chart_hover_border,
            font=dict(family=APP_FONT_FAMILY, size=13, color="#FFFFFF"),
        ),
        legend=dict(font=dict(size=13), itemclick="toggleothers", itemdoubleclick="toggle"),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=theme.chart_grid,
        zerolinecolor=theme.chart_zero,
        tickfont=dict(size=12),
        title_font=dict(size=13),
        automargin=True,
    )
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12), title_font=dict(size=13), automargin=True)
    return fig


def _allocation_source_rows(metrics: PortfolioMetrics, *, include_cash: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    total = metrics.total_value_krw if include_cash else metrics.total_position_value_krw
    for item in metrics.rows:
        if item.market_value_krw is None or item.market_value_krw <= 0:
            continue
        label = instrument_label(item.holding)
        rows.append(
            {
                "ticker": str(item.holding["ticker"]),
                "display_name": str(item.holding["display_name"]),
                "label": label,
                "legend_label": instrument_label(item.holding, include_ticker=True),
                "market": str(item.holding["market"]),
                "market_value_krw": item.market_value_krw,
                "weight": item.market_value_krw / total if total else 0.0,
                "day_change_krw": item.day_change_krw,
                "day_change_pct": item.day_change_pct,
                "total_pnl_pct": item.total_pnl_pct,
                "color_key": str(item.holding["ticker"]),
            }
        )
    if include_cash and metrics.cash_total_krw > 0:
        rows.append(
            {
                "ticker": "현금",
                "display_name": "현금",
                "label": "현금",
                "legend_label": "현금",
                "market": "KRW/USD",
                "market_value_krw": metrics.cash_total_krw,
                "weight": metrics.cash_total_krw / total if total else 0.0,
                "day_change_krw": 0.0,
                "day_change_pct": None,
                "total_pnl_pct": None,
                "color_key": "CASH",
            }
        )
    return sorted(rows, key=lambda row: float(row["market_value_krw"]), reverse=True)


def _collapse_small_allocation_rows(rows: list[dict[str, object]], *, max_slices: int, min_weight: float) -> list[dict[str, object]]:
    if len(rows) <= max_slices and all(float(row["weight"]) >= min_weight for row in rows):
        return rows
    keep: list[dict[str, object]] = []
    other: list[dict[str, object]] = []
    kept_non_cash = 0
    for row in rows:
        if row["ticker"] == "현금":
            keep.append(row)
        elif kept_non_cash < max_slices and float(row["weight"]) >= min_weight:
            keep.append(row)
            kept_non_cash += 1
        else:
            other.append(row)
    if other:
        other_value = sum(float(row["market_value_krw"]) for row in other)
        other_day_change = sum(float(row["day_change_krw"] or 0.0) for row in other)
        keep.append(
            {
                "ticker": "기타",
                "display_name": f"{len(other)}개 종목 합산",
                "label": "기타",
                "legend_label": f"기타 · {len(other)}개 종목",
                "market": "-",
                "market_value_krw": other_value,
                "weight": other_value / sum(float(row["market_value_krw"]) for row in rows),
                "day_change_krw": other_day_change,
                "day_change_pct": None,
                "total_pnl_pct": None,
                "color_key": "OTHER",
            }
        )
    return keep


def plot_allocation(
    metrics: PortfolioMetrics,
    *,
    max_slices: int = 8,
    min_label_weight: float = 0.035,
    include_cash: bool = True,
) -> go.Figure | None:
    theme = get_active_theme()
    source_rows = _allocation_source_rows(metrics, include_cash=include_cash)
    if not source_rows:
        return None
    rows = _collapse_small_allocation_rows(source_rows, max_slices=max_slices, min_weight=min_label_weight)
    values = [float(row["market_value_krw"]) for row in rows]
    legend_labels = [str(row["legend_label"]) for row in rows]
    text = [
        f"{row['label']}<br><b>{percentage(float(row['weight']))}</b>"
        if float(row["weight"]) >= min_label_weight or row["ticker"] in {"기타", "현금"}
        else ""
        for row in rows
    ]
    colors = [
        SEMANTIC_COLORS["cash"]
        if row["ticker"] == "현금"
        else SEMANTIC_COLORS["missing"]
        if row["ticker"] == "기타"
        else deterministic_color(row["color_key"])
        for row in rows
    ]
    customdata = [
        [
            row["label"],
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
    hovertext = [
        (
            f"<b>{escape(str(row['label']))}</b><br>"
            f"티커 {escape(str(row['ticker']))} · 시장 {escape(str(row['market']))}<br>"
            f"평가액 {escape(full_krw(float(row['market_value_krw'])))}<br>"
            f"비중 {escape(percentage(float(row['weight'])))}<br>"
            f"오늘 변동 {escape(signed_krw(row['day_change_krw']))} ({escape(signed_percentage(row['day_change_pct']))})<br>"
            f"총수익률 {escape(signed_percentage(row['total_pnl_pct']))}"
        )
        for row in rows
    ]
    fig = go.Figure(
        go.Pie(
            labels=legend_labels,
            values=values,
            domain=dict(x=[0.08, 0.92], y=[0.02, 0.98]),
            hole=0.58,
            sort=False,
            text=text,
            textinfo="text",
            textposition="inside",
            insidetextorientation="radial",
            textfont=dict(size=12, family=APP_FONT_FAMILY),
            customdata=customdata,
            hovertext=hovertext,
            marker=dict(colors=colors, line=dict(color=theme.border_strong, width=1)),
            pull=[0.025 if index == 0 else 0 for index, _ in enumerate(rows)],
            hovertemplate="%{hovertext}<extra></extra>",
        )
    )
    fig.update_layout(
        annotations=[
            dict(
                text=f"{'총자산' if include_cash else '투자자산'}<br><b>{compact_krw(metrics.total_value_krw if include_cash else metrics.total_position_value_krw)}</b>",
                x=0.5,
                y=0.5,
                showarrow=False,
                font=dict(size=16, family=APP_FONT_FAMILY, color=theme.text),
            )
        ],
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        uniformtext=dict(minsize=12, mode="hide"),
    )
    fig = apply_chart_layout(fig, height=DIMENSIONS.tall_height + 70, hovermode="closest")
    fig.update_layout(margin=dict(l=18, r=18, t=28, b=130))
    return fig


def plot_contribution(metrics: PortfolioMetrics, *, limit: int = 10, show_all: bool = False) -> go.Figure | None:
    rows = [
        {
            "label": instrument_label(item.holding),
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
    customdata = [
        [row["display_name"], row["ticker"], full_krw(float(row["day_change_krw"])), signed_percentage(row["day_change_pct"])]
        for row in selected
    ]
    height = max(DIMENSIONS.compact_height, 110 + len(selected) * DIMENSIONS.row_height)
    fig = go.Figure(
        go.Bar(
            x=x_values,
            y=y_values,
            orientation="h",
            marker_color=[signed_color(value) for value in x_values],
            text=[signed_krw(value) for value in x_values],
            textposition="outside",
            textfont=dict(size=13, family=APP_FONT_FAMILY),
            cliponaxis=False,
            customdata=customdata,
            hovertemplate="<b>%{y}</b><br>티커 %{customdata[1]}<br>변동액 %{customdata[2]}<br>변동률 %{customdata[3]}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_color="rgba(100,116,139,0.65)", line_width=1)
    fig.update_layout(xaxis_title="오늘 변동액", yaxis_title="", bargap=0.32)
    fig.update_xaxes(tickformat=",.0f", tickprefix="₩")
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
                marker=dict(color=CURRENCY_COLORS[currency], line=dict(color="rgba(255,255,255,0.75)", width=1)),
                text=[f"{currency}<br>{percentage(ratio)}"],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(size=14, family=APP_FONT_FAMILY, color="#FFFFFF"),
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
    if is_all_zero_series(total_values + position_values + cash_values):
        return None
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
            line=dict(color=SEMANTIC_COLORS["primary"], width=3.0, shape="spline", smoothing=0.35),
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
            line=dict(color=SEMANTIC_COLORS["secondary"], width=1.8, dash="dot"),
            hovertemplate="투자자산 ₩%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=cash_values,
            name="총현금",
            mode="lines",
            line=dict(color=SEMANTIC_COLORS["cash"], width=1.8, dash="dot"),
            hovertemplate="총현금 ₩%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="KRW", xaxis_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    fig.update_yaxes(tickformat=",.0f", tickprefix="₩")
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")


def plot_transaction_cashflow(transactions: list[dict[str, object]], *, usd_krw: float) -> go.Figure | None:
    rows = transaction_cashflow_rows(transactions, usd_krw=usd_krw)
    if not rows:
        return None
    x_values = [row["date"] for row in rows]
    net_values = [float(row["net_delta_krw"]) for row in rows]
    cumulative_values = [float(row["cumulative_net_invested_krw"]) for row in rows]
    if is_all_zero_series(net_values + cumulative_values):
        return None
    customdata = [
        [
            full_krw(float(row["buy_amount_krw"])),
            full_krw(float(row["sell_amount_krw"])),
            full_krw(float(row["net_delta_krw"])),
            full_krw(float(row["cumulative_net_invested_krw"])),
            f"매입 {int(row['buy_count'])}건 · 매도 {int(row['sell_count'])}건",
        ]
        for row in rows
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x_values,
            y=net_values,
            name="일별 순매입",
            marker_color=[signed_color(value) for value in net_values],
            customdata=customdata,
            hovertemplate=(
                "%{x}<br>"
                "%{customdata[4]}<br>"
                "매입 %{customdata[0]}<br>"
                "매도 %{customdata[1]}<br>"
                "순매입 %{customdata[2]}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=cumulative_values,
            name="누적 순매입",
            mode="lines+markers",
            line=dict(color=SEMANTIC_COLORS["primary"], width=3.0, shape="spline", smoothing=0.25),
            marker=dict(size=6),
            customdata=customdata,
            hovertemplate="%{x}<br>누적 순매입 %{customdata[3]}<extra></extra>",
            yaxis="y2",
        )
    )
    fig.add_hline(y=0, line_color="rgba(100,116,139,0.55)", line_width=1)
    fig.update_layout(
        xaxis_title="거래일",
        yaxis=dict(title="일별 순매입", tickformat=",.0f", tickprefix="₩"),
        yaxis2=dict(title="누적 순매입", overlaying="y", side="right", tickformat=",.0f", tickprefix="₩"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")


def plot_reconstructed_total_value(result: ReconstructionResult, *, include_cash: bool = True) -> go.Figure | None:
    if not result.daily_rows:
        return None
    x_values = [row.date for row in result.daily_rows]
    y_values = [row.total_value_krw if include_cash else row.position_value_krw for row in result.daily_rows]
    if len(y_values) < 2 or is_all_zero_series(y_values):
        return None
    customdata = [
        [
            row.date.isoformat(),
            full_krw(row.total_value_krw),
            full_krw(row.position_value_krw),
            full_krw(row.cash_total_krw),
            f"{row.usd_krw:,.2f}",
            row.applied_snapshot_date.isoformat(),
            row.priced_count,
            row.missing_price_count,
        ]
        for row in result.daily_rows
    ]
    fig = go.Figure(
        go.Scatter(
            x=x_values,
            y=y_values,
            name="총자산" if include_cash else "투자자산",
            mode="lines+markers" if len(x_values) <= 12 else "lines",
            line=dict(color=SEMANTIC_COLORS["primary"], width=3.0, shape="spline", smoothing=0.35),
            marker=dict(size=6 if len(x_values) <= 12 else 0),
            fill="tozeroy",
            fillcolor="rgba(37,99,235,0.12)",
            customdata=customdata,
            hovertemplate=(
                "%{customdata[0]}<br>"
                "총자산 %{customdata[1]}<br>"
                "투자자산 %{customdata[2]}<br>"
                "현금 %{customdata[3]}<br>"
                "USD/KRW %{customdata[4]}<br>"
                "적용 스냅샷 %{customdata[5]}<br>"
                "평가 가능 %{customdata[6]} · 가격 누락 %{customdata[7]}<extra></extra>"
            ),
        )
    )
    for marker in sorted({row.applied_snapshot_date for row in result.daily_rows}):
        fig.add_vline(x=marker, line_color="rgba(217,119,6,0.55)", line_width=1, line_dash="dot")
    fig.update_layout(yaxis_title="KRW", xaxis_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    fig.update_yaxes(tickformat=",.0f", tickprefix="₩")
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")


def plot_reconstructed_holdings_area(result: ReconstructionResult, *, top_n: int = 8) -> go.Figure | None:
    rows = build_ticker_value_series(result, top_n=top_n)
    if not rows:
        return None
    dates = sorted({row["date"] for row in rows})
    tickers = sorted({str(row["ticker"]) for row in rows}, key=lambda ticker: (ticker == "기타", ticker))
    value_by_key = {(str(row["date"]), str(row["ticker"])): float(row["market_value_krw"]) for row in rows}
    if is_all_zero_series(value_by_key.values()):
        return None
    display_names = {str(row["ticker"]): str(row["display_name"]) for row in rows}
    detail_by_key = {
        (str(row["date"]), str(row["ticker"])): [
            str(row["display_name"]),
            "" if row.get("quantity") is None else format_number(float(row["quantity"]), digits=4, trim=True),
            "" if row.get("close_price") is None else format_price(float(row["close_price"]), row.get("currency")),
            full_krw(float(row["market_value_krw"])),
        ]
        for row in rows
    }
    fig = go.Figure()
    for ticker in tickers:
        values = [value_by_key.get((current, ticker), 0.0) for current in dates]
        customdata = [detail_by_key.get((current, ticker), [display_names.get(ticker, ticker), "", "", full_krw(0)]) for current in dates]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=values,
                name=str(display_names.get(ticker, ticker)) if str(display_names.get(ticker, ticker)) != ticker else ticker,
                mode="lines",
                stackgroup="one",
                line=dict(width=1.1, color=SEMANTIC_COLORS["missing"] if ticker == "기타" else deterministic_color(ticker)),
                customdata=customdata,
                hovertemplate=(
                    f"<b>%{{customdata[0]}}</b><br>"
                    f"티커 {ticker}<br>"
                    "%{x}<br>"
                    "수량 %{customdata[1]}<br>"
                    "종가 %{customdata[2]}<br>"
                    "평가액 %{customdata[3]}<extra></extra>"
                ),
            )
        )
    fig.update_layout(yaxis_title="KRW", xaxis_title="", legend=dict(orientation="h", yanchor="bottom", y=-0.24, x=0))
    fig.update_yaxes(tickformat=",.0f")
    fig = apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")
    fig.update_layout(margin=dict(l=20, r=20, t=28, b=80))
    return fig
