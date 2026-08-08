from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import math
from typing import Callable, Mapping, Sequence

from portfolio.meta_strategy import DatedValue
from portfolio.meta_strategy_official import (
    build_official_meta_strategy_signal,
    build_technical_trace,
    calculate_exact_liquidity_trace,
)


ALTERNATIVE_PIPELINE_VERSION = "alternative-shadow-daily-v2"
ALTERNATIVE_RULESET_VERSION = "qqq-meta-v1-red-router-s1-n1-a1-v4-shadow-v3.0"
ALTERNATIVE_SCHEMA_VERSION = "2.0"
STRATEGY_ID = "qqq_meta_v1_red_router_s1_n1_a1_v4_shadow_v3_0"
STRATEGY_SPEC_VERSION = "3.0"
ENTRY_DISTANCE_THRESHOLD_PCT = 5.0
DEFERRED_COMPLETED_SESSIONS = 60
A1_STATE_ANCHOR_DATE = date(2010, 2, 11)


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def apply_n1_overlay(
    *,
    market_regime: str,
    active_strategy: str,
    base_target: str,
    router_active: bool,
) -> dict[str, object]:
    """Resolve the N1 target without mutating the canonical strategy state."""

    conditions = {
        "final_regime_is_bull": market_regime == "BULL",
        "active_policy_is_rsi_aggressive_immediate": active_strategy
        == "rsi_aggressive_immediate",
        "pre_overlay_base_target_is_moderate": base_target == "QLD",
        "red_router_latch_is_inactive": not router_active,
    }
    applied = all(conditions.values())
    failed = [name for name, passed in conditions.items() if not passed]
    return {
        "type": "BULL_RSI_MODERATE_TO_DEFENSIVE",
        "status": "APPLIED" if applied else "NOT_APPLIED",
        "applied": applied,
        "application_timing": "NEXT_COMMON_US_SESSION_OPEN",
        "base_target": base_target,
        "base_target_role": "moderate" if base_target == "QLD" else None,
        "replacement_target": "QQQ",
        "replacement_target_role": "defensive",
        "resolved_target": "QQQ" if applied else base_target,
        "conditions": conditions,
        "reason_codes": ["N1_ALL_CONDITIONS_MET"] if applied else [
            f"N1_CONDITION_FAILED_{name.upper()}" for name in failed
        ],
    }


def classify_a1_state_subtype(row: Mapping[str, object]) -> str:
    """Map the canonical regime fields to the v3.0 A1 state subtype."""

    regime = str(row.get("market_regime") or "").upper()
    trend = str(row.get("trend200") or "").upper()
    if regime == "BULL":
        return "BULL"
    if regime == "BEAR":
        return "BEAR"
    if regime == "MIXED" and trend == "UP":
        return "UP_MIXED"
    if regime == "MIXED" and trend == "DOWN" and row.get("recovery") is True:
        return "RECOVERY_MIXED"
    return regime or "UNKNOWN"


