from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

SESSION_COOKIE_NAME = "krstock_auth_session"
SESSION_SECRET_MIN_LENGTH = 32
DEFAULT_REMEMBER_DAYS = 30


class SessionPersistenceError(ValueError):
    pass


@dataclass(frozen=True)
class RememberedAuthSession:
    account_id: str
    owner_id: str
    access_token: str
    refresh_token: str
    expires_at: int


def validate_session_secret(secret: object | None) -> str:
    clean = str(secret or "").strip()
    if len(clean) < SESSION_SECRET_MIN_LENGTH:
        raise SessionPersistenceError(f"AUTH_SESSION_SECRET must be at least {SESSION_SECRET_MIN_LENGTH} characters")
    return clean


def _fernet_for_secret(secret: object | None) -> Fernet:
    clean = validate_session_secret(secret)
    key = base64.urlsafe_b64encode(hashlib.sha256(clean.encode("utf-8")).digest())
    return Fernet(key)


def _clean_required(name: str, value: object | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise SessionPersistenceError(f"{name} is required")
    return text


def encode_remembered_session(
    *,
    account_id: object | None,
    owner_id: object | None,
    access_token: object | None,
    refresh_token: object | None,
    secret: object | None,
    remember_days: int = DEFAULT_REMEMBER_DAYS,
    now: int | None = None,
) -> str:
    if remember_days <= 0:
        raise SessionPersistenceError("remember_days must be positive")
    current_time = int(time.time() if now is None else now)
    payload = {
        "version": 1,
        "account_id": _clean_required("account_id", account_id),
        "owner_id": _clean_required("owner_id", owner_id),
        "access_token": _clean_required("access_token", access_token),
        "refresh_token": _clean_required("refresh_token", refresh_token),
        "issued_at": current_time,
        "expires_at": current_time + remember_days * 24 * 60 * 60,
    }
    token = _fernet_for_secret(secret).encrypt(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return token.decode("ascii")


def decode_remembered_session(token: object | None, *, secret: object | None, now: int | None = None) -> RememberedAuthSession:
    token_text = str(token or "").strip()
    if not token_text:
        raise SessionPersistenceError("session token is required")
    try:
        payload = json.loads(_fernet_for_secret(secret).decrypt(token_text.encode("ascii")).decode("utf-8"))
    except (InvalidToken, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionPersistenceError("remembered session is invalid") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise SessionPersistenceError("remembered session version is invalid")
    expires_at = int(payload.get("expires_at") or 0)
    current_time = int(time.time() if now is None else now)
    if expires_at <= current_time:
        raise SessionPersistenceError("remembered session is expired")
    return RememberedAuthSession(
        account_id=_clean_required("account_id", payload.get("account_id")),
        owner_id=_clean_required("owner_id", payload.get("owner_id")),
        access_token=_clean_required("access_token", payload.get("access_token")),
        refresh_token=_clean_required("refresh_token", payload.get("refresh_token")),
        expires_at=expires_at,
    )


def remembered_session_to_public_payload(session: RememberedAuthSession) -> dict[str, Any]:
    return {
        "account_id": session.account_id,
        "owner_id": session.owner_id,
        "expires_at": session.expires_at,
    }
