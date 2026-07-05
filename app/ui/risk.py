from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio.risk_metrics import (
    BetaResult,
    MDDResult,
    ValuePoint,
    calculate_beta,
    calculate_mdd,
    filter_value_series_by_days,
    pct_change_series,
    value_series_from_history_records,
    value_series_from_reconstruction_result,
)

from .charts import apply_chart_layout, is_all_zero_series
from .components import render_empty_state, render_plotly_chart
from .formatters import format_number, full_krw, percentage
from .stability import begin_ui_action, finish_ui_action
from .theme import DIMENSIONS, SEMANTIC_COLORS


RISK_PERIOD_DAYS = {
    "1개월": 31,
    "3개월": 93,
    "6개월": 186,
    "1년": 366,
    "전체": None,
}
YFINANCE_PERIODS = {
    "1개월": "1mo",
    "3개월": "3mo",
    "6개월": "6mo",
    "1년": "1y",
    "전체": "max",
}
BENCHMARK_SYMBOLS = {
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "S&P 500": "^GSPC",
    "NASDAQ 100": "^NDX",
    "사용자 지정 티커": "",
}
USD_BENCHMARKS = {"S&P 500", "NASDAQ 100", "사용자 지정 티커"}
MIN_BETA_OBSERVATIONS = 20
RECONSTRUCTION_RESULT_STATE_KEY = "historical_reconstruction_result"


def _date_label(value: date | None, *, empty: str = "미산정") -> str:
    return value.isoformat() if value is not None else empty


def _close_series_from_frame(frame: pd.DataFrame) -> pd.Series:
    if frame is None or frame.empty:
        raise ValueError("가격 데이터가 비어 있습니다.")
    columns = frame.columns
    if getattr(columns, "nlevels", 1) > 1:
        for level in range(columns.nlevels):
            if "Close" not in set(columns.get_level_values(level)):
                continue
            close_frame = frame.xs("Close", axis=1, level=level)
            if isinstance(close_frame, pd.DataFrame):
                if close_frame.empty:
                    break
                return close_frame.iloc[:, 0].dropna()
            return close_frame.dropna()
        raise ValueError("Close 컬럼을 찾을 수 없습니다.")
    if "Close" not in frame.columns:
        raise ValueError("Close 컬럼을 찾을 수 없습니다.")
    return frame["Close"].dropna()


def _series_from_close(close: pd.Series) -> list[ValuePoint]:
    rows = []
    for index, value in close.sort_index().items():
        try:
            current_date = index.to_pydatetime().date() if hasattr(index, "to_pydatetime") else index.date()
            number = float(value)
        except Exception:
            continue
        if number > 0:
            rows.append(ValuePoint(current_date, number))
    return rows


def _filtered_source_series(
    *,
    actual_values: list[ValuePoint],
    reconstructed_values: list[ValuePoint],
    days: int | None,
    minimum_points: int,
) -> tuple[list[ValuePoint], str]:
    actual = filter_value_series_by_days(actual_values, days)
    if len(actual) >= minimum_points:
        return actual, "저장된 실제 기록"
    reconstructed = filter_value_series_by_days(reconstructed_values, days)
    if len(reconstructed) >= minimum_points:
        return reconstructed, "과거 보유현황 재구성"
    return actual, "저장된 실제 기록"


@st.cache_data(ttl=3600, show_spinner=False)
def _load_yfinance_value_series(symbol: str, period: str) -> list[ValuePoint]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance 패키지가 설치되어 있지 않습니다.") from exc

    kwargs = {
        "period": period,
        "interval": "1d",
        "auto_adjust": False,
        "progress": False,
        "threads": False,
        "timeout": 8,
    }
    try:
        frame = yf.download(symbol, multi_level_index=False, **kwargs)
    except TypeError:
        frame = yf.download(symbol, **kwargs)
    except Exception as exc:
        raise RuntimeError(f"{symbol} 벤치마크 가격을 조회할 수 없습니다.") from exc
    return _series_from_close(_close_series_from_frame(frame))


def _apply_krw_fx(benchmark: list[ValuePoint], fx_rates: list[ValuePoint]) -> list[ValuePoint]:
    fx_by_date = {point.date: point.value for point in fx_rates}
    return [ValuePoint(point.date, point.value * fx_by_date[point.date]) for point in benchmark if point.date in fx_by_date]