def advance_a1_overlay(
    *,
    as_of_date: date | str,
    previous_state: Mapping[str, object] | None,
    previous_subtype: str | None,
    current_subtype: str,
    previous_executed_target: str | None,
    post_n1_target: str,
    comparison3_target: str,
    router_active: bool,
) -> dict[str, object]:
    """Advance the deterministic A1 latch by one completed session."""

    prior = _mapping(previous_state)
    was_active = prior.get("active") is True
    was_blocked = prior.get("reentry_blocked") is True
    entry_session = prior.get("entry_session")
    last_release_session = prior.get("last_release_session")
    event = "NONE"
    active = was_active
    reentry_blocked = was_blocked
    resolved_target = post_n1_target
    reason_codes: list[str] = []

    release_conditions = {
        "current_state_subtype_not_up_mixed": current_subtype != "UP_MIXED",
        "comparison3_target_is_tqqq": comparison3_target == "TQQQ",
        "router_latch_is_active": router_active,
    }
    enter_conditions = {
        "previous_state_subtype_is_bull": previous_subtype == "BULL",
        "current_state_subtype_is_up_mixed": current_subtype == "UP_MIXED",
        "previous_executed_target_is_qqq": previous_executed_target == "QQQ",
        "current_post_n1_target_is_qld": post_n1_target == "QLD",
        "comparison3_target_is_qld": comparison3_target == "QLD",
        "router_latch_is_inactive": not router_active,
        "same_episode_reentry_is_allowed": not was_blocked,
    }

    if was_active:
        triggered_releases = [name for name, matched in release_conditions.items() if matched]
        if triggered_releases:
            event = "RELEASE"
            active = False
            reentry_blocked = current_subtype == "UP_MIXED"
            last_release_session = str(as_of_date)
            reason_codes = [f"A1_RELEASE_{name.upper()}" for name in triggered_releases]
        else:
            event = "HOLD"
            resolved_target = "QQQ"
            reason_codes = ["A1_LATCH_ACTIVE"]
    elif was_blocked:
        if current_subtype != "UP_MIXED":
            event = "REARM"
            reentry_blocked = False
            reason_codes = ["A1_NEW_UP_MIXED_EPISODE_REARMED"]
        else:
            event = "BLOCKED_REENTRY"
            reason_codes = ["A1_SAME_UP_MIXED_EPISODE_REENTRY_BLOCKED"]
    elif all(enter_conditions.values()):
        event = "ENTER"
        active = True
        reentry_blocked = False
        entry_session = str(as_of_date)
        resolved_target = "QQQ"
        reason_codes = ["A1_RISK_DOWNGRADE_BLOCK_RELEVERAGE"]
    else:
        reason_codes = [
            f"A1_CONDITION_FAILED_{name.upper()}"
            for name, matched in enter_conditions.items()
            if not matched
        ]

    return {
        "type": "BULL_EXIT_LEVERAGE_MONOTONICITY_LATCH",
        "execution_scope": "SHADOW_RESEARCH_ONLY",
        "evaluation_order": "AFTER_N1_BEFORE_ENTRY_FILTER_V4",
        "event": event,
        "status": "ACTIVE" if active else event,
        "applied": active,
        "active": active,
        "reentry_blocked": reentry_blocked,
        "entry_session": entry_session,
        "last_release_session": last_release_session,
        "previous_state_subtype": previous_subtype,
        "current_state_subtype": current_subtype,
        "previous_executed_target": previous_executed_target,
        "post_n1_target": post_n1_target,
        "comparison3_target": comparison3_target,
        "router_active": router_active,
        "latch_target": "QQQ",
        "resolved_target": resolved_target,
        "enter_conditions": enter_conditions,
        "release_conditions": release_conditions,
        "reason_codes": reason_codes,
    }


