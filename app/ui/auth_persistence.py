from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

import streamlit as st

from portfolio.session_persistence import DEFAULT_REMEMBER_DAYS, SESSION_COOKIE_NAME

_COOKIE_MANAGER_KEY = "_auth_cookie_manager_for_run"


def begin_cookie_run() -> None:
    # Re-read this browser's component on each rerun, once per script execution.
    st.session_state.pop(_COOKIE_MANAGER_KEY, None)


class CookieManagerLike(Protocol):
    def get(self, cookie: str) -> str | None:
        ...

    def set(self, cookie: str, val: str, *, expires_at: datetime | None = None, **kwargs) -> None:
        ...

    def delete(self, cookie: str) -> None:
        ...


def get_cookie_manager() -> CookieManagerLike | None:
    if _COOKIE_MANAGER_KEY in st.session_state:
        return st.session_state[_COOKIE_MANAGER_KEY]
    try:
        import extra_streamlit_components as stx
    except ImportError:
        st.session_state[_COOKIE_MANAGER_KEY] = None
        return None
    manager = stx.CookieManager(key="public_auth_cookies")
    st.session_state[_COOKIE_MANAGER_KEY] = manager
    return manager


def remember_cookie_expires_at(*, remember_days: int = DEFAULT_REMEMBER_DAYS) -> datetime:
    return datetime.utcnow() + timedelta(days=remember_days)


def set_remember_cookie(cookie_manager: CookieManagerLike | None, token: str, *, remember_days: int = DEFAULT_REMEMBER_DAYS) -> bool:
    if cookie_manager is None:
        return False
    cookie_manager.set(SESSION_COOKIE_NAME, token, expires_at=remember_cookie_expires_at(remember_days=remember_days), secure=True, same_site="strict")
    return True


def get_remember_cookie(cookie_manager: CookieManagerLike | None) -> str | None:
    if cookie_manager is None:
        return None
    try:
        return cookie_manager.get(SESSION_COOKIE_NAME)
    except Exception:
        return None


def delete_remember_cookie(cookie_manager: CookieManagerLike | None) -> None:
    if cookie_manager is None:
        return
    try:
        cookie_manager.delete(SESSION_COOKIE_NAME)
    except Exception:
        return
