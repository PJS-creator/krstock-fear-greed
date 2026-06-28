from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Protocol

from portfolio.storage.supabase_store import SupabaseStorageConfig, should_enable_storage

from .models import HistoricalScheduleRecord, SCHEMA_VERSION
from .normalization import (
    cash_snapshots_to_dicts,
    holding_snapshots_to_dicts,
    normalize_cash_snapshots,
    normalize_holding_snapshots,
)

DEFAULT_SCHEDULE_TABLE_NAME = "historical_holding_schedules"


class HistoricalScheduleStoreError(RuntimeError):
    pass


class HistoricalScheduleStore(Protocol):
    def list_schedules(self, owner_id: str) -> list[HistoricalScheduleRecord]:
        ...

    def get_schedule(self, owner_id: str, schedule_name: str) -> HistoricalScheduleRecord | None:
        ...

    def save_schedule(self, owner_id: str, schedule_name: str, payload_json: Mapping[str, Any]) -> HistoricalScheduleRecord:
        ...

    def delete_schedule(self, owner_id: str, schedule_name: str) -> bool:
        ...


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_text(value: date | str | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def serialize_schedule_payload(
    holdings_snapshots: Iterable[Mapping[str, Any]],
    cash_snapshots: Iterable[Mapping[str, Any]],
    *,
    default_start_date: date | str | None = None,
    default_end_date: date | str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    holdings = normalize_holding_snapshots(holdings_snapshots)
    cash = normalize_cash_snapshots(cash_snapshots)
    return {
        "schema_version": SCHEMA_VERSION,
        "holdings_snapshots": holding_snapshots_to_dicts(holdings),
        "cash_snapshots": cash_snapshots_to_dicts(cash),
        "default_start_date": _date_text(default_start_date),
        "default_end_date": _date_text(default_end_date),
        "notes": str(notes or ""),
    }


def deserialize_schedule_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    version = int(payload.get("schema_version") or 0)
    if version != SCHEMA_VERSION:
        raise HistoricalScheduleStoreError(f"Unsupported historical schedule schema_version: {version}")
    holdings = normalize_holding_snapshots(payload.get("holdings_snapshots") or [])
    cash = normalize_cash_snapshots(payload.get("cash_snapshots") or [])
    return {
        "schema_version": version,
        "holdings_snapshots": holding_snapshots_to_dicts(holdings),
        "cash_snapshots": cash_snapshots_to_dicts(cash),
        "default_start_date": payload.get("default_start_date"),
        "default_end_date": payload.get("default_end_date"),
        "notes": str(payload.get("notes") or ""),
    }


def _copy_record(record: HistoricalScheduleRecord) -> HistoricalScheduleRecord:
    return HistoricalScheduleRecord(
        id=record.id,
        owner_id=record.owner_id,
        schedule_name=record.schedule_name,
        payload_json=deepcopy(record.payload_json),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class MemoryHistoricalScheduleStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], HistoricalScheduleRecord] = {}
        self._next_id = 1

    def list_schedules(self, owner_id: str) -> list[HistoricalScheduleRecord]:
        records = [record for (record_owner_id, _), record in self._records.items() if record_owner_id == owner_id]
        records.sort(key=lambda record: record.updated_at or "", reverse=True)
        return [_copy_record(record) for record in records]

    def get_schedule(self, owner_id: str, schedule_name: str) -> HistoricalScheduleRecord | None:
        record = self._records.get((owner_id, schedule_name))
        return _copy_record(record) if record is not None else None

    def save_schedule(self, owner_id: str, schedule_name: str, payload_json: Mapping[str, Any]) -> HistoricalScheduleRecord:
        clean_name = schedule_name.strip()
        if not clean_name:
            raise HistoricalScheduleStoreError("schedule_name is required")
        now = _utc_now_iso()
        existing = self._records.get((owner_id, clean_name))
        record = HistoricalScheduleRecord(
            id=existing.id if existing else self._next_id,
            owner_id=owner_id,
            schedule_name=clean_name,
            payload_json=deepcopy(dict(payload_json)),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        if existing is None:
            self._next_id += 1
        self._records[(owner_id, clean_name)] = record
        return _copy_record(record)

    def delete_schedule(self, owner_id: str, schedule_name: str) -> bool:
        return self._records.pop((owner_id, schedule_name), None) is not None


def _record_from_row(row: Mapping[str, Any]) -> HistoricalScheduleRecord:
    payload_json = row.get("payload_json")
    return HistoricalScheduleRecord(
        id=int(row["id"]) if row.get("id") is not None else None,
        owner_id=str(row.get("owner_id", "")),
        schedule_name=str(row.get("schedule_name", "")),
        payload_json=dict(payload_json) if isinstance(payload_json, Mapping) else {},
        created_at=str(row["created_at"]) if row.get("created_at") is not None else None,
        updated_at=str(row["updated_at"]) if row.get("updated_at") is not None else None,
    )


class SupabaseHistoricalScheduleStore:
    def __init__(self, config: SupabaseStorageConfig, *, table_name: str = DEFAULT_SCHEDULE_TABLE_NAME) -> None:
        if not should_enable_storage(config):
            raise HistoricalScheduleStoreError("Supabase storage is not configured")
        try:
            from supabase import create_client
        except ImportError as exc:
            raise HistoricalScheduleStoreError("The supabase package is not installed") from exc
        self._table_name = table_name
        try:
            self._client = create_client(config.supabase_url, config.service_role_key)
        except Exception as exc:
            raise HistoricalScheduleStoreError("Failed to create Supabase client") from exc

    def _table(self):
        return self._client.table(self._table_name)

    def list_schedules(self, owner_id: str) -> list[HistoricalScheduleRecord]:
        try:
            result = (
                self._table()
                .select("id, owner_id, schedule_name, payload_json, created_at, updated_at")
                .eq("owner_id", owner_id)
                .order("updated_at", desc=True)
                .execute()
            )
        except Exception as exc:
            raise HistoricalScheduleStoreError("Failed to list historical schedules") from exc
        return [_record_from_row(row) for row in (result.data or [])]

    def get_schedule(self, owner_id: str, schedule_name: str) -> HistoricalScheduleRecord | None:
        try:
            result = (
                self._table()
                .select("id, owner_id, schedule_name, payload_json, created_at, updated_at")
                .eq("owner_id", owner_id)
                .eq("schedule_name", schedule_name)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise HistoricalScheduleStoreError("Failed to load historical schedule") from exc
        rows = result.data or []
        return _record_from_row(rows[0]) if rows else None

    def save_schedule(self, owner_id: str, schedule_name: str, payload_json: Mapping[str, Any]) -> HistoricalScheduleRecord:
        clean_name = schedule_name.strip()
        if not clean_name:
            raise HistoricalScheduleStoreError("schedule_name is required")
        existing = self.get_schedule(owner_id, clean_name)
        now = _utc_now_iso()
        row = {
            "owner_id": owner_id,
            "schedule_name": clean_name,
            "payload_json": dict(payload_json),
            "created_at": existing.created_at if existing else now,
            "updated_at": now,
        }
        try:
            result = self._table().upsert(row, on_conflict="owner_id,schedule_name").execute()
        except Exception as exc:
            raise HistoricalScheduleStoreError("Failed to save historical schedule") from exc
        rows = result.data or [row]
        return _record_from_row(rows[0])

    def delete_schedule(self, owner_id: str, schedule_name: str) -> bool:
        try:
            result = self._table().delete().eq("owner_id", owner_id).eq("schedule_name", schedule_name).execute()
        except Exception as exc:
            raise HistoricalScheduleStoreError("Failed to delete historical schedule") from exc
        return bool(result.data)


def build_supabase_historical_schedule_store(config: SupabaseStorageConfig) -> SupabaseHistoricalScheduleStore | None:
    if not should_enable_storage(config):
        return None
    return SupabaseHistoricalScheduleStore(config)
