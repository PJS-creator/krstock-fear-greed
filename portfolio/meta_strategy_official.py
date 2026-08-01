from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from typing import Callable, Mapping, Sequence

from portfolio.meta_strategy import (
    DatedValue,
    LIQUIDITY_BEAR,
    LIQUIDITY_BULL,
    LIQUIDITY_MIXED,
    MetaStrategyInsufficientData,
    TREND_DOWN,
    TREND_UP,
    classify_liquidity_state,
    classify_market_regime,
    simple_moving_average,
)


PIPELINE_VERSION = "meta-strategy-daily-v2"
RULESET_VERSION = "pdf-regime-meta-v1-red-router-s1-entry-filter-v4"
SCHEMA_VERSION = "1.0"


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _points_by_date(points: Sequence[DatedValue]) -> dict[date, float]:
    result: dict[date, float] = {}
    for point in points:
        value = _finite(point.value)
        if value is not None:
            result[point.as_of_date] = value
    return result


def _combine_series(
    current: Sequence[DatedValue],
    historical: Sequence[DatedValue],
) -> dict[date, float]:
    result = _points_by_date(historical)
    result.update(_points_by_date(current))
    return result


def calculate_wilder_rsi_ewm(values: Sequence[float], period: int = 14) -> list[float | None]:
    """Return Wilder RSI using the handoff's adjust=False first-delta seed."""

    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) < 2:
        return result

    average_gain: float | None = None
    average_loss: float | None = None
    alpha = 1.0 / period
    for index in range(1, len(values)):
        change = float(values[index]) - float(values[index - 1])
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        if average_gain is None:
            average_gain = gain
            average_loss = loss
        else:
            average_gain = (1.0 - alpha) * average_gain + alpha * gain
            average_loss = (1.0 - alpha) * float(average_loss) + alpha * loss
        if index < period:
            continue
        if average_gain == 0.0 and average_loss == 0.0:
            result[index] = 50.0
        elif average_loss == 0.0:
            result[index] = 100.0
        else:
            relative_strength = average_gain / average_loss
            result[index] = 100.0 - 100.0 / (1.0 + relative_strength)
    return result


def calculate_exclusive_percentile(
    history: Sequence[float],
    current: float,
) -> tuple[int, int, float]:
    if not history:
        raise ValueError("history must not be empty")
    rank_less = sum(1 for value in history if float(value) < float(current))
    rank_equal = sum(1 for value in history if float(value) == float(current))
    percentile = 100.0 * (rank_less + 0.5 * rank_equal) / len(history)
    return rank_less, rank_equal, percentile


