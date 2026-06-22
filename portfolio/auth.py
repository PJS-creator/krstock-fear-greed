from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Mapping

AUTH_SCOPE_ALL = "all"
AUTH_SCOPE_MANUAL = "manual"
VALID_AUTH_SCOPES = {AUTH_SCOPE_ALL, AUTH_SCOPE_MANUAL}


@dataclass(frozen=True)
class AppSecurityConfig:
    app_password: str | None
    auth_scope: str = AUTH_SCOPE_ALL
    alpha_vantage_api_key: str | None = None

    @property
    def has_password(self) -> bool:
        return bool(self.app_password)

    @property
    def has_alpha_vantage_api_key(self) -> bool:
        return bool(self.alpha_vantage_api_key)


def _clean_secret(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_auth_scope(value: object | None) -> str:
    scope = str(value or AUTH_SCOPE_ALL).strip().lower()
    if scope not in VALID_AUTH_SCOPES:
        return AUTH_SCOPE_ALL
    return scope


def config_from_secrets(secrets: Mapping[str, object] | None) -> AppSecurityConfig:
    secrets = secrets or {}
    return AppSecurityConfig(
        app_password=_clean_secret(secrets.get("APP_PASSWORD")),
        auth_scope=normalize_auth_scope(secrets.get("APP_AUTH_SCOPE")),
        alpha_vantage_api_key=_clean_secret(secrets.get("ALPHA_VANTAGE_API_KEY")),
    )


def verify_password(candidate_password: str | None, expected_password: str | None) -> bool:
    candidate = _clean_secret(candidate_password)
    expected = _clean_secret(expected_password)
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate, expected)


def should_lock_entire_app(config: AppSecurityConfig, *, is_authenticated: bool) -> bool:
    return config.has_password and config.auth_scope == AUTH_SCOPE_ALL and not is_authenticated


def should_lock_manual_mode(config: AppSecurityConfig, *, is_authenticated: bool) -> bool:
    return config.has_password and config.auth_scope == AUTH_SCOPE_MANUAL and not is_authenticated


def should_disable_price_update(config: AppSecurityConfig) -> bool:
    return config.has_alpha_vantage_api_key and not config.has_password
