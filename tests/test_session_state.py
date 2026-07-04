import os

from streamlit.testing.v1 import AppTest


def test_public_app_initializes_core_session_state_keys():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.run(timeout=20)

    assert not at.exception
    for key in (
        "portfolio_name",
        "portfolio_transactions",
        "cash_ledger_entries",
        "target_allocations",
        "holdings_rows",
        "usd_krw",
        "theme_mode",
        "app_theme_mode",
    ):
        assert key in at.session_state
    assert at.session_state["portfolio_name"] == "main"
    assert at.session_state["app_theme_mode"] in {"dark", "light"}
    assert at.session_state["theme_mode"] == at.session_state["app_theme_mode"]


def test_theme_toggle_preserves_public_navigation_and_inputs():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["public_dashboard_section"] = "input"
    at.session_state["public_holdings_view"] = "cash_fx"
    at.session_state["cash_ledger_entries"] = [{"event_date": "2026-01-01", "currency": "KRW", "event_type": "deposit", "amount": "10000"}]
    at.session_state["app_theme_choice"] = "라이트"
    at.run(timeout=20)

    assert not at.exception
    assert at.session_state["app_theme_mode"] == "light"
    assert at.session_state["theme_mode"] == "light"
    assert at.session_state["public_dashboard_section"] == "input"
    assert at.session_state["public_holdings_view"] == "cash_fx"
    assert at.session_state["cash_ledger_entries"][0]["amount"] == "10000"


def test_public_entrypoint_restores_public_auth_environment_flag():
    previous = os.environ.get("PORTFOLIO_PUBLIC_AUTH")
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.run(timeout=20)

    assert not at.exception
    assert os.environ.get("PORTFOLIO_PUBLIC_AUTH") == previous