def calculate_exact_liquidity_trace(
    series: Mapping[str, Sequence[DatedValue]],
    *,
    effective_session_resolver: Callable[[date], date] | None = None,
) -> list[dict[str, object]]:
    """Build the exact Wednesday liquidity lineage used by the official signal."""

    walcl = _combine_series(series.get("WALCL", ()), series.get("TOTRA", ()))
    wdtgal = _combine_series(series.get("WDTGAL", ()), series.get("LDGUST", ()))
    rrp = _points_by_date(series.get("RRPONTSYD", ()))
    observation_dates = sorted(set(walcl).intersection(wdtgal))
    observation_dates = [item for item in observation_dates if item.weekday() == 2]
    if len(observation_dates) < 300:
        raise MetaStrategyInsufficientData(
            f"정확히 정렬된 수요일 유동성 관측치가 최소 300주 필요합니다. 현재 {len(observation_dates)}주입니다."
        )

    rows: list[dict[str, object]] = []
    for observation_date in observation_dates:
        reverse_repo = rrp.get(observation_date, 0.0)
        net_liquidity = walcl[observation_date] / 1000.0 - wdtgal[observation_date] / 1000.0 - reverse_repo
        rows.append(
            {
                "observation_date": observation_date,
                "signal_label_date": observation_date + timedelta(days=2),
                "walcl_millions": walcl[observation_date],
                "wdtgal_millions": wdtgal[observation_date],
                "rrp_billions": reverse_repo,
                "rrp_missing_assumed_zero": observation_date not in rrp,
                "net_liquidity_billions": net_liquidity,
                "growth_26w": None,
                "smooth_13w": None,
                "rank_less_raw": None,
                "rank_equal_raw": None,
                "rank_less": None,
                "rank_equal": None,
                "rank_denominator": 260,
                "percentile_raw": None,
                "percentile_applied": None,
                "percentile_source_label_date": None,
                "percentile_source_net_liquidity_billions": None,
                "percentile_source_growth_26w": None,
                "percentile_source_smooth_13w": None,
                "state": None,
                "effective_from_session": None,
            }
        )

    for index in range(26, len(rows)):
        current = float(rows[index]["net_liquidity_billions"])
        previous = float(rows[index - 26]["net_liquidity_billions"])
        if current > 0.0 and previous > 0.0:
            rows[index]["growth_26w"] = math.log(current / previous)

    for index in range(12, len(rows)):
        window = [rows[position]["growth_26w"] for position in range(index - 12, index + 1)]
        if all(value is not None for value in window):
            rows[index]["smooth_13w"] = sum(float(value) for value in window) / 13.0

    for index, row in enumerate(rows):
        current = row["smooth_13w"]
        if current is None or index < 260:
            continue
        history = [rows[position]["smooth_13w"] for position in range(index - 260, index)]
        if any(value is None for value in history):
            continue
        rank_less, rank_equal, percentile = calculate_exclusive_percentile(
            [float(value) for value in history],
            float(current),
        )
        row["rank_less_raw"] = rank_less
        row["rank_equal_raw"] = rank_equal
        row["percentile_raw"] = percentile

    state = LIQUIDITY_MIXED
    validated_rows: list[dict[str, object]] = []
    for index in range(1, len(rows)):
        source = rows[index - 1]
        applied = source["percentile_raw"]
        if applied is None:
            continue
        row = rows[index]
        state = classify_liquidity_state(state, float(applied))
        label_date = row["signal_label_date"]
        assert isinstance(label_date, date)
        row["percentile_applied"] = float(applied)
        row["percentile_source_label_date"] = source["signal_label_date"]
        row["percentile_source_observation_date"] = source["observation_date"]
        row["percentile_source_net_liquidity_billions"] = source["net_liquidity_billions"]
        row["percentile_source_growth_26w"] = source["growth_26w"]
        row["percentile_source_smooth_13w"] = source["smooth_13w"]
        row["rank_less"] = source["rank_less_raw"]
        row["rank_equal"] = source["rank_equal_raw"]
        row["state"] = state
        row["effective_from_session"] = (
            effective_session_resolver(label_date) if effective_session_resolver is not None else label_date
        )
        validated_rows.append(row)

    if not validated_rows:
        raise MetaStrategyInsufficientData("유동성 백분위 계보를 계산할 수 없습니다.")
    return validated_rows


def _weekly_end_indices(points: Sequence[DatedValue]) -> set[int]:
    result: set[int] = set()
    previous_week: tuple[int, int] | None = None
    previous_index: int | None = None
    for index, point in enumerate(points):
        iso = point.as_of_date.isocalendar()
        week = (iso.year, iso.week)
        if previous_week is not None and week != previous_week and previous_index is not None:
            result.add(previous_index)
        previous_week = week
        previous_index = index
    if previous_index is not None:
        result.add(previous_index)
    return result


def _advance_confirmed_state(
    confirmed: str,
    candidate: str | None,
    candidate_count: int,
    raw_state: str,
) -> tuple[str, str | None, int]:
    if raw_state == confirmed:
        return confirmed, None, 0
    if raw_state == candidate:
        candidate_count += 1
    else:
        candidate = raw_state
        candidate_count = 1
    if candidate_count >= 2:
        return raw_state, None, 0
    return confirmed, candidate, candidate_count


