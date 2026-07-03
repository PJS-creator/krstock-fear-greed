from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from portfolio.storage.supabase_store import SupabaseStorageConfig

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN_LENGTH = 8


class SupabaseAuthError(RuntimeError):
    pass


class SupabaseAuthValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SupabaseAuthAccount:
    account_id: str
    owner_id: str
    access_token: str
    refresh_token: str


@dataclass(frozen=True)
class SupabaseSignupResult:
    account: SupabaseAuthAccount | None
    confirmation_required: bool = False


def normalize_email(value: object | None) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise SupabaseAuthValidationError("올바른 이메일 주소를 입력하세요.")
    return email


def validate_password(value: object | None) -> str:
    password = str(value or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise SupabaseAuthValidationError(f"비밀번호는 {PASSWORD_MIN_LENGTH}자 이상으로 입력하세요.")
    return password


def _field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def account_from_auth_response(response: Any) -> SupabaseAuthAccount | None:
    session = _field(response, "session")
    if session is None:
        return None
    user = _field(session, "user") or _field(response, "user")
    owner_id = str(_field(user, "id") or "").strip()
    email = str(_field(user, "email") or "").strip().lower()
    access_token = str(_field(session, "access_token") or "").strip()
    refresh_token = str(_field(session, "refresh_token") or "").strip()
    if not owner_id or not access_token or not refresh_token:
        raise SupabaseAuthError("Supabase 로그인 응답에 필요한 세션 정보가 없습니다.")
    return SupabaseAuthAccount(
        account_id=email or owner_id,
        owner_id=owner_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )


class SupabaseAuthStore:
    def __init__(self, config: SupabaseStorageConfig) -> None:
        if not config.supabase_url or not config.publishable_key:
            raise SupabaseAuthError("Streamlit Secrets에 SUPABASE_URL과 SUPABASE_PUBLISHABLE_KEY 또는 SUPABASE_ANON_KEY가 필요합니다.")
        try:
            from supabase import create_client
        except ImportError as exc:
            raise SupabaseAuthError("The supabase package is not installed") from exc
        try:
            self._client = create_client(config.supabase_url, config.publishable_key)
        except Exception as exc:
            raise SupabaseAuthError("Supabase Auth 클라이언트를 초기화할 수 없습니다.") from exc

    def sign_in(self, email: object | None, password: object | None) -> SupabaseAuthAccount:
        clean_email = normalize_email(email)
        clean_password = validate_password(password)
        try:
            response = self._client.auth.sign_in_with_password({"email": clean_email, "password": clean_password})
        except Exception as exc:
            raise SupabaseAuthError("로그인 정보를 확인할 수 없습니다.") from exc
        account = account_from_auth_response(response)
        if account is None:
            raise SupabaseAuthError("로그인 세션을 만들 수 없습니다.")
        return account

    def sign_up(self, email: object | None, password: object | None) -> SupabaseSignupResult:
        clean_email = normalize_email(email)
        clean_password = validate_password(password)
        try:
            response = self._client.auth.sign_up({"email": clean_email, "password": clean_password})
        except Exception as exc:
            raise SupabaseAuthError("회원가입을 완료할 수 없습니다.") from exc
        account = account_from_auth_response(response)
        return SupabaseSignupResult(account=account, confirmation_required=account is None)
