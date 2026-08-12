from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from html import escape

import pandas as pd
import streamlit as st

from app.ui.components import render_empty_state
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
ATTENTION_SCORE_THRESHOLD = 70.0
ATTENTION_DELTA_THRESHOLD = 14.0
_ELEVATED_SCORE_THRESHOLD = 50.0
_MAX_ATTENTION_CARDS = 3
_SORT_LABELS = {
    "attention": "주목 변화순",
    "top_score": "고점점수 높은순",
    "bottom_score": "저점점수 높은순",
}
_WARNING_LABELS = {
    "APPROXIMATED_TRADED_VALUE": "거래대금 추정값 사용",
    "ZERO_VOLUME_SESSION_PRESENT": "거래량 0 세션 포함",
    "SPLIT_EVENTS_UNAVAILABLE": "분할 이벤트 확인 불가",
    "PROVIDER_ADJUSTMENT_UNVERIFIED": "공급원 조정 기준 미확인",
    "NO_COMPLETED_SESSION": "완료 일봉 없음",
    "KIS_DAILY_FALLBACK": "KIS 일봉 실패로 대체 출처 사용",
}
_TOP_COMPONENT_LABELS = {
    "A1": "최근 고점 경과일",
    "A2": "고점 전 선행 상승폭",
    "A3": "고점 대비 하락 진행률",
    "A4": "하락 진행 속도",
    "A5": "3일 표준화 수익률",
    "A6": "EMA5 하회",
    "A7": "하락일 거래대금 비중",
}


@dataclass(frozen=True)
class ScoreSignal:
    score: float | None
    delta: float | None
    recent: tuple[tuple[date, float], ...]
    emphasis: str
    label: str
    priority: int


@dataclass(frozen=True)
class ChartAnalysisView:
    result: ChartAnalysisResult
    top: ScoreSignal
    bottom: ScoreSignal
    priority: int
    attention_level: str
    attention_label: str


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


def build_chart_analysis_views(results: Iterable[ChartAnalysisResult]) -> tuple[ChartAnalysisView, ...]:
    views: list[ChartAnalysisView] = []
    for result in results:
        top = _score_signal(result, score_name="top_score", delta=result.top_delta)
        bottom = _score_signal(result, score_name="bottom_score", delta=result.bottom_delta)
        priority = max(top.priority, bottom.priority)
        labels: list[str] = []
        if top.priority >= 2:
            labels.append(f"고점 {top.label}")
        if bottom.priority >= 2:
            labels.append(f"저점 {bottom.label}")
        attention_level = {
            4: "urgent",
            3: "surge",
            2: "high",
            1: "elevated",
        }.get(priority, "normal")
        views.append(
            ChartAnalysisView(
                result=result,
                top=top,
                bottom=bottom,
                priority=priority,
                attention_level=attention_level,
                attention_label=" · ".join(labels) if labels else "일반 범위",
            )
        )
    return sort_chart_analysis_views(views, sort_mode="attention")


def sort_chart_analysis_views(
    views: Iterable[ChartAnalysisView],
    *,
    sort_mode: str,
) -> tuple[ChartAnalysisView, ...]:
    items = tuple(views)
    if sort_mode == "top_score":
        key = lambda view: (
            view.top.score is None,
            -(view.top.score or 0.0),
            -(view.top.delta or 0.0),
            -view.priority,
            view.result.instrument.display_name,
        )
    elif sort_mode == "bottom_score":
        key = lambda view: (
            view.bottom.score is None,
            -(view.bottom.score or 0.0),
            -(view.bottom.delta or 0.0),
            -view.priority,
            view.result.instrument.display_name,
        )
    else:
        key = lambda view: (
            -view.priority,
            -max(view.top.delta or 0.0, view.bottom.delta or 0.0),
            -max(view.top.score or 0.0, view.bottom.score or 0.0),
            view.result.instrument.display_name,
        )
    return tuple(sorted(items, key=key))


