from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd
import streamlit as st

from app.ui.components import render_empty_state, render_metric_card_grid
from app.ui.theme import DIMENSIONS
from portfolio.chart_analysis import (
    AnalysisInstrument,
    ChartAnalysisResult,
    TOP_COMPONENT_IDS,
    analyze_daily_history,
)
from portfolio.chart_analysis_data import (
    KisDailyHistoryProvider,
    fetch_daily_histories,
    holdings_to_analysis_instruments,
)


_RESULTS_KEY = "chart_analysis_results"
_SIGNATURE_KEY = "chart_analysis_holdings_signature"
_WARNING_LABELS = {
    "APPROXIMATED_TRADED_VALUE": "거래대금 추정값 사용",
    "ZERO_VOLUME_SESSION_PRESENT": "거래량 0 세션 포함",
    "SPLIT_EVENTS_UNAVAILABLE": "분할 이벤트 확인 불가",
    "PROVIDER_ADJUSTMENT_UNVERIFIED": "공급원 조정 기준 미확인",
    "NO_COMPLETED_SESSION": "완료 일봉 없음",
    "KIS_DAILY_FALLBACK": "KIS 일봉 실패로 대체 출처 사용",
}


@st.cache_data(ttl=30 * 60, show_spinner=False, max_entries=16)
def _load_chart_analysis(
    payload: tuple[tuple[str, str, str], ...],
    use_kis: bool,
    _kis_provider: KisDailyHistoryProvider | None = None,
) -> tuple[ChartAnalysisResult, ...]:
    instruments = tuple(
        AnalysisInstrument(market=market, symbol=symbol, display_name=display_name)
        for market, symbol, display_name in payload
    )
    provider = _kis_provider if use_kis else None
    return tuple(
        analyze_daily_history(history)
        for history in fetch_daily_histories(instruments, kis_provider=provider)
    )


