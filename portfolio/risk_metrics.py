from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any


MIN_BETA_OBSERVATIONS = 20


@dataclass(frozen=True)
class ValuePoint:
    date: date
    value: float


@dataclass(frozen=True)
class DrawdownPoint:
    date: date | None
    value: float
    running_peak: float
    drawdown: float


@dataclass(frozen=True)
class MDDResult:
    max_drawdown: float
    peak_date: date | None
    trough_date: date | None
    recovery_date: date | None
    current_drawdown: float
    observations: int
    series: list[DrawdownPoint]


@dataclass(frozen=True)
class ReturnObservation:
    date: date | None
    portfolio_return: float
    benchmark_return: float


@dataclass(frozen=True)
class BetaResult:
    beta: float
    r_squared: float | None
    observations: int
    start_date: date | None
    end_date: date | None


def _to_finite_float(value: object, *, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _to_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        raise ValueError("date is required")
    return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def normalize_value_series(rows: Iterable[ValuePoint | Mapping[str, Any] | tuple[Any, Any]]) -> list[ValuePoint]:
    points: list[ValuePoint] = []
    for index, row in enumerate(rows, start=1):
        if isinstance(row, ValuePoint):
            point = row
        elif isinstance(row, Mapping):
            raw_date = row.get("date") or row.get("captured_at") or row.get("timestamp")
            raw_value = row.get("value")
            if raw_value is None:
                raw_value = row.get("total_value_krw")
            point = ValuePoint(date=_to_date(raw_date), value=_to_finite_float(raw_value, field_name=f"value row {index}"))
        else:
            raw_date, raw_value = row
            point = ValuePoint(date=_to_date(raw_date), value=_to_finite_float(raw_value, field_name=f"value row {index}"))
        if point.value <= 0:
            continue
        points.append(point)
    latest_by_date: dict[date, ValuePoint] = {}
    for point in points:
        latest_by_date[point.date] = point
    return [latest_by_date[current] for current in sorted(latest_by_date)]


def value_series_from_history_records(records: Iterable[Any]) -> list[ValuePoint]:
    rows = []
    for record in records:
        rows.append(
            {
                "date": getattr(record, "captured_at", None),
                "value": getattr(record, "total_value_krw", None),
            }
        )
    return normalize_value_series(rows)


def value_series_from_reconstruction_result(result: object | None) -> list[ValuePoint]:
    daily_rows = getattr(result, "daily_rows", None)
    if not daily_rows:
        return []
    rows = []
    for row in daily_rows:
        rows.append({"date": getattr(row, "date", None), "value": getattr(row, "total_value_krw", None)})
    return normalize_value_series(rows)


def filter_value_series_by_days(series: Iterable[ValuePoint], days: int | None, *, today: date | None = None) -> list[ValuePoint]:
    values = list(series)
    if days is None:
        return values
    current = today or date.today()
    start = current - timedelta(days=days)
    return [point for point in values if point.date >= start]


def calculate_drawdown_series(values: Iterable[float], dates: Iterable[object] | None = None) -> list[DrawdownPoint]:
    value_list = [_to_finite_float(value, field_name="value") for value in values]
    if dates is None:
        date_list: list[date | None] = [None] * len(value_list)
    else:
        date_list = [_to_date(value) for value in dates]
    if len(value_list) != len(date_list):
        raise ValueError("values and dates must have the same length")
    if not value_list:
        return []

    peak = None
    rows: list[DrawdownPoint] = []
    for value, current_date in zip(value_list, date_list, strict=True):
        if value <= 0:
            raise ValueError("values must be positive")
        peak = value if peak is None else max(peak, value)
        drawdown = value / peak - 1.0
        rows.append(DrawdownPoint(date=current_date, value=value, running_peak=peak, drawdown=drawdown))
    return rows


def calculate_mdd(values: Iterable[float], dates: Iterable[object] | None = None) -> MDDResult:
    series = calculate_drawdown_series(values, dates)
    if len(series) < 2:
        raise ValueError("MDD requires at least two positive observations")

    trough_index, trough = min(enumerate(series), key=lambda item: item[1].drawdown)
    peak_value = trough.running_peak
    peak_index = next(index for index in range(trough_index, -1, -1) if series[index].value == peak_value)
    recovery_date = None
    for point in series[trough_index + 1 :]:
        if point.value >= peak_value:
            recovery_date = point.date
            break
    return MDDResult(
        max_drawdown=trough.drawdown,
        peak_date=series[peak_index].date,
        trough_date=trough.date,
        recovery_date=recovery_date,
        current_drawdown=series[-1].drawdown,
        observations=len(series),
        series=series,
    )


def pct_change_series(series: Iterable[ValuePoint]) -> dict[date, float]:
    values = list(series)
    returns: dict[date, float] = {}
    for previous, current in zip(values, values[1:], strict=False):
        if previous.value <= 0:
            continue
        returns[current.date] = current.value / previous.value - 1.0
    return returns


def _normalize_return_mapping(values: Mapping[Any, Any]) -> dict[date, float]:
    return {_to_date(key): _to_finite_float(value, field_name="return") for key, value in values.items()}


def _normalize_return_sequence(values: Sequence[Any]) -> dict[int, float]:
    return {index: _to_finite_float(value, field_name="return") for index, value in enumerate(values)}


def align_return_series(
    portfolio_returns: Mapping[Any, Any] | Sequence[Any],
    benchmark_returns: Mapping[Any, Any] | Sequence[Any],
) -> list[ReturnObservation]:
    if isinstance(portfolio_returns, Mapping) and isinstance(benchmark_returns, Mapping):
        portfolio = _normalize_return_mapping(portfolio_returns)
        benchmark = _normalize_return_mapping(benchmark_returns)
        common_dates = sorted(set(portfolio) & set(benchmark))
        return [ReturnObservation(date=current, portfolio_return=portfolio[current], benchmark_return=benchmark[current]) for current in common_dates]
    if isinstance(portfolio_returns, Mapping) != isinstance(benchmark_returns, Mapping):
        raise ValueError("portfolio_returns and benchmark_returns must both be mappings or both be sequences")

    portfolio_sequence = _normalize_return_sequence(portfolio_returns)  # type: ignore[arg-type]
    benchmark_sequence = _normalize_return_sequence(benchmark_returns)  # type: ignore[arg-type]
    common_indexes = sorted(set(portfolio_sequence) & set(benchmark_sequence))
    return [
        ReturnObservation(date=None, portfolio_return=portfolio_sequence[index], benchmark_return=benchmark_sequence[index])
        for index in common_indexes
    ]


def calculate_beta(
    portfolio_returns: Mapping[Any, Any] | Sequence[Any],
    benchmark_returns: Mapping[Any, Any] | Sequence[Any],
    *,
    min_observations: int = MIN_BETA_OBSERVATIONS,
) -> BetaResult:
    observations = align_return_series(portfolio_returns, benchmark_returns)
    if len(observations) < min_observations:
        raise ValueError(f"Beta requires at least {min_observations} aligned observations")

    portfolio_values = [row.portfolio_return for row in observations]
    benchmark_values = [row.benchmark_return for row in observations]
    portfolio_mean = sum(portfolio_values) / len(portfolio_values)
    benchmark_mean = sum(benchmark_values) / len(benchmark_values)
    benchmark_deviation = [value - benchmark_mean for value in benchmark_values]
    portfolio_deviation = [value - portfolio_mean for value in portfolio_values]
    benchmark_variance = sum(value * value for value in benchmark_deviation)
    if benchmark_variance == 0:
        raise ValueError("benchmark return variance is zero")

    covariance = sum(portfolio_delta * benchmark_delta for portfolio_delta, benchmark_delta in zip(portfolio_deviation, benchmark_deviation, strict=True))
    beta = covariance / benchmark_variance
    portfolio_variance = sum(value * value for value in portfolio_deviation)
    r_squared = None
    if portfolio_variance > 0:
        correlation = covariance / math.sqrt(portfolio_variance * benchmark_variance)
        r_squared = correlation * correlation

    dated = [row.date for row in observations if row.date is not None]
    return BetaResult(
        beta=beta,
        r_squared=r_squared,
        observations=len(observations),
        start_date=min(dated) if dated else None,
        end_date=max(dated) if dated else None,
    )