def _score_signal(result: ChartAnalysisResult, *, score_name: str, delta: float | None) -> ScoreSignal:
    latest = result.latest
    score = float(getattr(latest, score_name)) if latest is not None else None
    recent = tuple(
        (snapshot.as_of_session, float(getattr(snapshot, score_name)))
        for snapshot in result.recent
    )
    if score is None:
        return ScoreSignal(None, delta, recent, "missing", "산출 불가", -1)
    high = score >= ATTENTION_SCORE_THRESHOLD
    surge = delta is not None and delta >= ATTENTION_DELTA_THRESHOLD
    if high and surge:
        return ScoreSignal(score, delta, recent, "urgent", "높음·급상승", 4)
    if surge:
        return ScoreSignal(score, delta, recent, "surge", "급상승", 3)
    if high:
        return ScoreSignal(score, delta, recent, "high", "높음", 2)
    if score >= _ELEVATED_SCORE_THRESHOLD or (delta is not None and delta > 0):
        return ScoreSignal(score, delta, recent, "elevated", "관찰", 1)
    return ScoreSignal(score, delta, recent, "normal", "일반", 0)


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


def _render_results_table(views: tuple[ChartAnalysisView, ...]) -> tuple[ChartAnalysisView, ...]:
    title_col, sort_col = st.columns([3, 2], vertical_alignment="bottom")
    with title_col:
        st.markdown("#### 전체 종목 점수")
    with sort_col:
        sort_mode = st.selectbox(
            "정렬 기준",
            tuple(_SORT_LABELS),
            format_func=_SORT_LABELS.__getitem__,
            key="chart_analysis_sort_mode",
        )
    sorted_views = sort_chart_analysis_views(views, sort_mode=sort_mode)
    st.caption(
        f"{_SORT_LABELS[sort_mode]}으로 표시합니다. 최근 5일 점수는 막대 위 숫자로 확인할 수 있습니다."
    )
    header = (
        "<div class='chart-analysis-table-head' aria-hidden='true'>"
        "<span>종목</span><span>고점 근거</span><span>저점 근거</span><span>판정</span>"
        "</div>"
    )
    rows = "".join(_result_row_html(view) for view in sorted_views)
    st.markdown(
        f"<div class='chart-analysis-table' role='table' aria-label='보유종목 차트분석 결과'>{header}{rows}</div>",
        unsafe_allow_html=True,
    )
    return sorted_views


def _result_row_html(view: ChartAnalysisView) -> str:
    result = view.result
    latest = result.latest
    session = latest.as_of_session.isoformat() if latest is not None else "기준일 없음"
    status = _data_status(result)
    status_tone = _data_status_tone(result)
    attention_badge = ""
    if view.priority >= 2:
        attention_badge = (
            f"<span class='chart-attention-badge chart-attention-{view.attention_level}'>"
            f"{escape(view.attention_label)}</span>"
        )
    verdict = latest.verdict if latest is not None else "산출 불가"
    return (
        f"<article class='chart-analysis-row chart-analysis-row-{view.attention_level}' role='row'>"
        "<div class='chart-analysis-asset' role='cell'>"
        f"<div class='chart-analysis-name'>{escape(result.instrument.display_name)}</div>"
        f"<div class='chart-analysis-meta'>{escape(result.instrument.market)} · {escape(session)}</div>"
        f"{attention_badge}"
        "</div>"
        f"{_score_block_html(view.top, axis='top', label='고점점수')}"
        f"{_score_block_html(view.bottom, axis='bottom', label='저점점수')}"
        "<div class='chart-analysis-verdict' role='cell'>"
        "<span class='chart-analysis-cell-label'>판정결과</span>"
        f"<strong>{escape(verdict)}</strong>"
        f"<span class='chart-data-status chart-data-status-{status_tone}'>{escape(status)}</span>"
        "</div>"
        "</article>"
    )


