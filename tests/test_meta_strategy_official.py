from datetime import date, timedelta
import math

import pytest

from portfolio.meta_strategy import DatedValue
from portfolio.meta_strategy_official import (
    build_entry_advice,
    build_official_meta_strategy_signal,
    build_rsi_reference,
    build_technical_trace,
    calculate_exclusive_percentile,
    calculate_exact_liquidity_trace,
    calculate_wilder_rsi_ewm,
)


def _wednesdays(count: int, start: date = date(2018, 1, 3)) -> list[date]:
    return [start + timedelta(days=7 * index) for index in range(count)]


def _weekday_prices(count: int, *, start: date = date(2024, 1, 2), descending: bool = False) -> list[DatedValue]:
    points: list[DatedValue] = []
    candidate = start
    for index in range(count):
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        value = 500.0 - index if descending else 100.0 + index
        points.append(DatedValue(candidate, value))
        candidate += timedelta(days=1)
    return points


def test_exact_liquidity_uses_same_wednesday_zero_rrp_and_one_week_lag():
    dates = _wednesdays(330)
    net_values = [math.exp(0.0001 * index * index) + 100.0 for index in range(len(dates))]
    series = {
        "WALCL": [DatedValue(item, value * 1000.0) for item, value in zip(dates, net_values)],
        "WDTGAL": [DatedValue(item, 0.0) for item in dates],
        # A value on Thursday must not be carried back or forward into a Wednesday.
        "RRPONTSYD": [DatedValue(dates[-1] + timedelta(days=1), 999.0)],
    }

    trace = calculate_exact_liquidity_trace(
        series,
        effective_session_resolver=lambda friday: friday + timedelta(days=3),
    )

    latest = trace[-1]
    assert latest["observation_date"].weekday() == 2
    assert latest["signal_label_date"] == latest["observation_date"] + timedelta(days=2)
    assert latest["effective_from_session"] == latest["signal_label_date"] + timedelta(days=3)
    assert latest["rrp_billions"] == 0.0
    assert latest["rrp_missing_assumed_zero"] is True
    assert latest["percentile_source_label_date"] == latest["signal_label_date"] - timedelta(days=7)
    assert latest["percentile_source_observation_date"] == latest["observation_date"] - timedelta(days=7)
    assert latest["rank_denominator"] == 260
    assert latest["rank_less"] == 260
    assert latest["rank_equal"] == 0
    assert latest["percentile_applied"] == pytest.approx(100.0)


def test_exclusive_percentile_reproduces_corrected_rank_lineage_values():
    history = [float(index) for index in range(260)]

    rank_210 = calculate_exclusive_percentile(history, 209.5)
    rank_213 = calculate_exclusive_percentile(history, 212.5)

    assert rank_210 == (210, 0, pytest.approx(80.7692307692))
    assert rank_213 == (213, 0, pytest.approx(81.9230769231))


def test_exact_liquidity_does_not_cross_week_fill_treasury_series():
    dates = _wednesdays(330)
    missing_date = dates[-1]
    series = {
        "WALCL": [DatedValue(item, (9000.0 + index) * 1000.0) for index, item in enumerate(dates)],
        "WDTGAL": [
            DatedValue(item, 500.0 * 1000.0)
            for item in dates
            if item != missing_date
        ],
        "RRPONTSYD": [],
    }

    trace = calculate_exact_liquidity_trace(series)

    assert trace[-1]["observation_date"] == dates[-2]


def test_wilder_rsi_uses_adjust_false_first_delta_seed():
    values = [100.0, 102.0, 101.0, 104.0, 103.0, 107.0, 106.0, 108.0]

    result = calculate_wilder_rsi_ewm(values, period=3)

    assert result[:3] == [None, None, None]
    assert result[3] == pytest.approx(89.4736842105)
    assert result[-1] == pytest.approx(81.7307692308)


