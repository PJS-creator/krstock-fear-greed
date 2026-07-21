from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest

from portfolio.meta_strategy import (
    DatedValue,
    LIQUIDITY_BEAR,
    LIQUIDITY_BULL,
    LIQUIDITY_MIXED,
    REGIME_BEAR,
    REGIME_BULL,
    REGIME_MIXED,
    TREND_DOWN,
    TREND_UP,
    advance_comparison1,
    advance_comparison3,
    analyze_qqq_technicals,
    build_meta_strategy_result,
    calculate_liquidity_signals,
    classify_liquidity_state,
    classify_market_regime,
    parse_fred_liquidity_csv,
    parse_yahoo_qqq_history,
    retain_previous_meta_strategy_result,
    unavailable_meta_strategy_result,
    wilder_rsi,
)


def _weekly_liquidity_series(count: int = 320) -> dict[str, list[DatedValue]]:
    start = date(2019, 1, 2)
    walcl: list[DatedValue] = []
    wdtgal: list[DatedValue] = []
    rrp: list[DatedValue] = []
    for index in range(count):
        point_date = start + timedelta(days=index * 7)
        walcl.append(DatedValue(point_date, 6_000_000 + index * 9_000 + index * index * 8))
        wdtgal.append(DatedValue(point_date, 500_000 + index * 250))
        rrp.append(DatedValue(point_date, 100 + index * 0.05))
    return {"WALCL": walcl, "WDTGAL": wdtgal, "RRPONTSYD": rrp}


def _daily_prices(values: list[float], start: date = date(2024, 1, 2)) -> list[DatedValue]:
    return [DatedValue(start + timedelta(days=index), value) for index, value in enumerate(values)]


def test_parse_yahoo_history_prefers_adjusted_close():
    payload = {
        "chart": {
            "error": None,
            "result": [
                {
                    "timestamp": [1704153600, 1704240000],
                    "indicators": {
                        "quote": [{"close": [101.0, 102.0]}],
                        "adjclose": [{"adjclose": [99.0, 100.0]}],
                    },
                }
            ],
        }
    }

    points = parse_yahoo_qqq_history(payload)

    assert [point.value for point in points] == [99.0, 100.0]


def test_parse_fred_zip_reads_all_required_series():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("weekly.csv", "observation_date,WALCL,WDTGAL\n2026-07-01,6724564,807359\n")
        archive.writestr("daily.csv", "observation_date,RRPONTSYD\n2026-07-01,12.5\n")

    parsed = parse_fred_liquidity_csv(buffer.getvalue())

    assert parsed["WALCL"][0].value == 6_724_564
    assert parsed["WDTGAL"][0].value == 807_359
    assert parsed["RRPONTSYD"][0].value == 12.5


def test_liquidity_hysteresis_uses_pdf_thresholds():
    assert classify_liquidity_state(LIQUIDITY_MIXED, 75) == LIQUIDITY_BULL
    assert classify_liquidity_state(LIQUIDITY_BULL, 64.9) == LIQUIDITY_MIXED
    assert classify_liquidity_state(LIQUIDITY_MIXED, 25) == LIQUIDITY_BEAR
    assert classify_liquidity_state(LIQUIDITY_BEAR, 35) == LIQUIDITY_BEAR
    assert classify_liquidity_state(LIQUIDITY_BEAR, 35.1) == LIQUIDITY_MIXED


def test_liquidity_percentile_is_lagged_one_week():
    signals = calculate_liquidity_signals(_weekly_liquidity_series())

    assert signals
    assert 0 <= signals[-1].percentile <= 100
    assert signals[-1].as_of_date.weekday() == 4
    assert signals[-1].state in {LIQUIDITY_BULL, LIQUIDITY_MIXED, LIQUIDITY_BEAR}


def test_wilder_rsi_handles_rising_and_flat_prices():
    rising = wilder_rsi([float(index) for index in range(30)])
    flat = wilder_rsi([100.0] * 30)

    assert rising[-1] == pytest.approx(100.0)
    assert flat[-1] == pytest.approx(50.0)


def test_comparison3_uses_rsi_cross_rules():
    assert advance_comparison3(
        "QLD",
        close=90,
        sma200=100,
        previous_rsi=39,
        current_rsi=41,
    ) == "TQQQ"
    assert advance_comparison3(
        "TQQQ",
        close=120,
        sma200=100,
        previous_rsi=79,
        current_rsi=81,
    ) == "QLD"


def test_comparison1_requires_same_raw_target_twice():
    confirmed, candidate, count = advance_comparison1("QLD", None, 0, "QQQ")
    assert (confirmed, candidate, count) == ("QLD", "QQQ", 1)

    confirmed, candidate, count = advance_comparison1(confirmed, candidate, count, "QQQ")
    assert (confirmed, candidate, count) == ("QQQ", None, 0)


def test_market_regime_priority_matches_strategy_spec():
    assert classify_market_regime(TREND_DOWN, False, LIQUIDITY_BULL) == REGIME_BEAR
    assert classify_market_regime(TREND_DOWN, True, LIQUIDITY_BEAR) == REGIME_MIXED
    assert classify_market_regime(TREND_UP, False, LIQUIDITY_BULL) == REGIME_BULL
    assert classify_market_regime(TREND_UP, False, LIQUIDITY_MIXED) == REGIME_MIXED


def test_qqq_analysis_confirms_uptrend_and_comparison1_target():
    snapshot = analyze_qqq_technicals(_daily_prices([100.0 + index for index in range(260)]))

    assert snapshot.trend200 == TREND_UP
    assert snapshot.comparison1_ticker == "TQQQ"


def test_meta_strategy_result_selects_strategy_and_ticker():
    result = build_meta_strategy_result(
        _daily_prices([100.0 + index * 0.5 for index in range(360)]),
        _weekly_liquidity_series(),
        fetched_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    assert result.status == "updated"
    assert result.market_regime in {REGIME_BULL, REGIME_MIXED, REGIME_BEAR}
    assert result.active_strategy in {"comparison1", "comparison3"}
    assert result.applied_ticker in {"QQQ", "QLD", "TQQQ"}
    assert result.source == "FRED + Yahoo chart"


def test_failed_refresh_retains_last_successful_classification():
    previous = build_meta_strategy_result(
        _daily_prices([100.0 + index * 0.5 for index in range(360)]),
        _weekly_liquidity_series(),
    )
    current = unavailable_meta_strategy_result("temporary outage")

    retained = retain_previous_meta_strategy_result(previous, current)

    assert retained.status == "previous"
    assert retained.applied_ticker == previous.applied_ticker
    assert retained.error_message == "temporary outage"