def _score_block_html(signal: ScoreSignal, *, axis: str, label: str) -> str:
    if signal.score is None:
        return (
            f"<div class='chart-score-block chart-score-{axis}' role='cell'>"
            f"<span class='chart-analysis-cell-label'>{escape(label)}</span>"
            "<strong class='chart-score-missing'>-</strong>"
            "<span class='chart-score-delta chart-score-delta-neutral'>비교 불가</span>"
            "</div>"
        )
    score = max(0.0, min(100.0, signal.score))
    return (
        f"<div class='chart-score-block chart-score-{axis} chart-score-emphasis-{signal.emphasis}' role='cell'>"
        "<div class='chart-score-heading'>"
        f"<span class='chart-analysis-cell-label'>{escape(label)}</span>"
        f"<span class='chart-score-level'>{escape(signal.label)}</span>"
        "</div>"
        "<div class='chart-score-value-row'>"
        f"<strong class='chart-score-value'>{score:.1f}</strong>"
        f"{_delta_html(signal.delta)}"
        "</div>"
        "<div class='chart-score-meter' aria-hidden='true'>"
        f"<span style='width:{score:.2f}%'></span>"
        "</div>"
        f"{_trend_html(signal, axis=axis)}"
        "</div>"
    )


def _delta_html(delta: float | None) -> str:
    if delta is None:
        return "<span class='chart-score-delta chart-score-delta-neutral'>전일 비교 없음</span>"
    if delta > 0:
        tone = "surge" if delta >= ATTENTION_DELTA_THRESHOLD else "rise"
        return f"<span class='chart-score-delta chart-score-delta-{tone}'>▲ +{delta:.1f}</span>"
    if delta < 0:
        return f"<span class='chart-score-delta chart-score-delta-fall'>▼ {delta:.1f}</span>"
    return "<span class='chart-score-delta chart-score-delta-neutral'>변화 없음</span>"


def _trend_html(signal: ScoreSignal, *, axis: str) -> str:
    if not signal.recent:
        return "<div class='chart-score-trend-empty'>5일 추이 없음</div>"
    values = " → ".join(f"{value:.1f}" for _, value in signal.recent)
    points = "".join(
        (
            f"<span class='chart-score-trend-point' title='{session.isoformat()} · {value:.1f}'>"
            f"<span class='chart-score-trend-value'>{value:.1f}</span>"
            "<span class='chart-score-trend-track' aria-hidden='true'>"
            f"<i class='chart-score-trend-fill' style='height:{max(8.0, min(100.0, value)):.2f}%'></i>"
            "</span></span>"
        )
        for session, value in signal.recent
    )
    return (
        "<span class='chart-score-trend-label'>최근 5일 점수</span>"
        f"<div class='chart-score-trend chart-score-trend-{axis}' "
        f"aria-label='최근 5일 {escape(values)}' title='{escape(values)}'>"
        f"{points}</div>"
    )


