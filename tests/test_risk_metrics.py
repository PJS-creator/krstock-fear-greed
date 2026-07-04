from datetime import date
from types import SimpleNamespace

import pytest

from portfolio.risk_metrics import (
    ValuePoint,
    align_return_series,
    calculate_beta,
    calculate_drawdown_series,
    calculate_mdd,
    pct_change_series,
    value_series_from_history_records,
    value_series_from_reconstruction_result,
)


def test_mdd_calculates_maximum_drawdown_from_running_peak():
    values = [100, 120, 90, 95, 130]
    dates = [date(2026, 1, day) for day in range(1, 6)]

    result = calculate_mdd(values, dates)

    assert [round(row.running_peak, 6) for row in result.series] == [100, 120, 120, 120, 130]
    assert result.max_drawdown == pytest.approx(-0.25)
    assert result.peak_date == date(2026, 1, 2)
    assert result.trough_date == date(2026, 1, 3)
    assert result.recovery_date == date(2026, 1, 5)
    assert result.current_drawdown == pytest.approx(0.0)


def test_drawdown_series_rejects_non_positive_values():
    with pytest.raises(ValueError, match="positive"):
        calculate_drawdown_series([100, 0, 90])


def test_beta_is_two_when_portfolio_moves_twice_benchmark():
    benchmark_returns = [0.01, -0.02, 0.015, 0.003, -0.004, 0.02, -0.01, 0.006, 0.012, -0.007]
    portfolio_returns = [value * 2 for value in benchmark_returns]

    result = calculate_beta(portfolio_returns, benchmark_returns, min_observations=5)

    assert result.beta == pytest.approx(2.0)
    assert result.r_squared == pytest.approx(1.0)
    assert result.observations == len(benchmark_returns)


def test_beta_aligns_returns_by_inner_joined_dates():
    portfolio_returns = {
        date(2026, 1, 2): 0.02,
        date(2026, 1, 3): 0.04,
        date(2026, 1, 4): 0.06,
    }
    benchmark_returns = {
        date(2026, 1, 1): 0.01,
        date(2026, 1, 2): 0.01,
        date(2026, 1, 3): 0.02,
        date(2026, 1, 4): 0.03,
    }

    aligned = align_return_series(portfolio_returns, benchmark_returns)
    result = calculate_beta(portfolio_returns, benchmark_returns, min_observations=3)

    assert [row.date for row in aligned] == [date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4)]
    assert result.beta == pytest.approx(2.0)
    assert result.start_date == date(2026, 1, 2)
    assert result.end_date == date(2026, 1, 4)


def test_pct_change_series_uses_daily_value_points():
    returns = pct_change_series(
        [
            ValuePoint(date(2026, 1, 1), 100),
            ValuePoint(date(2026, 1, 2), 110),
            ValuePoint(date(2026, 1, 3), 99),
        ]
    )

    assert returns[date(2026, 1, 2)] == pytest.approx(0.1)
    assert returns[date(2026, 1, 3)] == pytest.approx(-0.1)


def test_value_series_from_history_records_keeps_latest_record_per_day():
    records = [
        SimpleNamespace(captured_at="2026-01-01T00:00:00+00:00", total_value_krw=100),
        SimpleNamespace(captured_at="2026-01-01T09:00:00+00:00", total_value_krw=110),
        SimpleNamespace(captured_at="2026-01-02T00:00:00+00:00", total_value_krw=120),
    ]

    series = value_series_from_history_records(records)

    assert series == [ValuePoint(date(2026, 1, 1), 110), ValuePoint(date(2026, 1, 2), 120)]


def test_value_series_from_reconstruction_result_uses_daily_rows():
    result = SimpleNamespace(
        daily_rows=[
            SimpleNamespace(date=date(2026, 1, 1), total_value_krw=100),
            SimpleNamespace(date=date(2026, 1, 2), total_value_krw=120),
        ]
    )

    assert value_series_from_reconstruction_result(result) == [
        ValuePoint(date(2026, 1, 1), 100),
        ValuePoint(date(2026, 1, 2), 120),
    ]