def _advance_comparison3(
    current_ticker: str,
    *,
    close: float,
    sma200: float | None,
    previous_rsi: float | None,
    current_rsi: float | None,
) -> str:
    ticker = current_ticker if current_ticker in {"QLD", "TQQQ"} else "QLD"
    if sma200 is None or previous_rsi is None or current_rsi is None:
        return ticker
    entry_cross = previous_rsi <= 40.0 < current_rsi
    exit_cross = previous_rsi <= 80.0 < current_rsi
    if exit_cross:
        return "QLD"
    if ticker == "QLD" and close < sma200 and entry_cross:
        return "TQQQ"
    return ticker


def _forward_fill_shift_one(
    sessions: Sequence[date],
    points: Sequence[DatedValue],
) -> list[float | None]:
    source = sorted(_points_by_date(points).items())
    filled: list[float | None] = []
    source_index = 0
    current: float | None = None
    for session in sessions:
        while source_index < len(source) and source[source_index][0] <= session:
            current = source[source_index][1]
            source_index += 1
        filled.append(current)
    return [None] + filled[:-1]


def _router_evaluation(
    index: int,
    *,
    qqq_close: Sequence[float],
    gld_close: Sequence[float | None],
    gld_sma20: Sequence[float | None],
    vix: Sequence[float | None],
    hy_oas: Sequence[float | None],
    real_yield: Sequence[float | None],
    broad_dollar: Sequence[float | None],
) -> tuple[str, list[str], dict[str, object]]:
    required: dict[str, float | None] = {
        "vix": vix[index],
        "vix_10": vix[index - 10] if index >= 10 else None,
        "hy_oas": hy_oas[index],
        "hy_oas_20": hy_oas[index - 20] if index >= 20 else None,
        "qqq_close": qqq_close[index],
        "qqq_close_5": qqq_close[index - 5] if index >= 5 else None,
        "gld_close": gld_close[index],
        "gld_sma20": gld_sma20[index],
        "real_yield": real_yield[index],
        "real_yield_20": real_yield[index - 20] if index >= 20 else None,
        "broad_dollar": broad_dollar[index],
        "broad_dollar_20": broad_dollar[index - 20] if index >= 20 else None,
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        return "XLV", ["ROUTER_REQUIRED_INPUT_MISSING", *[f"MISSING_{key.upper()}" for key in missing]], required

    qqq_gate = (
        float(required["vix"]) < float(required["vix_10"])
        and float(required["hy_oas"]) <= float(required["hy_oas_20"])
        and float(required["qqq_close"]) > float(required["qqq_close_5"])
    )
    gld_gate = (
        float(required["gld_close"]) > float(required["gld_sma20"])
        and (
            float(required["real_yield"]) < float(required["real_yield_20"])
            or float(required["broad_dollar"]) < float(required["broad_dollar_20"])
        )
    )
    required["qqq_gate"] = qqq_gate
    required["gld_gate"] = gld_gate
    if qqq_gate:
        return "QQQ", ["ROUTER_QQQ_GATE"], required
    if gld_gate:
        return "GLD", ["ROUTER_GLD_GATE"], required
    return "XLV", ["ROUTER_FALLBACK_XLV"], required


def build_technical_trace(
    qqq_points: Sequence[DatedValue],
    liquidity_trace: Sequence[Mapping[str, object]],
    *,
    gld_points: Sequence[DatedValue] = (),
    router_series: Mapping[str, Sequence[DatedValue]] | None = None,
    final_liquidity_session: date | None = None,
) -> list[dict[str, object]]:
    prices = sorted(_points_by_date(qqq_points).items())
    if len(prices) < 205:
        raise MetaStrategyInsufficientData(
            f"QQQ 공식 판정에는 최소 205거래일이 필요합니다. 현재 {len(prices)}일입니다."
        )
    dates = [item[0] for item in prices]
    closes = [item[1] for item in prices]
    sma20 = simple_moving_average(closes, 20)
    sma50 = simple_moving_average(closes, 50)
    sma200 = simple_moving_average(closes, 200)
    rsi14 = calculate_wilder_rsi_ewm(closes, 14)
    week_ends = _weekly_end_indices([DatedValue(item[0], item[1]) for item in prices])

    liquidity_sorted = sorted(
        liquidity_trace,
        key=lambda row: row.get("effective_from_session") or date.min,
    )
    liquidity_index = 0
    current_liquidity: Mapping[str, object] | None = None

    gld_map = _points_by_date(gld_points)
    gld_close: list[float | None] = [gld_map.get(session) for session in dates]
    gld_sma20: list[float | None] = [None] * len(dates)
    gld_window: list[float] = []
    for index, value in enumerate(gld_close):
        if value is None:
            gld_window.clear()
            continue
        gld_window.append(value)
        if len(gld_window) > 20:
            gld_window.pop(0)
        if len(gld_window) == 20:
            gld_sma20[index] = sum(gld_window) / 20.0

    router_data = router_series or {}
    vix_map = _points_by_date(router_data.get("VIXCLS", ()))
    vix = [vix_map.get(session) for session in dates]
    hy_oas = _forward_fill_shift_one(dates, router_data.get("BAMLH0A0HYM2", ()))
    real_yield = _forward_fill_shift_one(dates, router_data.get("DFII10", ()))
    broad_dollar = _forward_fill_shift_one(dates, router_data.get("DTWEXBGS", ()))

    trend: str | None = None
    trend_candidate: str | None = None
    trend_candidate_count = 0
    recovery = False
    above_sma20_count = 0
    below_sma20_count = 0
    comparison1 = "YELLOW"
    comparison1_candidate: str | None = None
    comparison1_count = 0
    comparison3 = "QLD"
    router_active = False
    router_target: str | None = None
    router_reason_codes: list[str] = []
    router_inputs: dict[str, object] = {}
    rows: list[dict[str, object]] = []

    for index, (as_of_date, close) in enumerate(prices):
        liquidity_session = (
            max(as_of_date, final_liquidity_session)
            if final_liquidity_session is not None and index == len(prices) - 1
            else as_of_date
        )
        while liquidity_index < len(liquidity_sorted):
            effective = liquidity_sorted[liquidity_index].get("effective_from_session")
            if not isinstance(effective, date) or effective > liquidity_session:
                break
            current_liquidity = liquidity_sorted[liquidity_index]
            liquidity_index += 1

        transition_to_down = False
        if index in week_ends and sma200[index] is not None:
            side = TREND_UP if close > float(sma200[index]) else TREND_DOWN if close < float(sma200[index]) else None
            if side is None:
                trend_candidate = None
                trend_candidate_count = 0
            elif side == trend_candidate:
                trend_candidate_count += 1
            else:
                trend_candidate = side
                trend_candidate_count = 1
            if side is not None and trend_candidate_count >= 2 and side != trend:
                transition_to_down = side == TREND_DOWN
                trend = side
                trend_candidate = None
                trend_candidate_count = 0

        if transition_to_down:
            recovery = False
            above_sma20_count = 0
            below_sma20_count = 0
        elif trend == TREND_DOWN and sma20[index] is not None:
            if close > float(sma20[index]):
                above_sma20_count += 1
                below_sma20_count = 0
            else:
                below_sma20_count += 1
                above_sma20_count = 0
            if below_sma20_count >= 2:
                recovery = False
            if (
                above_sma20_count >= 5
                and index >= 5
                and sma20[index - 5] is not None
                and float(sma20[index]) > float(sma20[index - 5])
            ):
                recovery = True
        elif trend != TREND_DOWN:
            recovery = False
            above_sma20_count = 0
            below_sma20_count = 0

        raw_comparison1: str | None = None
        if sma50[index] is not None and sma200[index] is not None:
            if close > float(sma50[index]) and close > float(sma200[index]):
                raw_comparison1 = "GREEN"
            elif close < float(sma50[index]) and close < float(sma200[index]):
                raw_comparison1 = "RED"
            else:
                raw_comparison1 = "YELLOW"
            comparison1, comparison1_candidate, comparison1_count = _advance_confirmed_state(
                comparison1,
                comparison1_candidate,
                comparison1_count,
                raw_comparison1,
            )
        comparison3 = _advance_comparison3(
            comparison3,
            close=close,
            sma200=sma200[index],
            previous_rsi=rsi14[index - 1] if index else None,
            current_rsi=rsi14[index],
        )

        liquidity_state = (
            str(current_liquidity.get("state"))
            if current_liquidity is not None and current_liquidity.get("state")
            else LIQUIDITY_MIXED
        )
        regime = classify_market_regime(trend, recovery, liquidity_state).upper()
        router_condition = regime == "BEAR" and comparison1 == "RED"
        if router_active and not router_condition:
            router_active = False
            router_target = None
            router_reason_codes = ["ROUTER_LATCH_RELEASED"]
            router_inputs = {}
        if router_condition and not router_active:
            router_target, router_reason_codes, router_inputs = _router_evaluation(
                index,
                qqq_close=closes,
                gld_close=gld_close,
                gld_sma20=gld_sma20,
                vix=vix,
                hy_oas=hy_oas,
                real_yield=real_yield,
                broad_dollar=broad_dollar,
            )
            router_active = True

        if regime == "BEAR":
            active_strategy = "trend_2d"
            active_strategy_label = "비교1 · 2거래일 추세"
            comparison_target = {"GREEN": "TQQQ", "YELLOW": "QLD", "RED": "QQQ"}[comparison1]
            if comparison1 == "RED":
                execution_target = router_target or "XLV"
                active_strategy = "red_router_s1"
                active_strategy_label = "RED Router-S1"
            else:
                execution_target = comparison_target
        else:
            active_strategy = "rsi_aggressive_immediate"
            active_strategy_label = "비교3 · RSI 전환"
            execution_target = comparison3

        rows.append(
            {
                "as_of_date": as_of_date,
                "close": close,
                "sma20": sma20[index],
                "sma50": sma50[index],
                "sma200": sma200[index],
                "rsi14": rsi14[index],
                "trend200": trend,
                "recovery": recovery,
                "liquidity": dict(current_liquidity) if current_liquidity is not None else None,
                "market_regime": regime,
                "comparison1_raw_state": raw_comparison1,
                "comparison1_confirmed_state": comparison1,
                "comparison3_ticker": comparison3,
                "router_active": router_active,
                "router_target": router_target,
                "router_reason_codes": list(router_reason_codes),
                "router_inputs": dict(router_inputs),
                "active_strategy": active_strategy,
                "active_strategy_label": active_strategy_label,
                "execution_target": execution_target,
            }
        )
    return rows


def build_entry_advice(
    *,
    execution_target: str,
    qqq_close: float,
    qqq_sma50: float | None,
    execution_session: date,
    deferred_due_session: date,
) -> dict[str, object]:
    distance = None if qqq_sma50 in {None, 0.0} else qqq_close / float(qqq_sma50) - 1.0
    split_condition = execution_target == "QLD" and distance is not None and distance >= 0.05
    if split_condition:
        mode = "SPLIT_50_50"
        immediate_weight = 0.5
        deferred_weight = 0.5
        reason_codes = ["TARGET_QLD", "QQQ_SMA50_DISTANCE_GTE_5PCT"]
    else:
        mode = "IMMEDIATE_100"
        immediate_weight = 1.0
        deferred_weight = 0.0
        reason_codes = []
        if execution_target != "QLD":
            reason_codes.append("TARGET_NOT_QLD")
        if distance is None:
            reason_codes.append("QQQ_SMA50_UNAVAILABLE")
        elif distance < 0.05:
            reason_codes.append("QQQ_SMA50_DISTANCE_LT_5PCT")
    return {
        "scope": "NEW_CASH_IF_RECEIVED",
        "mode": mode,
        "condition_met": split_condition,
        "qqq_close": qqq_close,
        "qqq_sma50": qqq_sma50,
        "qqq_sma50_upper_distance_pct": None if distance is None else distance * 100.0,
        "immediate_weight_pct": immediate_weight * 100.0,
        "immediate_target": execution_target,
        "initial_execution_session": execution_session,
        "deferred_weight_pct": deferred_weight * 100.0,
        "deferred_due_session": deferred_due_session if split_condition else None,
        "deferred_target_policy": "RECOMPUTE_ROUTER_TARGET_ON_DUE_SESSION" if split_condition else None,
        "reason_codes": reason_codes,
        "assumption_only": True,
    }


def build_rsi_reference(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    usable = [row for row in rows if row.get("rsi14") is not None]
    if len(usable) < 6:
        return {
            "status": "INSUFFICIENT_DATA",
            "warning": False,
            "threshold": 60.0,
            "recent_sessions": [],
        }
    tail = usable[-6:]
    recent: list[dict[str, object]] = []
    up_days = 0
    down_days = 0
    for previous, current in zip(tail, tail[1:]):
        previous_close = float(previous["close"])
        current_close = float(current["close"])
        daily_return = current_close / previous_close - 1.0 if previous_close else 0.0
        if daily_return > 0:
            up_days += 1
        elif daily_return < 0:
            down_days += 1
        recent.append(
            {
                "date": current["as_of_date"],
                "close": current_close,
                "daily_return_pct": daily_return * 100.0,
                "rsi14": float(current["rsi14"]),
            }
        )
    cumulative = float(tail[-1]["close"]) / float(tail[0]["close"]) - 1.0
    latest_rsi = float(tail[-1]["rsi14"])
    previous_rsi = float(tail[-2]["rsi14"])
    if cumulative >= 0.01 and latest_rsi >= previous_rsi and recent[-1]["daily_return_pct"] > 0:
        trend_label = "상승 지속"
    elif cumulative >= 0.01:
        trend_label = "상승 둔화"
    elif cumulative <= -0.01 and recent[-1]["daily_return_pct"] < 0:
        trend_label = "하락 전환"
    elif abs(cumulative) < 0.005 and abs(up_days - down_days) <= 1:
        trend_label = "횡보"
    else:
        trend_label = "혼조"
    return {
        "status": "UPDATED",
        "warning": latest_rsi >= 60.0,
        "threshold": 60.0,
        "latest_rsi14": latest_rsi,
        "five_session_return_pct": cumulative * 100.0,
        "up_days": up_days,
        "down_days": down_days,
        "trend_label": trend_label,
        "recent_sessions": recent,
        "affects_target": False,
    }


def _serialize_dates(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialize_dates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_dates(item) for item in value]
    return value


def build_official_meta_strategy_signal(
    *,
    qqq_points: Sequence[DatedValue],
    gld_points: Sequence[DatedValue],
    liquidity_series: Mapping[str, Sequence[DatedValue]],
    router_series: Mapping[str, Sequence[DatedValue]],
    decision_session: date,
    planned_execution_session: date,
    deferred_due_session: date,
    next_session_after: Callable[[date], date],
    generated_at: datetime | None = None,
    source_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    liquidity_trace = calculate_exact_liquidity_trace(
        liquidity_series,
        effective_session_resolver=next_session_after,
    )
    technical_trace = build_technical_trace(
        qqq_points,
        liquidity_trace,
        gld_points=gld_points,
        router_series=router_series,
        final_liquidity_session=planned_execution_session,
    )
    latest = technical_trace[-1]
    if latest["as_of_date"] != decision_session:
        raise MetaStrategyInsufficientData(
            f"QQQ 최신 조정종가 기준일 {latest['as_of_date']}이 완료 거래일 {decision_session}과 일치하지 않습니다."
        )
    liquidity = latest.get("liquidity")
    if not isinstance(liquidity, Mapping):
        raise MetaStrategyInsufficientData("완료 거래일에 적용 가능한 유동성 판정이 없습니다.")

    entry_advice = build_entry_advice(
        execution_target=str(latest["execution_target"]),
        qqq_close=float(latest["close"]),
        qqq_sma50=_finite(latest.get("sma50")),
        execution_session=planned_execution_session,
        deferred_due_session=deferred_due_session,
    )
    rsi_reference = build_rsi_reference(technical_trace)
    regime = str(latest["market_regime"])
    regime_label = {"BULL": "강세장", "MIXED": "혼재장", "BEAR": "약세장"}[regime]
    generated = generated_at or datetime.now(timezone.utc)
    percentile = float(liquidity["percentile_applied"])
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "ruleset_version": RULESET_VERSION,
        "status": "VALIDATED",
        "generated_at_utc": generated.astimezone(timezone.utc),
        "decision_session": decision_session,
        "planned_execution_session": planned_execution_session,
        "market_regime": regime,
        "market_regime_label": regime_label,
        "active_strategy": latest["active_strategy"],
        "active_strategy_label": latest["active_strategy_label"],
        "router_target": latest["router_target"],
        "overall_execution_target": latest["execution_target"],
        "liquidity": {
            "state": liquidity["state"],
            "percentile": percentile,
            "rank_less": liquidity["rank_less"],
            "rank_equal": liquidity["rank_equal"],
            "rank_denominator": 260,
            "current_row_percentile_raw": liquidity["percentile_raw"],
            "current_row_rank_less_raw": liquidity["rank_less_raw"],
            "current_row_rank_equal_raw": liquidity["rank_equal_raw"],
            "observation_date": liquidity["observation_date"],
            "signal_label_date": liquidity["signal_label_date"],
            "percentile_source_label_date": liquidity["percentile_source_label_date"],
            "percentile_source_observation_date": liquidity["percentile_source_observation_date"],
            "percentile_source_net_liquidity_billions": liquidity[
                "percentile_source_net_liquidity_billions"
            ],
            "percentile_source_growth_26w": liquidity["percentile_source_growth_26w"],
            "percentile_source_smooth_13w": liquidity["percentile_source_smooth_13w"],
            "effective_from_session": liquidity["effective_from_session"],
            "net_liquidity_billions": liquidity["net_liquidity_billions"],
            "rrp_missing_assumed_zero": liquidity["rrp_missing_assumed_zero"],
        },
        "qqq": {
            "as_of_date": latest["as_of_date"],
            "close": latest["close"],
            "sma20": latest["sma20"],
            "sma50": latest["sma50"],
            "sma200": latest["sma200"],
            "rsi14": latest["rsi14"],
            "trend200": latest["trend200"],
            "recovery": latest["recovery"],
            "comparison1_raw_state": latest["comparison1_raw_state"],
            "comparison1_confirmed_state": latest["comparison1_confirmed_state"],
            "comparison3_ticker": latest["comparison3_ticker"],
        },
        "red_router": {
            "active": latest["router_active"],
            "target": latest["router_target"],
            "reason_codes": latest["router_reason_codes"],
            "inputs": latest["router_inputs"],
            "latch_mode": "HOLD_ENTRY_CHOICE",
        },
        "entry_advice": entry_advice,
        "rsi_reference": rsi_reference,
        "execution_audit": {
            "status": "PENDING_NEXT_OPEN",
            "raw_open": None,
            "note": "07:37 KST 판정 시점에는 다음 거래일 시가가 존재하지 않습니다.",
        },
        "sources": dict(source_metadata or {}),
        # Compatibility fields consumed by the existing Streamlit panel.
        "legacy_view": {
            "status": "updated",
            "data_mode": "official",
            "market_regime": regime.lower(),
            "market_regime_label": regime_label,
            "active_strategy": latest["active_strategy"],
            "active_strategy_label": latest["active_strategy_label"],
            "applied_ticker": latest["execution_target"],
            "qqq_as_of_date": latest["as_of_date"],
            "liquidity_as_of_date": liquidity["signal_label_date"],
            "liquidity_percentile": percentile,
            "liquidity_state": liquidity["state"],
            "trend200": latest["trend200"],
            "recovery": latest["recovery"],
            "qqq_close": latest["close"],
            "sma20": latest["sma20"],
            "sma50": latest["sma50"],
            "sma200": latest["sma200"],
            "rsi14": latest["rsi14"],
            "source": "GitHub Actions · Tiingo adjusted + FRED",
            "fetched_at": generated,
            "decision_session": decision_session,
            "planned_execution_session": planned_execution_session,
            "router_target": latest["router_target"],
            "entry_advice": entry_advice,
            "rsi_reference": rsi_reference,
        },
    }
    return _serialize_dates(payload)  # type: ignore[return-value]
