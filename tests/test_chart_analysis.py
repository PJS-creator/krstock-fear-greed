from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio.chart_analysis import (
    AnalysisInstrument,
    ChartAnalysisError,
    DailyHistoryInput,
    analyze_daily_history,
    calculate_bottom_evidence_score,
    calculate_chart_score_frame,
    score_top_conditions,
    validate_daily_bars,
)


def _daily_bars(rows: int = 330) -> pd.DataFrame:
    positions = np.arange(rows, dtype=float)
    close = 100.0 + positions * 0.08 + np.sin(positions / 9.0) * 3.0
    return pd.DataFrame(
        {
            "timestamp": pd.bdate_range("2024-01-02", periods=rows),
            "open": close * 0.998,
            "high": close * 1.012,
            "low": close * 0.988,
            "close": close,
            "volume": 1_000_000.0 + (positions % 17) * 10_000.0,
        }
    )


@pytest.mark.parametrize(
    ("active_count", "expected"),
    [(0, 0.0), (1, 14.29), (6, 85.71), (7, 100.0)],
)
def test_top_score_is_discrete_seven_condition_ratio(active_count, expected):
    assert score_top_conditions([True] * active_count + [False] * (7 - active_count)) == expected


@pytest.mark.parametrize(
    ("drawdown", "near_low", "rsi", "expected_score", "expected_watch"),
    [
        (0.0, 0.20, 50.0, 0.0, False),
        (0.125, 0.10, 40.0, 50.0, False),
        (0.25, 0.04, 30.0, 94.0, True),
        (0.24, 0.0, 30.0, 98.4, False),
    ],
)
def test_bottom_score_matches_spec_examples(drawdown, near_low, rsi, expected_score, expected_watch):
    score, components, watch = calculate_bottom_evidence_score(drawdown, near_low, rsi)

    assert score == expected_score
    assert sum(components.values()) == pytest.approx(expected_score)
    assert watch is expected_watch


def test_daily_bar_validation_fails_closed_for_duplicate_sessions():
    frame = _daily_bars(10)
    frame.loc[9, "timestamp"] = frame.loc[8, "timestamp"]

    with pytest.raises(ChartAnalysisError, match="중복된 거래일"):
        validate_daily_bars(frame)


def test_chart_analysis_returns_latest_previous_and_five_day_history():
    instrument = AnalysisInstrument(market="US", symbol="TEST", display_name="테스트")
    result = analyze_daily_history(
        DailyHistoryInput(
            instrument=instrument,
            frame=_daily_bars(),
            provider="test-provider",
            adjustment_mode="SPLIT_ADJUSTED_OHLCV",
            source_symbol="TEST",
        )
    )

    assert result.readiness == "READY_ELIGIBLE"
    assert result.latest is not None
    assert result.previous is not None
    assert len(result.recent) == 5
    assert result.top_delta == round(result.latest.top_score - result.previous.top_score, 2)
    assert result.bottom_delta == round(result.latest.bottom_score - result.previous.bottom_score, 2)
    assert len(result.source_sha256) == 64


def test_chart_score_does_not_change_past_rows_when_future_rows_are_added():
    frame = _daily_bars(330)
    shorter, _ = calculate_chart_score_frame(frame.iloc[:320])
    longer, _ = calculate_chart_score_frame(frame)

    for column in ("top_score", "bottom_score", "top_flow_break", "bottom_watch", "verdict"):
        assert shorter.iloc[-1][column] == longer.iloc[319][column]


def test_analysis_requires_at_least_300_input_rows():
    instrument = AnalysisInstrument(market="KR", symbol="005930", display_name="삼성전자")
    result = analyze_daily_history(DailyHistoryInput(instrument=instrument, frame=_daily_bars(299)))

    assert result.readiness == "WARMUP"
    assert result.latest is None
    assert "300" in str(result.error)

