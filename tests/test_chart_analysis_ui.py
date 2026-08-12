from __future__ import annotations

from datetime import date

from app.ui.chart_analysis import (
    ATTENTION_DELTA_THRESHOLD,
    ATTENTION_SCORE_THRESHOLD,
    build_chart_analysis_views,
    chart_analysis_table_rows,
)
from portfolio.chart_analysis import AnalysisInstrument, ChartAnalysisResult, ChartScoreSnapshot


def _snapshot(session: date, top: float, bottom: float) -> ChartScoreSnapshot:
    return ChartScoreSnapshot(
        as_of_session=session,
        top_score=top,
        bottom_score=bottom,
        top_components={f"A{index}": False for index in range(1, 8)},
        bottom_components={"drawdown": 0.0, "near_low": 0.0, "rsi": 0.0},
        top_flow_break=False,
        top_damage_observed=False,
        bottom_watch=False,
        direction_conflict=False,
        verdict="특이 조건 없음",
    )


def test_chart_analysis_table_contains_required_scores_deltas_and_five_day_trends():
    snapshots = tuple(
        _snapshot(date(2026, 8, day), top=float(day), bottom=float(day * 2))
        for day in range(1, 6)
    )
    result = ChartAnalysisResult(
        instrument=AnalysisInstrument(market="US", symbol="QURE", display_name="QURE"),
        readiness="READY_ELIGIBLE",
        quality_status="PASS",
        latest=snapshots[-1],
        previous=snapshots[-2],
        recent=snapshots,
    )

    row = chart_analysis_table_rows([result])[0]

    assert row["기준일"] == "2026-08-05"
    assert row["고점점수"] == 5.0
    assert row["고점 증감"] == 1.0
    assert row["저점점수"] == 10.0
    assert row["저점 증감"] == 2.0
    assert row["판정결과"] == "특이 조건 없음"
    assert row["최근 5일 고점점수"] == "1.00 → 2.00 → 3.00 → 4.00 → 5.00"
    assert row["최근 5일 저점점수"] == "2.00 → 4.00 → 6.00 → 8.00 → 10.00"


def _result(name: str, *, previous_top: float, top: float, previous_bottom: float, bottom: float):
    previous = _snapshot(date(2026, 8, 4), top=previous_top, bottom=previous_bottom)
    latest = _snapshot(date(2026, 8, 5), top=top, bottom=bottom)
    return ChartAnalysisResult(
        instrument=AnalysisInstrument(market="US", symbol=name, display_name=name),
        readiness="READY_ELIGIBLE",
        quality_status="PASS",
        latest=latest,
        previous=previous,
        recent=(previous, latest),
    )


def test_high_score_with_large_daily_increase_is_ranked_first():
    ordinary = _result("ORDINARY", previous_top=20.0, top=25.0, previous_bottom=15.0, bottom=20.0)
    high_only = _result(
        "HIGH",
        previous_top=ATTENTION_SCORE_THRESHOLD,
        top=ATTENTION_SCORE_THRESHOLD,
        previous_bottom=20.0,
        bottom=20.0,
    )
    urgent = _result(
        "URGENT",
        previous_top=50.0,
        top=ATTENTION_SCORE_THRESHOLD,
        previous_bottom=20.0,
        bottom=20.0,
    )

    views = build_chart_analysis_views((ordinary, high_only, urgent))

    assert [view.result.instrument.display_name for view in views] == ["URGENT", "HIGH", "ORDINARY"]
    assert views[0].attention_level == "urgent"
    assert views[0].attention_label == "고점 높음·급상승"


def test_top_and_bottom_attention_are_classified_independently():
    bottom_surge = _result(
        "BOTTOM",
        previous_top=30.0,
        top=30.0,
        previous_bottom=40.0,
        bottom=40.0 + ATTENTION_DELTA_THRESHOLD,
    )

    view = build_chart_analysis_views((bottom_surge,))[0]

    assert view.top.priority == 0
    assert view.bottom.priority == 3
    assert view.attention_label == "저점 급상승"


def test_missing_result_is_sorted_after_ready_results():
    ready = _result("READY", previous_top=10.0, top=10.0, previous_bottom=10.0, bottom=10.0)
    missing = ChartAnalysisResult(
        instrument=AnalysisInstrument(market="KR", symbol="000000", display_name="MISSING"),
        readiness="ERROR",
    )

    views = build_chart_analysis_views((missing, ready))

    assert [view.result.instrument.display_name for view in views] == ["READY", "MISSING"]
    assert views[-1].top.emphasis == "missing"
