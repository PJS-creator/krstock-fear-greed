from __future__ import annotations

from datetime import date

from app.ui.chart_analysis import chart_analysis_table_rows
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

