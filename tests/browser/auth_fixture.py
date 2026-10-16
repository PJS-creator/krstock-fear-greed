"""Local/CI-only auth UI: synthetic accounts, real browser cookies, no external services."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from app import portfolio_dashboard as dashboard
from app.ui.auth_persistence import begin_cookie_run, get_cookie_manager
from portfolio.auth import AppSecurityConfig
from portfolio.session_persistence import encode_remembered_session
from portfolio.supabase_auth import SupabaseAuthAccount, SupabaseAuthError


SECRET = "local-fixture-only-not-a-real-secret" * 2
ACCOUNT = SupabaseAuthAccount("qa@example.invalid", "qa-owner", "fake-access", "fake-refresh")


class FakeAuthStore:
    def sign_in(self, email, password):
        if email != ACCOUNT.account_id or password != "test-password":
            raise SupabaseAuthError("QA 로그인 정보를 확인하세요.")
        return ACCOUNT

    def restore_session(self, access, refresh):
        st.session_state["qa_restore_count"] = st.session_state.get("qa_restore_count", 0) + 1
        return ACCOUNT

    def sign_out(self):
        st.session_state["qa_signout_count"] = st.session_state.get("qa_signout_count", 0) + 1


class DelayedCookies:
    """Keep returning the old cookie, even after deletion, to reproduce the race."""
    def get(self, cookie):
        return st.session_state.get("qa_stale_cookie")

    def set(self, cookie, val, **kwargs):
        if kwargs.get("max_age") == 0:
            st.session_state["qa_cookie_expirations"] = st.session_state.get("qa_cookie_expirations", 0) + 1
        else:
            st.session_state["qa_stale_cookie"] = val


def auth_store(_config):
    if dashboard.PUBLIC_AUTH_STORE_KEY not in st.session_state:
        st.session_state[dashboard.PUBLIC_AUTH_STORE_KEY] = FakeAuthStore()
    return st.session_state[dashboard.PUBLIC_AUTH_STORE_KEY]


st.set_page_config(page_title="Logout QA", layout="wide")
begin_cookie_run()
dashboard._initialize_theme_state()
dashboard.inject_styles(dashboard._current_theme_mode())
dashboard._initialize_session_state(public_auth_enabled=True)
if st.query_params.get("seed_cookie") == "1" and "qa_seeded" not in st.session_state:
    st.session_state["qa_seeded"] = True
    st.session_state["qa_stale_cookie"] = encode_remembered_session(
        account_id=ACCOUNT.account_id, owner_id=ACCOUNT.owner_id,
        access_token=ACCOUNT.access_token, refresh_token=ACCOUNT.refresh_token, secret=SECRET,
    )

manager = DelayedCookies() if st.query_params.get("cookies") == "fake" else get_cookie_manager()
with patch.object(dashboard, "get_cookie_manager", return_value=manager), \
     patch.object(dashboard, "_auth_session_secret", return_value=SECRET), \
     patch.object(dashboard, "_build_public_auth_store", side_effect=auth_store):
    dashboard._handle_public_logout_query()
    if not dashboard._is_authenticated():
        dashboard._restore_public_auth_session(None)
    if not dashboard._is_authenticated():
        dashboard._render_public_auth_gate(None)
    dashboard._flush_pending_public_auth_cookie()
    dashboard._render_theme_selector()
    st.title("QA 로그인됨")
    dashboard._render_security_status(AppSecurityConfig(None), public_auth_enabled=True)
    dashboard._render_mobile_public_auth_status(public_auth_enabled=True)
    if st.button("QA 다시 실행"):
        dashboard.request_app_rerun()
