from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .base import PortfolioRecord, PortfolioStoreError

DEFAULT_TABLE_NAME = "portfolio_snapshots"


@dataclass(frozen=True)
class SupabaseStorageConfig:
    supabase_url: str | None
    service_role_key: str | None
    owner_id: str | None
    table_name: str = DEFAULT_TABLE_NAME
    publishable_key: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None

    @property
    def api_key(self) -> str | None:
        return self.service_role_key or self.publishable_key

    @property
    def has_credentials(self) -> bool:
        return bool(self.supabase_url and self.api_key)

    @property
    def is_configured(self) -> bool:
        return self.has_credentials and bool(self.owner_id)

    def with_auth_session(
        self,
        *,
        owner_id: str | None,
        access_token: str | None,
        refresh_token: str | None,
    ) -> "SupabaseStorageConfig":
        return SupabaseStorageConfig(
            supabase_url=self.supabase_url,
            service_role_key=self.service_role_key,
            owner_id=_clean_secret(owner_id),
            table_name=self.table_name,
            publishable_key=self.publishable_key,
            access_token=_clean_secret(access_token),
            refresh_token=_clean_secret(refresh_token),
        )


def _clean_secret(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def supabase_config_from_secrets(secrets: Mapping[str, object] | None) -> SupabaseStorageConfig:
    secrets = secrets or {}
    return SupabaseStorageConfig(
        supabase_url=_clean_secret(secrets.get("SUPABASE_URL")),
        service_role_key=_clean_secret(secrets.get("SUPABASE_SERVICE_ROLE_KEY")),
        owner_id=_clean_secret(secrets.get("PORTFOLIO_OWNER_ID")),
        publishable_key=_clean_secret(secrets.get("SUPABASE_PUBLISHABLE_KEY"))
        or _clean_secret(secrets.get("SUPABASE_ANON_KEY")),
    )


def has_supabase_credentials(config: SupabaseStorageConfig) -> bool:
    return config.has_credentials


def should_enable_storage(config: SupabaseStorageConfig, *, owner_id: str | None = None) -> bool:
    return config.has_credentials and bool(owner_id or config.owner_id)


def build_supabase_store(config: SupabaseStorageConfig, *, client: Any | None = None) -> "SupabasePortfolioStore | None":
    if not has_supabase_credentials(config):
        return None
    return SupabasePortfolioStore(config, client=client)


def _field(source: Any, name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)


def create_supabase_client(config: SupabaseStorageConfig):
    if not has_supabase_credentials(config):
        raise PortfolioStoreError("Supabase storage is not configured")
    try:
        from supabase import create_client
    except ImportError as exc:
        raise PortfolioStoreError("The supabase package is not installed") from exc

    try:
        client = create_client(config.supabase_url, config.api_key)
    except Exception as exc:
        raise PortfolioStoreError("Failed to create Supabase client") from exc

    access_token = config.access_token
    if access_token and config.refresh_token:
        try:
            response = client.auth.set_session(access_token, config.refresh_token)
            session = _field(response, "session")
            access_token = str(_field(session, "access_token") or access_token).strip()
        except Exception:
            pass

    if access_token:
        auth_header = f"Bearer {access_token}"
        client.options.headers["Authorization"] = auth_header
        if hasattr(client, "auth") and hasattr(client.auth, "_headers"):
            client.auth._headers["Authorization"] = auth_header
        if hasattr(client, "_postgrest"):
            client._postgrest = None
        if hasattr(client, "_storage"):
            client._storage = None
        if hasattr(client, "_functions"):
            client._functions = None
    return client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_from_mapping(data: Mapping[str, Any]) -> PortfolioRecord:
    payload_json = data.get("payload_json")
    if not isinstance(payload_json, Mapping):
        payload_json = {}
    return PortfolioRecord(
        owner_id=str(data.get("owner_id", "")),
        portfolio_name=str(data.get("portfolio_name", "")),
        payload_json=dict(payload_json),
        created_at=str(data["created_at"]) if data.get("created_at") is not None else None,
        updated_at=str(data["updated_at"]) if data.get("updated_at") is not None else None,
    )


class SupabasePortfolioStore:
    def __init__(self, config: SupabaseStorageConfig, *, client: Any | None = None) -> None:
        if not has_supabase_credentials(config):
            raise PortfolioStoreError("Supabase storage is not configured")

        self._owner_id = config.owner_id
        self._table_name = config.table_name
        self._client = client if client is not None else create_supabase_client(config)

    def _table(self):
        return self._client.table(self._table_name)

    def list_portfolios(self, owner_id: str) -> list[PortfolioRecord]:
        try:
            result = (
                self._table()
                .select("owner_id, portfolio_name, payload_json, created_at, updated_at")
                .eq("owner_id", owner_id)
                .order("updated_at", desc=True)
                .execute()
            )
        except Exception as exc:
            raise PortfolioStoreError("Failed to list portfolios") from exc
        return [_record_from_mapping(record) for record in (result.data or [])]

    def get_portfolio(self, owner_id: str, portfolio_name: str) -> PortfolioRecord | None:
        try:
            result = (
                self._table()
                .select("owner_id, portfolio_name, payload_json, created_at, updated_at")
                .eq("owner_id", owner_id)
                .eq("portfolio_name", portfolio_name)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise PortfolioStoreError("Failed to load portfolio") from exc

        records = result.data or []
        if not records:
            return None
        return _record_from_mapping(records[0])

    def save_portfolio(
        self,
        owner_id: str,
        portfolio_name: str,
        payload_json: Mapping[str, Any],
    ) -> PortfolioRecord:
        clean_name = portfolio_name.strip()
        if not clean_name:
            raise PortfolioStoreError("portfolio_name is required")

        now = _utc_now_iso()
        row = {
            "owner_id": owner_id,
            "portfolio_name": clean_name,
            "payload_json": dict(payload_json),
            "updated_at": now,
        }
        try:
            result = self._table().upsert(row, on_conflict="owner_id,portfolio_name").execute()
        except Exception as exc:
            raise PortfolioStoreError("Failed to save portfolio") from exc

        records = result.data or [row]
        return _record_from_mapping(records[0])

    def delete_portfolio(self, owner_id: str, portfolio_name: str) -> bool:
        try:
            result = (
                self._table()
                .delete()
                .eq("owner_id", owner_id)
                .eq("portfolio_name", portfolio_name)
                .execute()
            )
        except Exception as exc:
            raise PortfolioStoreError("Failed to delete portfolio") from exc
        return bool(result.data)