def test_declining_bear_red_router_falls_back_to_xlv_when_inputs_are_missing():
    qqq = _weekday_prices(280, descending=True)
    gld = [DatedValue(point.as_of_date, 100.0) for point in qqq]
    liquidity_trace = [
        {
            "effective_from_session": qqq[0].as_of_date,
            "state": "BEAR",
            "percentile_applied": 10.0,
        }
    ]

    trace = build_technical_trace(
        qqq,
        liquidity_trace,
        gld_points=gld,
        router_series={},
    )

    latest = trace[-1]
    assert latest["market_regime"] == "BEAR"
    assert latest["comparison1_confirmed_state"] == "RED"
    assert latest["router_active"] is True
    assert latest["router_target"] == "XLV"
    assert latest["execution_target"] == "XLV"
    assert "ROUTER_REQUIRED_INPUT_MISSING" in latest["router_reason_codes"]


def test_entry_advice_splits_only_qld_with_five_percent_upper_distance():
    split = build_entry_advice(
        execution_target="QLD",
        qqq_close=105.0,
        qqq_sma50=100.0,
        execution_session=date(2026, 7, 27),
        deferred_due_session=date(2026, 10, 20),
    )
    immediate = build_entry_advice(
        execution_target="QQQ",
        qqq_close=110.0,
        qqq_sma50=100.0,
        execution_session=date(2026, 7, 27),
        deferred_due_session=date(2026, 10, 20),
    )

    assert split["mode"] == "SPLIT_50_50"
    assert split["immediate_weight_pct"] == 50.0
    assert split["deferred_weight_pct"] == 50.0
    assert split["deferred_target_policy"] == "RECOMPUTE_ROUTER_TARGET_ON_DUE_SESSION"
    assert immediate["mode"] == "IMMEDIATE_100"
    assert immediate["deferred_due_session"] is None


def test_rsi_reference_is_advisory_and_contains_five_sessions():
    rows = []
    start = date(2026, 7, 13)
    for index, close in enumerate([100.0, 101.0, 102.0, 103.0, 104.0, 105.0]):
        rows.append(
            {
                "as_of_date": start + timedelta(days=index),
                "close": close,
                "rsi14": 58.0 + index,
            }
        )

    result = build_rsi_reference(rows)

    assert result["warning"] is True
    assert result["affects_target"] is False
    assert result["trend_label"] == "상승 지속"
    assert len(result["recent_sessions"]) == 5


def test_official_signal_serializes_full_validated_contract():
    dates = _wednesdays(330)
    net_values = [math.exp(0.0001 * index * index) + 100.0 for index in range(len(dates))]
    liquidity_series = {
        "WALCL": [DatedValue(item, value * 1000.0) for item, value in zip(dates, net_values)],
        "WDTGAL": [DatedValue(item, 0.0) for item in dates],
        "RRPONTSYD": [],
    }
    qqq = _weekday_prices(400)
    gld = [DatedValue(point.as_of_date, 80.0 + index * 0.1) for index, point in enumerate(qqq)]
    router_series = {
        "VIXCLS": [DatedValue(point.as_of_date, 15.0) for point in qqq],
        "BAMLH0A0HYM2": [DatedValue(point.as_of_date, 3.0) for point in qqq],
        "DFII10": [DatedValue(point.as_of_date, 1.5) for point in qqq],
        "DTWEXBGS": [DatedValue(point.as_of_date, 110.0) for point in qqq],
    }
    decision = qqq[-1].as_of_date

    signal = build_official_meta_strategy_signal(
        qqq_points=qqq,
        gld_points=gld,
        liquidity_series=liquidity_series,
        router_series=router_series,
        decision_session=decision,
        planned_execution_session=decision + timedelta(days=1),
        deferred_due_session=decision + timedelta(days=90),
        next_session_after=lambda value: value + timedelta(days=3),
        source_metadata={"price_provider": "Tiingo"},
    )

    assert signal["status"] == "VALIDATED"
    assert signal["decision_session"] == decision.isoformat()
    assert signal["liquidity"]["rank_denominator"] == 260
    assert signal["legacy_view"]["data_mode"] == "official"
    assert signal["legacy_view"]["source"] == "GitHub Actions · Tiingo adjusted + FRED"
