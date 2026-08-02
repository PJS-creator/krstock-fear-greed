from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import math
from typing import Callable, Mapping, Sequence

from portfolio.meta_strategy import DatedValue
from portfolio.meta_strategy_official import build_official_meta_strategy_signal


ALTERNATIVE_PIPELINE_VERSION = "alternative-shadow-daily-v1"
ALTERNATIVE_RULESET_VERSION = "qqq-meta-v1-red-router-s1-n1-v4-shadow-v2.1"
ALTERNATIVE_SCHEMA_VERSION = "1.0"
STRATEGY_ID = "qqq_meta_v1_red_router_s1_n1_v4_shadow_v2_1"
STRATEGY_SPEC_VERSION = "2.1"
ENTRY_DISTANCE_THRESHOLD_PCT = 5.0
DEFERRED_COMPLETED_SESSIONS = 60


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


def build_shadow_entry_plan(
    *,
    base_target: str,
    resolved_target: str,
    qqq_close: object,
    qqq_sma50: object,
    execution_session: date | str,
    deferred_due_session: date | str,
) -> dict[str, object]:
    """Build the initial-capital-only V4 plan as a non-executable shadow view."""

    close = _finite(qqq_close)
    sma50 = _finite(qqq_sma50)
    data_available = close is not None and sma50 is not None and sma50 > 0.0
    ratio = close / sma50 if data_available else None
    distance_pct = (ratio - 1.0) * 100.0 if ratio is not None else None
    base_is_moderate = base_target == "QLD"
    threshold_met = distance_pct is not None and distance_pct >= ENTRY_DISTANCE_THRESHOLD_PCT
    triggered = base_is_moderate and threshold_met

    if triggered:
        mode = "SPLIT_50_50"
        immediate_weight = 50.0
        cash_weight = 50.0
        release_session: date | str | None = deferred_due_session
        reason_codes = ["BASE_TARGET_QLD", "QQQ_SMA50_UPPER_DISTANCE_GTE_5"]
    else:
        mode = "IMMEDIATE_100"
        immediate_weight = 100.0
        cash_weight = 0.0
        release_session = None
        reason_codes = []
        if not base_is_moderate:
            reason_codes.append("BASE_TARGET_NOT_QLD")
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
        "resolved_target_after_n1": resolved_target,
        "qqq_close": close,
        "qqq_sma50": sma50,
        "qqq_close_to_sma50_ratio": ratio,
        "qqq_sma50_upper_distance_pct": distance_pct,
        "trigger_threshold_pct": ENTRY_DISTANCE_THRESHOLD_PCT,
        "trigger_conditions": {
            "base_target_is_moderate": base_is_moderate,
            "qqq_sma50_data_available": data_available,
            "qqq_sma50_upper_distance_gte_5": threshold_met,
        },
        "initial_execution_session": execution_session,
        "immediate_target": resolved_target,
        "immediate_weight_pct": immediate_weight,
        "cash_weight_pct": cash_weight,
        "deferred_weight_pct": cash_weight,
        "hold_completed_common_sessions": DEFERRED_COMPLETED_SESSIONS if triggered else 0,
        "during_hold_policy": "ACTIVE_HALF_FOLLOWS_DAILY_RESOLVED_TARGET" if triggered else None,
        "deferred_due_session": release_session,
        "deferred_target_policy": "JOIN_THEN_CURRENT_RESOLVED_TARGET" if triggered else None,
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
    """Derive the separate N1/V4 shadow signal from the canonical official result."""

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
    router = _mapping(payload.get("red_router"))
    qqq = _mapping(payload.get("qqq"))
    base_target = str(payload.get("overall_execution_target") or "")
    n1 = apply_n1_overlay(
        market_regime=str(payload.get("market_regime") or ""),
        active_strategy=str(payload.get("active_strategy") or ""),
        base_target=base_target,
        router_active=router.get("active") is True,
    )
    resolved_target = str(n1["resolved_target"])
    entry_plan = build_shadow_entry_plan(
        base_target=base_target,
        resolved_target=resolved_target,
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
            "resolved_execution_target": resolved_target,
            "overall_execution_target": resolved_target,
            "n1_overlay": n1,
            "entry_filter_v4": entry_plan,
            "entry_advice": entry_plan,
            "canonical_reference": {
                "pipeline_version": canonical.get("pipeline_version"),
                "ruleset_version": canonical.get("ruleset_version"),
                "base_execution_target": base_target,
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
            f"- 대안 resolved target: **{_markdown_value(payload.get('resolved_execution_target'))}**",
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