def chart_analysis_table_rows(results: Iterable[ChartAnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        latest = result.latest
        rows.append(
            {
                "종목": result.instrument.display_name,
                "기준일": latest.as_of_session.isoformat() if latest is not None else "-",
                "고점점수": latest.top_score if latest is not None else None,
                "고점 증감": result.top_delta,
                "저점점수": latest.bottom_score if latest is not None else None,
                "저점 증감": result.bottom_delta,
                "판정결과": latest.verdict if latest is not None else "산출 불가",
                "최근 5일 고점점수": _score_trend(result, score_name="top_score"),
                "최근 5일 저점점수": _score_trend(result, score_name="bottom_score"),
                "데이터 상태": _data_status(result),
            }
        )
    return rows


def _score_trend(result: ChartAnalysisResult, *, score_name: str) -> str:
    if not result.recent:
        return "-"
    values = [float(getattr(snapshot, score_name)) for snapshot in result.recent]
    return " → ".join(f"{value:.2f}" for value in values)


def _data_status(result: ChartAnalysisResult) -> str:
    if result.latest is not None:
        return "준비 완료" if result.quality_status == "PASS" else "준비 완료 · 주의"
    if result.readiness == "WARMUP":
        return "데이터 부족"
    if result.readiness == "READY_INELIGIBLE":
        return "직전봉 부적격"
    return "조회/검증 실패"


def _payload(instruments: Iterable[AnalysisInstrument]) -> tuple[tuple[str, str, str], ...]:
    return tuple((item.market, item.symbol, item.display_name) for item in instruments)


def _render_results_table(results: tuple[ChartAnalysisResult, ...]) -> None:
    rows = chart_analysis_table_rows(results)
    frame = pd.DataFrame(rows)
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=min(DIMENSIONS.max_table_height, 92 + len(frame) * DIMENSIONS.row_height),
        column_config={
            "종목": st.column_config.TextColumn("종목", width="medium"),
            "기준일": st.column_config.TextColumn("기준일", width="small"),
            "고점점수": st.column_config.NumberColumn("고점점수", format="%.2f", width="small"),
            "고점 증감": st.column_config.NumberColumn("고점 전일증감", format="%+.2f", width="small"),
            "저점점수": st.column_config.NumberColumn("저점점수", format="%.2f", width="small"),
            "저점 증감": st.column_config.NumberColumn("저점 전일증감", format="%+.2f", width="small"),
            "판정결과": st.column_config.TextColumn("판정결과", width="medium"),
            "최근 5일 고점점수": st.column_config.TextColumn("고점점수 5일", width="large"),
            "최근 5일 저점점수": st.column_config.TextColumn("저점점수 5일", width="large"),
            "데이터 상태": st.column_config.TextColumn("상태", width="medium"),
        },
    )


def _render_result_details(results: tuple[ChartAnalysisResult, ...]) -> None:
    with st.expander("종목별 산출 근거와 데이터 품질", expanded=False):
        selected_key = st.selectbox(
            "종목",
            [result.instrument.key for result in results],
            format_func=lambda key: next(
                result.instrument.display_name for result in results if result.instrument.key == key
            ),
            key="chart_analysis_detail_symbol",
        )
        result = next(result for result in results if result.instrument.key == selected_key)
        traded_value_mode = (
            "추정 거래대금"
            if "APPROXIMATED_TRADED_VALUE" in result.warnings
            else "원자료 거래대금"
        )
        st.caption(
            f"출처 {result.provider or '-'} · 조회 심볼 {result.source_symbol or '-'} · "
            f"조정 {result.adjustment_mode or '-'} · {traded_value_mode} · "
            f"입력 {result.rows}개 · 적격 {result.eligible_rows}개"
        )
        if result.source_sha256:
            st.caption(f"원자료 해시 {result.source_sha256[:16]}…")
        if result.error:
            st.warning(result.error)
        if result.warnings:
            labels = [_warning_text(warning) for warning in result.warnings]
            st.caption("데이터 주의: " + " · ".join(labels))
        if result.latest is None:
            return
        st.markdown("**직전 완료봉 판정 근거**")
        top_rows = [
            {
                "조건": component,
                "충족": "충족" if result.latest.top_components.get(component) else "미충족",
            }
            for component in TOP_COMPONENT_IDS
        ]
        bottom_rows = [
            {"요소": "63일 고점 대비 낙폭", "기여점수": result.latest.bottom_components.get("drawdown")},
            {"요소": "20일 저점 근접도", "기여점수": result.latest.bottom_components.get("near_low")},
            {"요소": "RSI14", "기여점수": result.latest.bottom_components.get("rsi")},
        ]
        left, right = st.columns(2, gap="medium")
        with left:
            st.dataframe(pd.DataFrame(top_rows), hide_index=True, width="stretch")
        with right:
            st.dataframe(pd.DataFrame(bottom_rows), hide_index=True, width="stretch")
        st.caption(
            "고점 흐름 훼손 "
            f"{'충족' if result.latest.top_flow_break else '미충족'} · 고점 손상 관찰 "
            f"{'충족' if result.latest.top_damage_observed else '미충족'} · 저점권 투매 관찰 "
            f"{'충족' if result.latest.bottom_watch else '미충족'}"
        )


def _warning_text(value: str) -> str:
    return _WARNING_LABELS.get(value, value)


def render_chart_analysis(
    holdings: Iterable[Mapping[str, object]],
    *,
    auto_load: bool,
    kis_provider: KisDailyHistoryProvider | None = None,
) -> None:
    st.subheader("차트분석")
    st.caption(
        "현재 보유종목의 직전 완료 정규장 일봉을 동일 기준으로 분석합니다. "
        "고점·저점 점수는 서로 독립적인 근거 점수이며 매수·매도 확률이나 자동 주문 신호가 아닙니다."
    )
    instruments = holdings_to_analysis_instruments(holdings)
    if not instruments:
        render_empty_state(
            "분석할 보유종목이 없습니다.",
            "사용자입력에서 국내 또는 미국 주식 보유수량을 입력한 뒤 다시 확인하세요.",
        )
        return

    payload = _payload(instruments)
    signature = (payload, kis_provider is not None)
    if st.session_state.get(_SIGNATURE_KEY) != signature:
        st.session_state[_SIGNATURE_KEY] = signature
        st.session_state.pop(_RESULTS_KEY, None)

    action_label = "일봉 데이터 새로고침" if auto_load else "차트분석 실행"
    action_clicked = st.button(
        action_label,
        type="primary",
        icon=":material/candlestick_chart:",
        key="chart_analysis_refresh",
    )
    if action_clicked:
        _load_chart_analysis.clear()
    should_load = action_clicked or (auto_load and _RESULTS_KEY not in st.session_state)
    if should_load:
        with st.spinner(f"보유종목 {len(instruments)}개의 완료 일봉을 조회하고 있습니다..."):
            st.session_state[_RESULTS_KEY] = _load_chart_analysis(
                payload,
                kis_provider is not None,
                kis_provider,
            )

    results = st.session_state.get(_RESULTS_KEY)
    if not results:
        st.info("차트분석 실행을 누르면 보유종목 일봉을 한 번에 조회해 점수를 계산합니다.")
        return
    results = tuple(results)
    ready_count = sum(result.latest is not None for result in results)
    warning_count = sum(result.latest is not None and result.quality_status == "WARNING" for result in results)
    failed_count = len(results) - ready_count
    latest_sessions = [result.latest.as_of_session for result in results if result.latest is not None]
    render_metric_card_grid(
        [
            {"title": "분석 종목", "value": f"{len(results)}개", "status": "neutral"},
            {"title": "산출 완료", "value": f"{ready_count}개", "status": "success" if ready_count else "warning"},
            {"title": "주의/실패", "value": f"{warning_count + failed_count}개", "status": "warning" if warning_count + failed_count else "success"},
            {"title": "최근 기준일", "value": max(latest_sessions).isoformat() if latest_sessions else "-", "status": "info"},
        ]
    )
    _render_results_table(results)
    _render_result_details(results)
    st.caption(
        "판정결과는 직전 완료봉의 raw 조건 요약입니다. 점수 증감과 5일 추이는 설명용이며, "
        "고점점수와 저점점수를 서로 빼거나 비교해 투자 방향을 정하지 않습니다."
    )
