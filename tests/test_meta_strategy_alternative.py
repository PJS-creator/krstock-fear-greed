from datetime import date
from pathlib import Path

import pytest

from portfolio import meta_strategy_alternative as alternative
from portfolio.meta_strategy_alternative import (
    advance_a1_overlay,
    apply_n1_overlay,
    build_alternative_meta_strategy_signal,
    build_shadow_entry_plan,
    replay_n1_a1_overlays,
)


def test_n1_changes_only_eligible_bull_qld_target():
    result = apply_n1_overlay(
        market_regime="BULL",
        active_strategy="rsi_aggressive_immediate",
        base_target="QLD",
        router_active=False,
    )

    assert result["applied"] is True
    assert result["base_target"] == "QLD"
    assert result["resolved_target"] == "QQQ"
    assert result["reason_codes"] == ["N1_ALL_CONDITIONS_MET"]


@pytest.mark.parametrize(
    ("market_regime", "active_strategy", "base_target", "router_active"),
    [
        ("MIXED", "rsi_aggressive_immediate", "QLD", False),
        ("BULL", "trend_2d", "QLD", False),
        ("BULL", "rsi_aggressive_immediate", "TQQQ", False),
        ("BULL", "rsi_aggressive_immediate", "QLD", True),
    ],
)
def test_n1_preserves_base_target_when_any_condition_fails(
    market_regime,
    active_strategy,
    base_target,
    router_active,
):
    result = apply_n1_overlay(
        market_regime=market_regime,
        active_strategy=active_strategy,
        base_target=base_target,
        router_active=router_active,
    )

    assert result["applied"] is False
    assert result["resolved_target"] == base_target


def test_entry_v4_uses_post_a1_target_and_does_not_split_qqq():
    result = build_shadow_entry_plan(
        base_target="QLD",
        post_n1_target="QLD",
        post_a1_target="QQQ",
        qqq_close=105.0,
        qqq_sma50=100.0,
        execution_session=date(2026, 8, 3),
        deferred_due_session=date(2026, 10, 27),
    )

    assert result["triggered"] is False
    assert result["mode"] == "IMMEDIATE_100"
    assert result["immediate_target"] == "QQQ"
    assert result["immediate_weight_pct"] == 100.0
    assert result["cash_weight_pct"] == 0.0
    assert "POST_A1_TARGET_NOT_QLD" in result["reason_codes"]


def test_entry_v4_requires_qld_and_accepts_exact_five_percent_threshold():
    exact = build_shadow_entry_plan(
        base_target="QLD",
        post_n1_target="QLD",
        post_a1_target="QLD",
        qqq_close=105.0,
        qqq_sma50=100.0,
        execution_session="2026-08-03",
        deferred_due_session="2026-10-27",
    )
    non_qld = build_shadow_entry_plan(
        base_target="TQQQ",
        post_n1_target="TQQQ",
        post_a1_target="TQQQ",
        qqq_close=120.0,
        qqq_sma50=100.0,
        execution_session="2026-08-03",
        deferred_due_session="2026-10-27",
    )

    assert exact["triggered"] is True
    assert exact["qqq_sma50_upper_distance_pct"] == pytest.approx(5.0)
    assert non_qld["triggered"] is False
    assert non_qld["mode"] == "IMMEDIATE_100"
    assert non_qld["cash_weight_pct"] == 0.0


def test_a1_enters_holds_releases_blocks_same_episode_and_rearms():
    entered = advance_a1_overlay(
        as_of_date=date(2026, 8, 3),
        previous_state=None,
        previous_subtype="BULL",
        current_subtype="UP_MIXED",
        previous_executed_target="QQQ",
        post_n1_target="QLD",
        comparison3_target="QLD",
        router_active=False,
    )
    held = advance_a1_overlay(
        as_of_date=date(2026, 8, 4),
        previous_state=entered,
        previous_subtype="UP_MIXED",
        current_subtype="UP_MIXED",
        previous_executed_target="QQQ",
        post_n1_target="QLD",
        comparison3_target="QLD",
        router_active=False,
    )
    released = advance_a1_overlay(
        as_of_date=date(2026, 8, 5),
        previous_state=held,
        previous_subtype="UP_MIXED",
        current_subtype="UP_MIXED",
        previous_executed_target="QQQ",
        post_n1_target="TQQQ",
        comparison3_target="TQQQ",
        router_active=False,
    )
    blocked = advance_a1_overlay(
        as_of_date=date(2026, 8, 6),
        previous_state=released,
        previous_subtype="UP_MIXED",
        current_subtype="UP_MIXED",
        previous_executed_target="TQQQ",
        post_n1_target="QLD",
        comparison3_target="QLD",
        router_active=False,
    )
    rearmed = advance_a1_overlay(
        as_of_date=date(2026, 8, 7),
        previous_state=blocked,
        previous_subtype="UP_MIXED",
        current_subtype="BULL",
        previous_executed_target="QLD",
        post_n1_target="QQQ",
        comparison3_target="QLD",
        router_active=False,
    )

    assert entered["event"] == "ENTER"
    assert entered["resolved_target"] == "QQQ"
    assert held["event"] == "HOLD"
    assert held["active"] is True
    assert released["event"] == "RELEASE"
    assert released["reentry_blocked"] is True
    assert released["resolved_target"] == "TQQQ"
    assert blocked["event"] == "BLOCKED_REENTRY"
    assert blocked["resolved_target"] == "QLD"
    assert rearmed["event"] == "REARM"
    assert rearmed["reentry_blocked"] is False


