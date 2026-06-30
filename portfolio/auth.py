from __future__ import annotations

import json
import hmac
from dataclasses import dataclass
from typing import Mapping

AUTH_SCOPE_ALL = "all"
AUTH_SCOPE_MANUAL = "manual"
VALID_AUTH_SCOPES = {AUTH_SCOPE_ALL, AUTH_SCOPE_MANUAL}


@dataclass(frozen=True)
class AccountConfig:
    account_id: str
    password: str
    owner_id: str
    default_portfolio: str = "main"


@dataclass(frozen=True)
class AppSecurityConfig:
    app_password: str | None
    auth_scope: str = AUTH_SCOPE_ALL
    alpha_vantage_api_key: str | None = None
    accounts: tuple[AccountConfig, ...] = ()
    legacy_owner_id: str | None = None
    legacy_default_portfolio: str = "main"

    @property
    def has_password(self) -> bool:
        return bool(self.app_password or self.accounts)

    @property
    def has_alpha_vantage_api_key(self) -> bool:
        return bool(self.alpha_vantage_api_key)

    @property
    def has_accounts(self) -> bool:
        return bool(self.accounts)


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


def _clean_portfolio_name(value: object | None) -> str:
    return _clean_secret(value) or "main"


def _mapping_from_secret(value: object | None) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, Mapping):
            return decoded
    return {}


def _account_from_secret(account_id: object, value: object) -> AccountConfig | None:
    clean_account_id = _clean_secret(account_id)
    if clean_account_id is None:
        return None

    if isinstance(value, Mapping):
        password = _clean_secret(value.get("password") or value.get("APP_PASSWORD"))
        owner_id = _clean_secret(value.get("owner_id") or value.get("PORTFOLIO_OWNER_ID")) or clean_account_id
        default_portfolio = _clean_portfolio_name(value.get("default_portfolio") or value.get("portfolio_name"))
    else:
        password = _clean_secret(value)
        owner_id = clean_account_id
        default_portfolio = "main"

    if password is None:
        return None
    return AccountConfig(
        account_id=clean_account_id,
        password=password,
        owner_id=owner_id,
        default_portfolio=default_portfolio,
    )


def _accounts_from_secrets(secrets: Mapping[str, object]) -> tuple[AccountConfig, ...]:
    account_values: dict[str, object] = {}
    for key in ("ACCOUNTS", "accounts", "APP_ACCOUNTS"):
        account_values.update(dict(_mapping_from_secret(secrets.get(key))))

    accounts = [
        account
        for account_id, value in account_values.items()
        if (account := _account_from_secret(account_id, value)) is not None
    ]
    accounts.sort(key=lambda account: account.account_id)
    return tuple(accounts)


def config_from_secrets(secrets: Mapping[str, object] | None) -> AppSecurityConfig:
    secrets = secrets or {}
    legacy_default_portfolio = _clean_portfolio_name(secrets.get("DEFAULT_PORTFOLIO_NAME"))
    return AppSecurityConfig(
        app_password=_clean_secret(secrets.get("APP_PASSWORD")),
        auth_scope=normalize_auth_scope(secrets.get("APP_AUTH_SCOPE")),
        alpha_vantage_api_key=_clean_secret(secrets.get("ALPHA_VANTAGE_API_KEY")),
        accounts=_accounts_from_secrets(secrets),
        legacy_owner_id=_clean_secret(secrets.get("PORTFOLIO_OWNER_ID")),
        legacy_default_portfolio=legacy_default_portfolio,
    )


def verify_password(candidate_password: str | None, expected_password: str | None) -> bool:
    candidate = _clean_secret(candidate_password)
    expected = _clean_secret(expected_password)
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate, expected)


def available_account_ids(config: AppSecurityConfig) -> tuple[str, ...]:
    return tuple(account.account_id for account in config.accounts)


def get_account(config: AppSecurityConfig, account_id: str | None) -> AccountConfig | None:
    clean_account_id = _clean_secret(account_id)
    if not clean_account_id:
        return None
    for account in config.accounts:
        if account.account_id == clean_account_id:
            return account
    return None


def verify_account(account_id: str | None, candidate_password: str | None, config: AppSecurityConfig) -> AccountConfig | None:
    if config.accounts:
        account = get_account(config, account_id)
        if account is not None and verify_password(candidate_password, account.password):
            return account
        return None

    if verify_password(candidate_password, config.app_password):
        owner_id = config.legacy_owner_id or "main"
        return AccountConfig(
            account_id=owner_id,
            password=config.app_password or "",
            owner_id=owner_id,
            default_portfolio=config.legacy_default_portfolio,
        )
    return None


def should_lock_entire_app(config: AppSecurityConfig, *, is_authenticated: bool) -> bool:
    return config.has_password and config.auth_scope == AUTH_SCOPE_ALL and not is_authenticated


def should_lock_manual_mode(config: AppSecurityConfig, *, is_authenticated: bool) -> bool:
    return config.has_password and config.auth_scope == AUTH_SCOPE_MANUAL and not is_authenticated


def should_disable_price_update(config: AppSecurityConfig) -> bool:
    # Recent stock price and FX refresh use keyless providers.
    return False
