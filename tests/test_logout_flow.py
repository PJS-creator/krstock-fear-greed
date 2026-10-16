from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import portfolio_dashboard as dashboard
from app.ui import auth_persistence
from portfolio.supabase_auth import SupabaseAuthAccount, SupabaseAuthError


@pytest.fixture
def browser_state(monkeypatch):
    state = {
        dashboard.AUTHENTICATED_KEY: True,
        dashboard.ACCOUNT_ID_KEY: "user@example.invalid",
        dashboard.OWNER_ID_KEY: "owner-a",
        dashboard.AUTH_ACCESS_TOKEN_KEY: "access",
        dashboard.AUTH_REFRESH_TOKEN_KEY: "refresh",
    }
    query = {"view": "summary"}
    fake_st = SimpleNamespace(session_state=state, query_params=query)
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(auth_persistence, "st", fake_st)
    monkeypatch.setattr(dashboard, "_reset_current_portfolio_state", Mock())
    return state, query


def test_logout_blocks_delayed_cookie_restore_and_clears_credentials(monkeypatch, browser_state):
    state, query = browser_state
    store = Mock()
    state[dashboard.PUBLIC_AUTH_STORE_KEY] = store
    cookies = Mock()
    cookies.get.return_value = "stale-cookie-still-in-browser"
    monkeypatch.setattr(dashboard, "get_cookie_manager", Mock(return_value=cookies))
    restore_store = Mock()
    monkeypatch.setattr(dashboard, "_build_public_auth_store", restore_store)

    dashboard._logout(cookies, public_auth_enabled=True)
    store.sign_out.assert_called_once_with()
    assert state[dashboard.AUTHENTICATED_KEY] is False
    assert state[dashboard.ACCOUNT_STATUS_KEY] == "로그아웃했습니다."
    for key in (dashboard.ACCOUNT_ID_KEY, dashboard.OWNER_ID_KEY,
                dashboard.AUTH_ACCESS_TOKEN_KEY, dashboard.AUTH_REFRESH_TOKEN_KEY,
                dashboard.PUBLIC_AUTH_STORE_KEY):
        assert key not in state
    assert query == {"view": "summary", "app_logout": "1"}
    for _ in range(3):
        auth_persistence.begin_cookie_run()
        assert dashboard._restore_public_auth_session(None) is False
    restore_store.assert_not_called()
    cookies.get.assert_not_called()


def test_server_sign_out_failure_does_not_keep_user_logged_in(browser_state):
    state, _ = browser_state
    state[dashboard.PUBLIC_AUTH_STORE_KEY] = Mock(sign_out=Mock(side_effect=SupabaseAuthError("offline")))
    dashboard._logout(None, public_auth_enabled=True)
    assert state[dashboard.AUTHENTICATED_KEY] is False
    assert state[dashboard.PUBLIC_LOGGED_OUT_KEY] is True
    assert dashboard.AUTH_REFRESH_TOKEN_KEY not in state


def test_mobile_logout_intent_survives_fresh_session_and_is_idempotent(monkeypatch, browser_state):
    state, query = browser_state
    state.clear()
    query[dashboard.PUBLIC_LOGOUT_QUERY_KEY] = "1"
    cookies = Mock()
    monkeypatch.setattr(dashboard, "get_cookie_manager", Mock(return_value=cookies))
    for _ in range(3):
        dashboard._handle_public_logout_query()
        assert dashboard._restore_public_auth_session(None) is False
    dashboard._reset_current_portfolio_state.assert_called_once_with()
    assert query[dashboard.PUBLIC_LOGOUT_QUERY_KEY] == "1"


