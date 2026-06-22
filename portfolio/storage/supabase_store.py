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

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.service_role_key and self.owner_id)


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
    )


def should_enable_storage(config: SupabaseStorageConfig) -> bool:
    return config.is_configured


def build_supabase_store(config: SupabaseStorageConfig) -> "SupabasePortfolioStore | None":
    if not should_enable_storage(config):
        return None
    return SupabasePortfolioStore(config)


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
    def __init__(self, config: SupabaseStorageConfig) -> None:
        if not should_enable_storage(config):
            raise PortfolioStoreError("Supabase storage is not configured")
        try:
            from supabase import create_client
        except ImportError as exc:
            raise PortfolioStoreError("The supabase package is not installed") from exc

        self._owner_id = config.owner_id
        self._table_name = config.table_name
        try:
            self._client = create_client(config.supabase_url, config.service_role_key)
        except Exception as exc:
            raise PortfolioStoreError("Failed to create Supabase client") from exc

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

        existing = self.get_portfolio(owner_id, clean_name)
        now = _utc_now_iso()
        row = {
            "owner_id": owner_id,
            "portfolio_name": clean_name,
            "payload_json": dict(payload_json),
            "created_at": existing.created_at if existing else now,
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