def _render_attention_cards(views: tuple[ChartAnalysisView, ...]) -> None:
    attention = [view for view in views if view.priority >= 2][:_MAX_ATTENTION_CARDS]
    st.markdown(
        (
            "<div class='chart-analysis-section-title'>"
            "<div><strong>오늘의 주목 변화</strong>"
            f"<span>점수 {ATTENTION_SCORE_THRESHOLD:.0f} 이상 또는 전일 +{ATTENTION_DELTA_THRESHOLD:.0f}점 이상</span></div>"
            f"<span class='chart-analysis-focus-count'>{len([view for view in views if view.priority >= 2])}개</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if not attention:
        st.markdown(
            "<div class='chart-analysis-no-focus'>현재 강조 기준에 해당하는 종목이 없습니다.</div>",
            unsafe_allow_html=True,
        )
        return
    cards = "".join(_attention_card_html(view) for view in attention)
    st.markdown(f"<div class='chart-attention-grid'>{cards}</div>", unsafe_allow_html=True)


def _render_analysis_summary(
    *,
    attention_count: int,
    top_surge_count: int,
    bottom_surge_count: int,
    data_issue_count: int,
    ready_count: int,
    total_count: int,
) -> None:
    items = (
        (
            "주목 변화",
            f"{attention_count}개",
            "warning" if attention_count else "success",
            "점수 70 이상 또는 전일 대비 +14점 이상",
        ),
        (
            "고점 급상승",
            f"{top_surge_count}개",
            "warning" if top_surge_count else "neutral",
            "전일 대비 +14점 이상",
        ),
        (
            "저점 급상승",
            f"{bottom_surge_count}개",
            "warning" if bottom_surge_count else "neutral",
            "전일 대비 +14점 이상",
        ),
        (
            "데이터 점검",
            f"{data_issue_count}개",
            "warning" if data_issue_count else "success",
            f"산출 완료 {ready_count}/{total_count}",
        ),
    )
    html = "".join(
        (
            f"<div class='chart-analysis-kpi chart-analysis-kpi-{tone}' title='{escape(detail)}'>"
            f"<span>{escape(title)}</span><strong>{escape(value)}</strong><small>{escape(detail)}</small>"
            "</div>"
        )
        for title, value, tone, detail in items
    )
    st.markdown(f"<div class='chart-analysis-kpis'>{html}</div>", unsafe_allow_html=True)


def _attention_card_html(view: ChartAnalysisView) -> str:
    result = view.result
    latest = result.latest
    verdict = latest.verdict if latest is not None else "산출 불가"
    return (
        f"<article class='chart-attention-card chart-attention-card-{view.attention_level}'>"
        "<div class='chart-attention-card-head'>"
        f"<strong>{escape(result.instrument.display_name)}</strong>"
        f"<span class='chart-attention-badge chart-attention-{view.attention_level}'>{escape(view.attention_label)}</span>"
        "</div>"
        "<div class='chart-attention-score-grid'>"
        f"{_attention_axis_html(view.top, label='고점', axis='top')}"
        f"{_attention_axis_html(view.bottom, label='저점', axis='bottom')}"
        "</div>"
        f"<div class='chart-attention-verdict'>{escape(verdict)}</div>"
        "</article>"
    )


def _attention_axis_html(signal: ScoreSignal, *, label: str, axis: str) -> str:
    score = f"{signal.score:.1f}" if signal.score is not None else "-"
    return (
        f"<div class='chart-attention-axis chart-attention-axis-{axis}'>"
        f"<span>{escape(label)}점수</span><strong>{score}</strong>{_delta_html(signal.delta)}"
        "</div>"
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
                "조건": _TOP_COMPONENT_LABELS.get(component, component),
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


def _data_status_tone(result: ChartAnalysisResult) -> str:
    if result.latest is not None and result.quality_status == "PASS":
        return "success"
    if result.latest is not None or result.readiness in {"WARMUP", "READY_INELIGIBLE"}:
        return "warning"
    return "danger"


def render_chart_analysis(
    holdings: Iterable[Mapping[str, object]],
    *,
    auto_load: bool,
    kis_provider: KisDailyHistoryProvider | None = None,
) -> None:
    st.markdown("<h2 class='chart-analysis-title'>차트분석</h2>", unsafe_allow_html=True)
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
    views = build_chart_analysis_views(results)
    attention_count = sum(view.priority >= 2 for view in views)
    top_surge_count = sum(
        view.top.delta is not None and view.top.delta >= ATTENTION_DELTA_THRESHOLD
        for view in views
    )
    bottom_surge_count = sum(
        view.bottom.delta is not None and view.bottom.delta >= ATTENTION_DELTA_THRESHOLD
        for view in views
    )
    _render_analysis_summary(
        attention_count=attention_count,
        top_surge_count=top_surge_count,
        bottom_surge_count=bottom_surge_count,
        data_issue_count=warning_count + failed_count,
        ready_count=ready_count,
        total_count=len(results),
    )
    if latest_sessions:
        st.caption(f"최근 기준일 {max(latest_sessions).isoformat()}")
    _render_attention_cards(views)
    sorted_views = _render_results_table(views)
    ranked_results = tuple(view.result for view in sorted_views)
    _render_result_details(ranked_results)
    st.caption(
        "판정결과는 직전 완료봉의 raw 조건 요약입니다. 점수 증감과 5일 추이는 설명용이며, "
        "고점점수와 저점점수를 서로 빼거나 비교해 투자 방향을 정하지 않습니다."
    )
