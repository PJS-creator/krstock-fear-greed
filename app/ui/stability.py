from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from typing import Any

import streamlit as st

ACTION_GUARD_KEY = "app_action_guard"
ACTION_GUARD_NOTICE_KEY = "app_action_guard_notice"
ACTION_STALE_SECONDS = 20.0
DEFAULT_ACTION_COOLDOWN_SECONDS = 1.0
GLOBAL_ACTION_COOLDOWN_SECONDS = 0.35


def build_action_signature(action_key: str, payload: object | None = None) -> str:
    payload_text = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()[:16]
    return f"{action_key}:{digest}"


def action_is_recent(
    guard: Mapping[str, Any] | None,
    *,
    signature: str,
    now: float,
    cooldown_seconds: float,
) -> bool:
    if not guard:
        return False
    return guard.get("last_signature") == signature and now - float(guard.get("last_at") or 0.0) < cooldown_seconds


def action_is_globally_cooling_down(
    guard: Mapping[str, Any] | None,
    *,
    now: float,
    cooldown_seconds: float = GLOBAL_ACTION_COOLDOWN_SECONDS,
) -> bool:
    if not guard:
        return False
    return now - float(guard.get("last_at") or 0.0) < cooldown_seconds


def reset_stale_ui_action_guard(*, now: float | None = None, stale_seconds: float = ACTION_STALE_SECONDS) -> None:
    guard = dict(st.session_state.get(ACTION_GUARD_KEY) or {})
    if not guard.get("running"):
        return
    current_time = time.time() if now is None else now
    started_at = float(guard.get("started_at") or 0.0)
    if current_time - started_at > stale_seconds:
        guard["running"] = False
        guard["stale_cleared_at"] = current_time
        st.session_state[ACTION_GUARD_KEY] = guard


def state_flag_is_stale(
    is_running: object,
    started_at: object,
    *,
    now: float,
    stale_seconds: float,
) -> bool:
    if not is_running:
        return False
    try:
        start = float(started_at)
    except (TypeError, ValueError):
        return True
    if start <= 0:
        return True
    return now - start > stale_seconds


def begin_ui_action(
    action_key: str,
    *,
    payload: object | None = None,
    cooldown_seconds: float = DEFAULT_ACTION_COOLDOWN_SECONDS,
) -> bool:
    reset_stale_ui_action_guard()
    now = time.time()
    guard = dict(st.session_state.get(ACTION_GUARD_KEY) or {})
    if guard.get("running"):
        st.session_state[ACTION_GUARD_NOTICE_KEY] = "이전 작업을 처리 중입니다. 잠시 후 다시 눌러 주세요."
        return False

    signature = build_action_signature(action_key, payload)
    if action_is_globally_cooling_down(guard, now=now):
        st.session_state[ACTION_GUARD_NOTICE_KEY] = "화면을 갱신하는 중입니다. 잠시 후 다시 눌러 주세요."
        return False
    if action_is_recent(guard, signature=signature, now=now, cooldown_seconds=cooldown_seconds):
        st.session_state[ACTION_GUARD_NOTICE_KEY] = "방금 처리한 작업입니다. 화면 갱신 후 다시 시도해 주세요."
        return False

    st.session_state[ACTION_GUARD_KEY] = {
        **guard,
        "running": True,
        "current_key": action_key,
        "current_signature": signature,
        "started_at": now,
    }
    return True


def finish_ui_action(*, success: bool = True) -> None:
    guard = dict(st.session_state.get(ACTION_GUARD_KEY) or {})
    now = time.time()
    if success and guard.get("current_signature"):
        guard["last_signature"] = guard.get("current_signature")
        guard["last_at"] = now
    guard["running"] = False
    guard.pop("current_key", None)
    guard.pop("current_signature", None)
    guard.pop("started_at", None)
    st.session_state[ACTION_GUARD_KEY] = guard


def request_app_rerun() -> None:
    finish_ui_action(success=True)
    st.rerun()


def render_action_guard_notice() -> None:
    notice = st.session_state.pop(ACTION_GUARD_NOTICE_KEY, None)
    if notice:
        st.info(str(notice))
