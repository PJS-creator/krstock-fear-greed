from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from portfolio.storage.supabase_store import SupabaseStorageConfig, has_supabase_credentials

ACCOUNT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.@-]{2,63}$")
PASSWORD_MIN_LENGTH = 8
PBKDF2_ITERATIONS = 260_000
PASSWORD_ALGORITHM = "pbkdf2_sha256"
DEFAULT_PUBLIC_ACCOUNTS_TABLE = "public_accounts"


class PublicAccountError(RuntimeError):
    pass


class PublicAccountValidationError(ValueError):
    pass


class PublicAccountAlreadyExistsError(PublicAccountError):
    pass


@dataclass(frozen=True)
class PublicAccount:
    account_id: str
    owner_id: str
    created_at: str | None = None
    updated_at: str | None = None


def normalize_account_id(value: object | None) -> str:
    account_id = str(value or "").strip().lower()
    if not ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise PublicAccountValidationError("아이디는 영문 소문자, 숫자, ., _, -, @ 조합의 3~64자로 입력하세요.")
    return account_id


def validate_password(value: object | None) -> str:
    password = str(value or "")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PublicAccountValidationError(f"비밀번호는 {PASSWORD_MIN_LENGTH}자 이상으로 입력하세요.")
    return password


def owner_id_for_account(account_id: str) -> str:
    return f"public:{normalize_account_id(account_id)}"


def hash_password(password: str, *, salt: bytes | None = None) -> tuple[str, str]:
    clean_password = validate_password(password)
    password_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", clean_password.encode("utf-8"), password_salt, PBKDF2_ITERATIONS)
    return (
        base64.urlsafe_b64encode(password_salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password_hash(candidate_password: str | None, password_salt: str, password_hash: str) -> bool:
    try:
        clean_password = validate_password(candidate_password)
        salt = base64.urlsafe_b64decode(password_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(password_hash.encode("ascii"))
    except Exception:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", clean_password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest, expected)


def _account_from_row(row: Mapping[str, Any]) -> PublicAccount:
    return PublicAccount(
        account_id=str(row.get("account_id", "")),
        owner_id=str(row.get("owner_id", "")),
        created_at=str(row["created_at"]) if row.get("created_at") is not None else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") is not None else None,
    )


class SupabasePublicAccountStore:
    def __init__(self, config: SupabaseStorageConfig, *, table_name: str = DEFAULT_PUBLIC_ACCOUNTS_TABLE) -> None:
        if not has_supabase_credentials(config):
            raise PublicAccountError("Supabase 저장소가 설정되지 않았습니다.")
        try:
            from supabase import create_client
        except ImportError as exc:
            raise PublicAccountError("The supabase package is not installed") from exc

        self._table_name = table_name
        try:
            self._client = create_client(config.supabase_url, config.service_role_key)
        except Exception as exc:
            raise PublicAccountError("Supabase 계정 저장소를 초기화할 수 없습니다.") from exc

    def _table(self):
        return self._client.table(self._table_name)

    def get_account(self, account_id: object | None) -> PublicAccount | None:
        normalized = normalize_account_id(account_id)
        try:
            result = self._table().select("account_id, owner_id, created_at, updated_at").eq("account_id", normalized).limit(1).execute()
        except Exception as exc:
            raise PublicAccountError("계정 정보를 불러올 수 없습니다.") from exc
        rows = result.data or []
        if not rows:
            return None
        return _account_from_row(rows[0])

    def create_account(self, account_id: object | None, password: object | None) -> PublicAccount:
        normalized = normalize_account_id(account_id)
        clean_password = validate_password(password)
        if self.get_account(normalized) is not None:
            raise PublicAccountAlreadyExistsError("이미 사용 중인 아이디입니다.")

        password_salt, password_hash = hash_password(clean_password)
        row = {
            "account_id": normalized,
            "owner_id": owner_id_for_account(normalized),
            "password_salt": password_salt,
            "password_hash": password_hash,
            "password_algorithm": PASSWORD_ALGORITHM,
        }
        try:
            result = self._table().insert(row).execute()
        except Exception as exc:
            raise PublicAccountError("계정을 만들 수 없습니다.") from exc
        rows = result.data or [row]
        return _account_from_row(rows[0])

    def verify_account(self, account_id: object | None, password: object | None) -> PublicAccount | None:
        normalized = normalize_account_id(account_id)
        try:
            result = (
                self._table()
                .select("account_id, owner_id, password_salt, password_hash, created_at, updated_at")
                .eq("account_id", normalized)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise PublicAccountError("로그인 정보를 확인할 수 없습니다.") from exc
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        if not verify_password_hash(password, str(row.get("password_salt", "")), str(row.get("password_hash", ""))):
            return None
        return _account_from_row(row)