def replay_n1_a1_overlays(
    technical_trace: Sequence[Mapping[str, object]],
    *,
    anchor_date: date = A1_STATE_ANCHOR_DATE,
) -> dict[str, object]:
    """Replay N1 and stateful A1 from the fixed v3.0 anchor."""

    rows = [
        row
        for row in technical_trace
        if isinstance(row.get("as_of_date"), date) and row["as_of_date"] >= anchor_date
    ]
    if not rows:
        raise ValueError("A1 replay requires technical rows on or after the state anchor")

    previous_subtype: str | None = None
    previous_target: str | None = "QLD"
    a1_state: Mapping[str, object] | None = None
    latest: dict[str, object] | None = None
    event_history: list[dict[str, object]] = []

    for row in rows:
        router_active = row.get("router_active") is True
        base_target = str(row.get("execution_target") or "")
        n1 = apply_n1_overlay(
            market_regime=str(row.get("market_regime") or ""),
            active_strategy=str(row.get("active_strategy") or ""),
            base_target=base_target,
            router_active=router_active,
        )
        post_n1_target = str(n1["resolved_target"])
        current_subtype = classify_a1_state_subtype(row)
        a1 = advance_a1_overlay(
            as_of_date=row["as_of_date"],
            previous_state=a1_state,
            previous_subtype=previous_subtype,
            current_subtype=current_subtype,
            previous_executed_target=previous_target,
            post_n1_target=post_n1_target,
            comparison3_target=str(row.get("comparison3_ticker") or ""),
            router_active=router_active,
        )
        event = str(a1.get("event") or "NONE")
        if event in {"ENTER", "RELEASE", "REARM"}:
            event_history.append(
                {
                    "as_of_date": str(row["as_of_date"]),
                    "event": event,
                    "previous_state_subtype": a1.get("previous_state_subtype"),
                    "current_state_subtype": a1.get("current_state_subtype"),
                    "previous_executed_target": a1.get("previous_executed_target"),
                    "post_n1_target": a1.get("post_n1_target"),
                    "resolved_target": a1.get("resolved_target"),
                    "reason_codes": list(a1.get("reason_codes") or []),
                }
            )
        latest = {
            "as_of_date": str(row["as_of_date"]),
            "base_target": base_target,
            "post_n1_target": post_n1_target,
            "resolved_target": str(a1["resolved_target"]),
            "n1_overlay": n1,
            "a1_overlay": a1,
        }
        a1_state = a1
        previous_subtype = current_subtype
        previous_target = str(a1["resolved_target"])

    assert latest is not None
    latest_a1 = dict(_mapping(latest["a1_overlay"]))
    latest_a1.update(
        {
            "state_anchor_date": anchor_date.isoformat(),
            "replayed_through_session": latest["as_of_date"],
            "event_history": event_history,
        }
    )
    latest["a1_overlay"] = latest_a1
    return latest


def build_shadow_entry_plan(
    *,
    base_target: str,
    qqq_close: object,
    qqq_sma50: object,
    execution_session: date | str,
    deferred_due_session: date | str,
    resolved_target: str | None = None,
    post_n1_target: str | None = None,
    post_a1_target: str | None = None,
) -> dict[str, object]:
    """Build the initial-capital-only V4 plan as a non-executable shadow view."""

    close = _finite(qqq_close)
    sma50 = _finite(qqq_sma50)
    data_available = close is not None and sma50 is not None and sma50 > 0.0
    ratio = close / sma50 if data_available else None
    distance_pct = (ratio - 1.0) * 100.0 if ratio is not None else None
    resolved_n1 = post_n1_target or resolved_target or base_target
    resolved_a1 = post_a1_target or resolved_n1
    post_a1_is_moderate = resolved_a1 == "QLD"
    threshold_met = distance_pct is not None and distance_pct >= ENTRY_DISTANCE_THRESHOLD_PCT
    triggered = post_a1_is_moderate and threshold_met

    if triggered:
        mode = "SPLIT_50_50"
        immediate_weight = 50.0
        cash_weight = 50.0
        release_session: date | str | None = deferred_due_session
        reason_codes = ["POST_A1_TARGET_QLD", "QQQ_SMA50_UPPER_DISTANCE_GTE_5"]
    else:
        mode = "IMMEDIATE_100"
        immediate_weight = 100.0
        cash_weight = 0.0
        release_session = None
        reason_codes = []
        if not post_a1_is_moderate:
            reason_codes.append("POST_A1_TARGET_NOT_QLD")
        if not data_available:
            reason_codes.append("QQQ_SMA50_INPUT_UNAVAILABLE")
        elif not threshold_met:
            reason_codes.append("QQQ_SMA50_UPPER_DISTANCE_BELOW_5")

    return {
        "type": "STATE_AWARE_INITIAL_ENTRY_V4",
        "scope": "INITIAL_CAPITAL_IF_STARTED_NOW",
        "execution_scope": "SHADOW_RESEARCH_ONLY",
        "hypothetical": True,
        "affects_existing_capital": False,
        "triggered": triggered,
        "mode": mode,
        "base_target_before_n1": base_target,
        "resolved_target_after_n1": resolved_n1,
        "resolved_target_after_a1": resolved_a1,
        "qqq_close": close,
        "qqq_sma50": sma50,
        "qqq_close_to_sma50_ratio": ratio,
        "qqq_sma50_upper_distance_pct": distance_pct,
        "trigger_threshold_pct": ENTRY_DISTANCE_THRESHOLD_PCT,
        "trigger_conditions": {
            "post_a1_target_is_moderate": post_a1_is_moderate,
            "qqq_sma50_data_available": data_available,
            "qqq_sma50_upper_distance_gte_5": threshold_met,
        },
        "initial_execution_session": execution_session,
        "immediate_target": resolved_a1,
        "immediate_weight_pct": immediate_weight,
        "cash_weight_pct": cash_weight,
        "deferred_weight_pct": cash_weight,
        "hold_completed_common_sessions": DEFERRED_COMPLETED_SESSIONS if triggered else 0,
        "during_hold_policy": "ACTIVE_HALF_FOLLOWS_DAILY_POST_A1_TARGET" if triggered else None,
        "deferred_due_session": release_session,
        "deferred_target_policy": "JOIN_THEN_CURRENT_POST_A1_TARGET" if triggered else None,
        "deferred_execution_timing": "NEXT_COMMON_US_SESSION_OPEN" if triggered else None,
        "reason_codes": reason_codes,
    }


