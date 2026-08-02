from datetime import date
from pathlib import Path

import pytest

from portfolio import meta_strategy_alternative as alternative
from portfolio.meta_strategy_alternative import (
    apply_n1_overlay,
    build_alternative_meta_strategy_signal,
    build_shadow_entry_plan,
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


def test_entry_v4_uses_pre_n1_qld_target_and_executes_resolved_qqq():
    result = build_shadow_entry_plan(
        base_target="QLD",
        resolved_target="QQQ",
        qqq_close=105.0,
        qqq_sma50=100.0,
        execution_session=date(2026, 8, 3),
        deferred_due_session=date(2026, 10, 27),
    )

    assert result["triggered"] is True
    assert result["mode"] == "SPLIT_50_50"
    assert result["immediate_target"] == "QQQ"
    assert result["immediate_weight_pct"] == 50.0
    assert result["cash_weight_pct"] == 50.0
    assert result["hold_completed_common_sessions"] == 60
    assert result["deferred_due_session"] == date(2026, 10, 27)


def test_entry_v4_requires_qld_and_accepts_exact_five_percent_threshold():
    exact = build_shadow_entry_plan(
        base_target="QLD",
        resolved_target="QLD",
        qqq_close=105.0,
        qqq_sma50=100.0,
        execution_session="2026-08-03",
        deferred_due_session="2026-10-27",
    )
    non_qld = build_shadow_entry_plan(
        base_target="TQQQ",
        resolved_target="TQQQ",
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
        "qqq": {"close": 105.0, "sma50": 100.0},
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
    assert signal["resolved_execution_target"] == "QQQ"
    assert signal["overall_execution_target"] == "QQQ"
    assert signal["n1_overlay"]["applied"] is True
    assert signal["entry_filter_v4"]["immediate_target"] == "QQQ"
    assert signal["canonical_reference"]["base_execution_target"] == "QLD"
    assert canonical["overall_execution_target"] == "QLD"
    assert canonical["legacy_view"]["data_mode"] == "official"


def test_checked_in_strategy_spec_preserves_n1_and_initial_capital_contract():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "config"
        / "strategies"
        / "qqq_meta_v1_red_router_s1_n1_v4_shadow_v2_1.kis.yaml"
    ).read_text(encoding="utf-8")

    assert "id: qqq_meta_v1_red_router_s1_n1_v4_shadow_v2_1" in source
    assert "required_regime: BULL" in source
    assert "base_target_role: moderate" in source
    assert "replacement_target_role: defensive" in source
    assert "applies_to: initial_capital_only" in source
    assert "hold_trading_sessions: 60" in source