def _plot_total_value(series: list[ValuePoint]) -> go.Figure | None:
    if len(series) < 2:
        return None
    if is_all_zero_series(point.value for point in series):
        return None
    fig = go.Figure(
        go.Scatter(
            x=[point.date for point in series],
            y=[point.value for point in series],
            name="총자산",
            mode="lines+markers" if len(series) <= 20 else "lines",
            line=dict(color=SEMANTIC_COLORS["primary"], width=3),
            hovertemplate="%{x}<br>총자산 ₩%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="KRW", xaxis_title="", margin=dict(l=18, r=18, t=28, b=24))
    fig.update_yaxes(tickformat=",.0f")
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")


def _plot_drawdown(result: MDDResult) -> go.Figure | None:
    if len(result.series) < 2:
        return None
    fig = go.Figure(
        go.Scatter(
            x=[point.date for point in result.series],
            y=[point.drawdown * 100 for point in result.series],
            name="Drawdown",
            mode="lines",
            fill="tozeroy",
            line=dict(color=SEMANTIC_COLORS["negative"], width=2.5),
            hovertemplate="%{x}<br>고점 대비 %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(yaxis_title="고점 대비", xaxis_title="", margin=dict(l=18, r=18, t=28, b=24))
    fig.update_yaxes(ticksuffix="%", zeroline=True)
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="x unified")


def _plot_return_scatter(portfolio_returns: dict[date, float], benchmark_returns: dict[date, float]) -> go.Figure | None:
    common_dates = sorted(set(portfolio_returns) & set(benchmark_returns))
    if len(common_dates) < 2:
        return None
    fig = go.Figure(
        go.Scatter(
            x=[benchmark_returns[current] * 100 for current in common_dates],
            y=[portfolio_returns[current] * 100 for current in common_dates],
            mode="markers",
            marker=dict(color=SEMANTIC_COLORS["primary"], size=8, opacity=0.72),
            customdata=[current.isoformat() for current in common_dates],
            hovertemplate="%{customdata}<br>벤치마크 %{x:.2f}%<br>포트폴리오 %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="벤치마크 일간 수익률",
        yaxis_title="포트폴리오 일간 수익률",
        margin=dict(l=18, r=18, t=28, b=24),
    )
    fig.update_xaxes(ticksuffix="%", zeroline=True)
    fig.update_yaxes(ticksuffix="%", zeroline=True)
    return apply_chart_layout(fig, height=DIMENSIONS.default_height, hovermode="closest")


def _render_mdd_cards(result: MDDResult) -> None:
    col1, col2, col3, col4, col5 = st.columns(5, gap="small")
    col1.metric("MDD", percentage(result.max_drawdown), help="관측 기간 중 고점 대비 최대 낙폭입니다.", border=True)
    col2.metric("현재 고점 대비", percentage(result.current_drawdown), help="마지막 기록이 직전 고점에서 얼마나 내려와 있는지입니다.", border=True)
    col3.metric("고점일", _date_label(result.peak_date), border=True)
    col4.metric("저점일", _date_label(result.trough_date), border=True)
    col5.metric("회복일", _date_label(result.recovery_date, empty="미회복"), border=True)


def _render_beta_cards(result: BetaResult, *, benchmark_label: str, basis_label: str) -> None:
    col1, col2, col3, col4 = st.columns(4, gap="small")
    col1.metric("Beta", format_number(result.beta, digits=2), help="벤치마크 일간 수익률 대비 포트폴리오 민감도입니다.", border=True)
    col2.metric("R-squared", format_number(result.r_squared, digits=2), help="벤치마크 수익률이 포트폴리오 수익률 변동을 설명한 정도입니다.", border=True)
    col3.metric("관측치 수", f"{result.observations}개", border=True)
    col4.metric("벤치마크", benchmark_label, help=basis_label, border=True)


def render_risk_analysis(*, history_records: list[object] | None, load_error: str | None = None) -> None:
    st.subheader("리스크분석")
    st.caption("MDD는 과거 관측 기간의 최대 낙폭, Beta는 선택한 벤치마크 대비 민감도입니다. 과거 지표이며 미래 손실을 보장하거나 예측하지 않습니다.")
    if load_error:
        st.warning(f"자산 기록을 불러올 수 없습니다: {load_error}")
        return
    actual_values = value_series_from_history_records(history_records or [])
    reconstructed_values = value_series_from_reconstruction_result(st.session_state.get(RECONSTRUCTION_RESULT_STATE_KEY))
    if not actual_values and not reconstructed_values:
        render_empty_state(
            "리스크를 계산할 자산 기록이 부족합니다.",
            "MDD는 최소 2개 이상의 자산 기록, Beta는 최소 20개 이상의 일간 수익률 관측치가 필요합니다.",
        )
        return

    period_label = st.selectbox("분석 기간", options=list(RISK_PERIOD_DAYS.keys()), index=3, key="risk_period")
    values, mdd_source = _filtered_source_series(
        actual_values=actual_values,
        reconstructed_values=reconstructed_values,
        days=RISK_PERIOD_DAYS[str(period_label)],
        minimum_points=2,
    )
    if len(values) < 2:
        render_empty_state(
            "선택한 기간의 기록이 부족합니다.",
            "실제 기록을 더 저장하거나 과거 보유현황 재구성을 먼저 실행하면 MDD를 계산할 수 있습니다.",
        )
        return

    try:
        mdd = calculate_mdd([point.value for point in values], [point.date for point in values])
    except ValueError as exc:
        st.warning(f"MDD를 계산할 수 없습니다: {exc}")
        return

    _render_mdd_cards(mdd)
    st.caption(f"계산 기준: {mdd_source} {mdd.observations}개, {values[0].date.isoformat()} ~ {values[-1].date.isoformat()}")
    if mdd.observations < 5:
        st.warning("관측치가 적어 MDD 해석에 주의가 필요합니다. 실제 기록이나 과거 보유현황 재구성 기간을 더 확보하면 안정적인 지표가 됩니다.")
    chart_col1, chart_col2 = st.columns(2, gap="small")
    with chart_col1:
        total_fig = _plot_total_value(values)
        if total_fig is not None:
            render_plotly_chart(total_fig, key="risk_total_value")
    with chart_col2:
        drawdown_fig = _plot_drawdown(mdd)
        if drawdown_fig is not None:
            render_plotly_chart(drawdown_fig, key="risk_drawdown")

    st.subheader("Beta")
    beta_values, beta_source = _filtered_source_series(
        actual_values=actual_values,
        reconstructed_values=reconstructed_values,
        days=RISK_PERIOD_DAYS[str(period_label)],
        minimum_points=MIN_BETA_OBSERVATIONS + 1,
    )
    portfolio_returns = pct_change_series(beta_values)
    if len(portfolio_returns) < MIN_BETA_OBSERVATIONS:
        st.warning(f"Beta 계산에는 최소 {MIN_BETA_OBSERVATIONS}개 이상의 일간 수익률 관측치가 필요합니다. 현재 {len(portfolio_returns)}개입니다.")
        return

    controls = st.columns([1, 1, 1], gap="small", vertical_alignment="bottom")
    benchmark_label = controls[0].selectbox("벤치마크", options=list(BENCHMARK_SYMBOLS.keys()), index=2, key="risk_benchmark")
    custom_symbol = ""
    if benchmark_label == "사용자 지정 티커":
        custom_symbol = controls[1].text_input("사용자 지정 티커", value="", placeholder="예: SPY, QQQ, ^KS11", key="risk_custom_benchmark")
    basis_label = controls[2].radio("비교 기준", options=["KRW 기준", "현지통화 기준"], horizontal=False, key="risk_beta_basis")

    symbol = custom_symbol.strip().upper() if benchmark_label == "사용자 지정 티커" else BENCHMARK_SYMBOLS[benchmark_label]
    if not symbol:
        st.info("사용자 지정 티커를 입력하면 Beta를 계산할 수 있습니다.")
        return
    if st.button("Beta 계산", type="primary", icon=":material/analytics:"):
        if not begin_ui_action(
            "risk_beta_calculation",
            payload={"symbol": symbol, "period": str(period_label), "basis": str(basis_label)},
            cooldown_seconds=2.0,
        ):
            return
        success = False
        period = YFINANCE_PERIODS[str(period_label)]
        try:
            try:
                benchmark_values = _load_yfinance_value_series(symbol, period)
            except Exception as exc:
                st.warning(f"벤치마크 데이터를 불러올 수 없습니다: {exc}")
                return

            actual_basis = str(basis_label)
            if basis_label == "KRW 기준" and benchmark_label in USD_BENCHMARKS:
                try:
                    fx_values = _load_yfinance_value_series("KRW=X", period)
                    benchmark_values = _apply_krw_fx(benchmark_values, fx_values)
                except Exception as exc:
                    actual_basis = "현지통화 기준"
                    st.warning(f"USD/KRW 환율 시계열을 가져오지 못해 현지통화 기준 Beta로 계산합니다: {exc}")

            benchmark_values = filter_value_series_by_days(benchmark_values, RISK_PERIOD_DAYS[str(period_label)])
            benchmark_returns = pct_change_series(benchmark_values)
            try:
                beta = calculate_beta(portfolio_returns, benchmark_returns, min_observations=MIN_BETA_OBSERVATIONS)
            except ValueError as exc:
                st.warning(f"Beta를 계산할 수 없습니다: {exc}")
                return

            _render_beta_cards(beta, benchmark_label=f"{benchmark_label} ({symbol})", basis_label=actual_basis)
            if beta.start_date and beta.end_date:
                st.caption(f"Beta 사용 기간: {beta_source}, {beta.start_date.isoformat()} ~ {beta.end_date.isoformat()}, 날짜 inner join 후 관측치 {beta.observations}개")
            scatter = _plot_return_scatter(portfolio_returns, benchmark_returns)
            if scatter is not None:
                render_plotly_chart(scatter, key="risk_beta_scatter")
            success = True
        finally:
            finish_ui_action(success=success)

    st.caption("Beta와 MDD는 사용자가 저장한 포트폴리오 기록과 무료 벤치마크 데이터를 기준으로 계산됩니다. 데이터 결측, 기간 부족, 환율 시계열 누락이 있으면 결과가 표시되지 않거나 기준이 제한됩니다.")