def build_alternative_meta_strategy_signal(
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
    """Derive the separate N1/A1/V4 shadow signal from the official inputs."""

    canonical = build_official_meta_strategy_signal(
        qqq_points=qqq_points,
        gld_points=gld_points,
        liquidity_series=liquidity_series,
        router_series=router_series,
        decision_session=decision_session,
        planned_execution_session=planned_execution_session,
        deferred_due_session=deferred_due_session,
        next_session_after=next_session_after,
        generated_at=generated_at,
        source_metadata=source_metadata,
    )
    payload = deepcopy(canonical)
    qqq = _mapping(payload.get("qqq"))
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
    overlay_result = replay_n1_a1_overlays(technical_trace)
    if overlay_result.get("as_of_date") != decision_session.isoformat():
        raise ValueError("A1 replay did not end on the completed decision session")
    base_target = str(overlay_result["base_target"])
    post_n1_target = str(overlay_result["post_n1_target"])
    resolved_target = str(overlay_result["resolved_target"])
    n1 = _mapping(overlay_result["n1_overlay"])
    a1 = _mapping(overlay_result["a1_overlay"])
    entry_plan = build_shadow_entry_plan(
        base_target=base_target,
        post_n1_target=post_n1_target,
        post_a1_target=resolved_target,
        qqq_close=qqq.get("close"),
        qqq_sma50=qqq.get("sma50"),
        execution_session=str(payload.get("planned_execution_session")),
        deferred_due_session=deferred_due_session.isoformat(),
    )

    payload.update(
        {
            "schema_version": ALTERNATIVE_SCHEMA_VERSION,
            "pipeline_version": ALTERNATIVE_PIPELINE_VERSION,
            "ruleset_version": ALTERNATIVE_RULESET_VERSION,
            "strategy_id": STRATEGY_ID,
            "strategy_spec_version": STRATEGY_SPEC_VERSION,
            "strategy_kind": "ALTERNATIVE_SHADOW",
            "official_strategy_unchanged": True,
            "execution_scope": "SHADOW_RESEARCH_ONLY",
            "automated_ordering": False,
            "base_execution_target": base_target,
            "post_n1_execution_target": post_n1_target,
            "resolved_execution_target": resolved_target,
            "overall_execution_target": resolved_target,
            "n1_overlay": dict(n1),
            "a1_overlay": dict(a1),
            "entry_filter_v4": entry_plan,
            "entry_advice": entry_plan,
            "canonical_reference": {
                "pipeline_version": canonical.get("pipeline_version"),
                "ruleset_version": canonical.get("ruleset_version"),
                "base_execution_target": base_target,
                "post_n1_execution_target": post_n1_target,
                "canonical_entry_advice": canonical.get("entry_advice"),
            },
            "cost_assumptions": {
                "commission_rate_one_way": 0.0025,
                "slippage_rate_one_way": 0.001,
                "tax_rate": 0.0,
                "applied_to_signal_target": False,
            },
            "disclaimer": "백테스트·shadow 검증 전용이며 자동 주문 또는 투자 조언이 아닙니다.",
        }
    )
    legacy = payload.get("legacy_view")
    if isinstance(legacy, dict):
        legacy.update(
            {
                "data_mode": "alternative_shadow",
                "applied_ticker": resolved_target,
                "source": "GitHub Actions · alternative shadow · Tiingo adjusted + FRED",
                "entry_advice": entry_plan,
            }
        )
    return payload


def _markdown_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


def render_alternative_signal_markdown(payload: Mapping[str, object]) -> str:
    liquidity = _mapping(payload.get("liquidity"))
    qqq = _mapping(payload.get("qqq"))
    n1 = _mapping(payload.get("n1_overlay"))
    a1 = _mapping(payload.get("a1_overlay"))
    entry = _mapping(payload.get("entry_filter_v4"))
    rsi = _mapping(payload.get("rsi_reference"))
    return "\n".join(
        [
            "# 대안 shadow 전략 일일 판정",
            "",
            f"- 전략 ID: `{_markdown_value(payload.get('strategy_id'))}`",
            f"- 판정 거래일: {_markdown_value(payload.get('decision_session'))}",
            f"- 예정 실행일: {_markdown_value(payload.get('planned_execution_session'))}",
            f"- 시장구간: {_markdown_value(payload.get('market_regime_label'))}",
            f"- 활성화 전략: {_markdown_value(payload.get('active_strategy_label'))}",
            f"- N1 전 기준 목표: **{_markdown_value(payload.get('base_execution_target'))}**",
            f"- N1 적용: **{_markdown_value(n1.get('status'))}**",
            f"- N1 후 목표: **{_markdown_value(payload.get('post_n1_execution_target'))}**",
            f"- A1 이벤트: **{_markdown_value(a1.get('event'))}**",
            f"- A1 상태: **{_markdown_value(a1.get('status'))}**",
            (
                f"- A1 상태 전이: {_markdown_value(a1.get('previous_state_subtype'))}"
                f" → {_markdown_value(a1.get('current_state_subtype'))}"
            ),
            f"- v3.0 최종 shadow target: **{_markdown_value(payload.get('resolved_execution_target'))}**",
            "",
            "## 신규진입 V4 · 오늘 시작 가정",
            "",
            f"- 발동: {_markdown_value(entry.get('triggered'))}",
            f"- 집행 방식: {_markdown_value(entry.get('mode'))}",
            f"- QQQ 종가 / SMA50: {_markdown_value(qqq.get('close'))} / {_markdown_value(qqq.get('sma50'))}",
            f"- SMA50 상방이격률: {_markdown_value(entry.get('qqq_sma50_upper_distance_pct'))}%",
            (
                f"- 즉시 집행: {_markdown_value(entry.get('immediate_weight_pct'))}% "
                f"→ {_markdown_value(entry.get('immediate_target'))}"
            ),
            f"- 현금 유예: {_markdown_value(entry.get('cash_weight_pct'))}%",
            f"- 유예 합류 예정일: {_markdown_value(entry.get('deferred_due_session'))}",
            "",
            "## 공통 공식 입력",
            "",
            f"- 적용 P: {_markdown_value(liquidity.get('percentile'))}",
            f"- Router 목표자산: {_markdown_value(payload.get('router_target'))}",
            f"- RSI14: {_markdown_value(rsi.get('latest_rsi14'))}",
            f"- RSI 참고 경고: {_markdown_value(rsi.get('warning'))}",
            "",
            "> 공식 판정은 변경하지 않습니다. 이 결과는 별도 shadow 검증이며 자동 매매나 투자 조언이 아닙니다.",
            "",
        ]
    )