def test_only_explicit_sign_in_clears_logout_intent(monkeypatch, browser_state):
    state, query = browser_state
    state[dashboard.PUBLIC_LOGGED_OUT_KEY] = True
    query[dashboard.PUBLIC_LOGOUT_QUERY_KEY] = "1"
    account = SupabaseAuthAccount("next@example.invalid", "owner-b", "new-access", "new-refresh")
    authenticate, remember = Mock(), Mock()
    monkeypatch.setattr(dashboard, "_authenticate_public_account", authenticate)
    monkeypatch.setattr(dashboard, "_remember_public_auth_session", remember)
    dashboard._complete_public_sign_in(account, remember=True)
    assert dashboard.PUBLIC_LOGGED_OUT_KEY not in state
    assert query == {"view": "summary"}
    authenticate.assert_called_once_with(account)
    remember.assert_not_called()
    assert state[dashboard.PUBLIC_REMEMBER_PENDING_KEY] is True


def test_sign_in_cookie_command_runs_once_on_authenticated_render(monkeypatch, browser_state):
    state, _ = browser_state
    state[dashboard.PUBLIC_REMEMBER_PENDING_KEY] = False
    cookies, remember = Mock(), Mock()
    monkeypatch.setattr(dashboard, "get_cookie_manager", lambda: cookies)
    monkeypatch.setattr(dashboard, "_remember_public_auth_session", remember)
    dashboard._flush_pending_public_auth_cookie()
    dashboard._flush_pending_public_auth_cookie()
    remember.assert_called_once_with(
        SupabaseAuthAccount("user@example.invalid", "owner-a", "access", "refresh"),
        cookies, remember=False,
    )
    state[dashboard.PUBLIC_REMEMBER_PENDING_KEY] = True
    dashboard._logout(cookies, public_auth_enabled=True)
    assert dashboard.PUBLIC_REMEMBER_PENDING_KEY not in state
    dashboard._flush_pending_public_auth_cookie()
    assert remember.call_count == 1


def test_cookie_expiration_works_with_empty_snapshot_and_is_once_per_run(browser_state):
    cookies = Mock(cookies={})
    auth_persistence.delete_remember_cookie(cookies)
    auth_persistence.delete_remember_cookie(cookies)
    cookies.set.assert_called_once()
    name, value = cookies.set.call_args.args
    options = cookies.set.call_args.kwargs
    assert name == auth_persistence.SESSION_COOKIE_NAME
    assert value == ""
    assert options["path"] == "/"
    assert options["max_age"] == 0
    assert options["expires_at"].year == 1970
    assert options["secure"] is True
    assert options["same_site"] == "strict"
    auth_persistence.begin_cookie_run()
    auth_persistence.delete_remember_cookie(cookies)
    assert cookies.set.call_count == 2


def test_mobile_logout_runs_before_restore_and_protected_data(monkeypatch, browser_state):
    state, query = browser_state
    state.clear()
    query[dashboard.PUBLIC_LOGOUT_QUERY_KEY] = "1"
    dashboard.st.set_page_config = Mock()
    for name in ("_stop_if_unsupported_python_runtime", "begin_cookie_run", "_initialize_theme_state",
                 "inject_styles", "inject_public_cloud_chrome_guard", "_initialize_session_state"):
        monkeypatch.setattr(dashboard, name, Mock())
    monkeypatch.setattr(dashboard, "_current_theme_mode", lambda: "dark")
    monkeypatch.setattr(dashboard, "_read_security_config", lambda: None)
    monkeypatch.setattr(dashboard, "_read_storage_config", lambda **kwargs: None)
    monkeypatch.setattr(dashboard, "get_cookie_manager", lambda: None)
    protected_stores = Mock()
    monkeypatch.setattr(dashboard, "_build_stores", protected_stores)

    class LoginScreen(Exception):
        pass

    def login_gate(config):
        assert state[dashboard.PUBLIC_LOGGED_OUT_KEY]
        assert not dashboard._is_authenticated()
        raise LoginScreen

    monkeypatch.setattr(dashboard, "_render_public_auth_gate", login_gate)
    with pytest.raises(LoginScreen):
        dashboard.run_dashboard(public_auth_enabled=True)
    protected_stores.assert_not_called()
