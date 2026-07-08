from pathlib import Path

from app.ui.stability import action_is_globally_cooling_down, action_is_recent, build_action_signature, state_flag_is_stale


def test_action_signature_is_stable_for_equivalent_payloads():
    first = build_action_signature("cash_movement", {"amount": 1000, "currency": "KRW"})
    second = build_action_signature("cash_movement", {"currency": "KRW", "amount": 1000})

    assert first == second


def test_action_is_recent_only_blocks_matching_signature_inside_cooldown():
    signature = build_action_signature("apply_transactions", [{"ticker": "QURE", "quantity": 1}])
    guard = {"last_signature": signature, "last_at": 100.0}

    assert action_is_recent(guard, signature=signature, now=100.5, cooldown_seconds=1.0)
    assert not action_is_recent(guard, signature=signature, now=102.0, cooldown_seconds=1.0)
    assert not action_is_recent(guard, signature="other", now=100.5, cooldown_seconds=1.0)


def test_action_global_cooldown_blocks_back_to_back_different_buttons_briefly():
    guard = {"last_signature": "first", "last_at": 100.0}

    assert action_is_globally_cooling_down(guard, now=100.2, cooldown_seconds=0.35)
    assert not action_is_globally_cooling_down(guard, now=100.5, cooldown_seconds=0.35)


def test_state_flag_stale_detects_stuck_long_running_state():
    assert not state_flag_is_stale(False, 1.0, now=500.0, stale_seconds=180.0)
    assert not state_flag_is_stale(True, 400.0, now=500.0, stale_seconds=180.0)
    assert state_flag_is_stale(True, 100.0, now=500.0, stale_seconds=180.0)
    assert state_flag_is_stale(True, None, now=500.0, stale_seconds=180.0)


def test_streamlit_rerun_is_centralized_through_stability_helper():
    direct_calls = []
    for path in Path("app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "st.rerun()" in source and path.as_posix() != "app/ui/stability.py":
            direct_calls.append(path.as_posix())

    assert direct_calls == []


def test_high_risk_state_actions_are_guarded():
    expected_guards = {
        "app/portfolio_dashboard.py": [
            "price_refresh",
            "fx_refresh",
            "sidebar_load_portfolio",
            "sidebar_restore_last_saved",
            "sidebar_reset_portfolio",
        ],
        "app/ui/historical_reconstruction.py": [
            "historical_apply_preview",
            "historical_apply_holdings_csv",
            "historical_apply_cash_csv",
            "historical_run_reconstruction",
        ],
        "app/ui/manage.py": [
            "storage_save_portfolio",
            "storage_load_portfolio",
            "storage_rename_portfolio",
            "storage_delete_portfolio",
            "manual_history_capture",
        ],
        "app/ui/risk.py": ["risk_beta_calculation"],
    }

    for path, guard_keys in expected_guards.items():
        source = Path(path).read_text(encoding="utf-8")
        for guard_key in guard_keys:
            assert guard_key in source