def test_a1_replay_uses_fixed_anchor_and_preserves_event_history():
    def row(day, regime, trend, execution, comparison, *, recovery=False):
        return {
            "as_of_date": day,
            "market_regime": regime,
            "trend200": trend,
            "recovery": recovery,
            "active_strategy": "rsi_aggressive_immediate",
            "execution_target": execution,
            "comparison3_ticker": comparison,
            "router_active": False,
        }

    trace = [
        row(date(2010, 2, 10), "BULL", "UP", "QLD", "QLD"),
        row(date(2010, 2, 11), "BULL", "UP", "QLD", "QLD"),
        row(date(2010, 2, 12), "MIXED", "UP", "QLD", "QLD"),
        row(date(2010, 2, 16), "MIXED", "UP", "QLD", "QLD"),
        row(date(2010, 2, 17), "MIXED", "UP", "TQQQ", "TQQQ"),
        row(date(2010, 2, 18), "MIXED", "UP", "QLD", "QLD"),
        row(date(2010, 2, 19), "BULL", "UP", "QLD", "QLD"),
        row(date(2010, 2, 22), "MIXED", "UP", "QLD", "QLD"),
    ]

    result = replay_n1_a1_overlays(trace)

    assert result["as_of_date"] == "2010-02-22"
    assert result["resolved_target"] == "QQQ"
    assert result["a1_overlay"]["event"] == "ENTER"
    assert [item["event"] for item in result["a1_overlay"]["event_history"]] == [
        "ENTER",
        "RELEASE",
        "REARM",
        "ENTER",
    ]


def test_alternative_signal_derives_overlay_without_mutating_canonical_contract(monkeypatch):
    canonical = {
        "schema_version": "1.0",
        "pipeline_version": "meta-strategy-daily-v2",
        "ruleset_version": "official-rules",
        "status": "VALIDATED",
        "decision_session": "2026-07-31",
        "planned_execution_session": "2026-08-03",
        "market_regime": "BULL",
        "market_regime_label": "강세장",
        "active_strategy": "rsi_aggressive_immediate",
        "active_strategy_label": "비교3 · RSI 전환",
        "router_target": None,
        "overall_execution_target": "QLD",
        "liquidity": {"percentile": 83.8461538462},
        "qqq": {"close": 105.0, "sma50": 100.0, "trend200": "UP", "recovery": False},
        "red_router": {"active": False},
        "entry_advice": {"mode": "SPLIT_50_50", "immediate_target": "QLD"},
        "rsi_reference": {"latest_rsi14": 61.0, "warning": True},
        "legacy_view": {"data_mode": "official", "applied_ticker": "QLD"},
    }
    monkeypatch.setattr(
        alternative,
        "build_official_meta_strategy_signal",
        lambda **kwargs: canonical,
    )
    monkeypatch.setattr(alternative, "calculate_exact_liquidity_trace", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        alternative,
        "build_technical_trace",
        lambda *args, **kwargs: [
            {
                "as_of_date": date(2026, 7, 31),
                "market_regime": "BULL",
                "trend200": "UP",
                "recovery": False,
                "active_strategy": "rsi_aggressive_immediate",
                "execution_target": "QLD",
                "comparison3_ticker": "QLD",
                "router_active": False,
            }
        ],
    )

    signal = build_alternative_meta_strategy_signal(
        qqq_points=[],
        gld_points=[],
        liquidity_series={},
        router_series={},
        decision_session=date(2026, 7, 31),
        planned_execution_session=date(2026, 8, 3),
        deferred_due_session=date(2026, 10, 27),
        next_session_after=lambda value: value,
    )

    assert signal["strategy_kind"] == "ALTERNATIVE_SHADOW"
    assert signal["official_strategy_unchanged"] is True
    assert signal["base_execution_target"] == "QLD"
    assert signal["post_n1_execution_target"] == "QQQ"
    assert signal["resolved_execution_target"] == "QQQ"
    assert signal["overall_execution_target"] == "QQQ"
    assert signal["n1_overlay"]["applied"] is True
    assert signal["a1_overlay"]["event"] == "NONE"
    assert signal["entry_filter_v4"]["immediate_target"] == "QQQ"
    assert signal["entry_filter_v4"]["triggered"] is False
    assert signal["canonical_reference"]["base_execution_target"] == "QLD"
    assert canonical["overall_execution_target"] == "QLD"
    assert canonical["legacy_view"]["data_mode"] == "official"


def test_checked_in_strategy_spec_preserves_n1_a1_and_initial_capital_contract():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "config"
        / "strategies"
        / "qqq_meta_v1_red_router_s1_n1_a1_v4_shadow_v3_0.kis.yaml"
    ).read_text(encoding="utf-8")

    assert "id: qqq_meta_v1_red_router_s1_n1_a1_v4_shadow_v3_0" in source
    assert "required_regime: BULL" in source
    assert "base_target_role: moderate" in source
    assert "replacement_target_role: defensive" in source
    assert "id: a1_leverage_monotonicity_latch" in source
    assert "evaluation_order: after_n1_before_entry_filter_v4" in source
    assert "same_up_mixed_episode_reentry: false" in source
    assert "target_source: post_experimental_execution_target" in source
    assert "applies_to: initial_capital_only" in source
    assert "hold_trading_sessions: 60" in source
