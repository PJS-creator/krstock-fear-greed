from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from portfolio.storage.supabase_store import PortfolioStoreError, SupabaseStorageConfig, create_supabase_client, has_supabase_credentials

from .base import HistoryPeriod, PortfolioHistoryStoreError, period_start
from .models import PortfolioHistoryRecord

DEFAULT_HISTORY_TABLE_NAME = "portfolio_value_history"


def _record_to_row(record: PortfolioHistoryRecord) -> dict[str, Any]:
    return {
        "owner_id": record.owner_id,
        "portfolio_name": record.portfolio_name,
        "captured_at": record.captured_at,
        "event_type": record.event_type,
        "total_value_krw": record.total_value_krw,
        "total_position_value_krw": record.total_position_value_krw,
        "cash_krw": record.cash_krw,
        "cash_usd": record.cash_usd,
        "cash_total_krw": record.cash_total_krw,
        "usd_krw": record.usd_krw,
        "day_change_krw": record.day_change_krw,
        "day_change_pct": record.day_change_pct,
        "holdings_count": record.holdings_count,
        "stale_quote_count": record.stale_quote_count,
        "payload_json": record.payload_json,
        "fingerprint": record.fingerprint,
    }


def _record_from_row(row: Mapping[str, Any]) -> PortfolioHistoryRecord:
    payload_json = row.get("payload_json")
    return PortfolioHistoryRecord(
        id=int(row["id"]) if row.get("id") is not None else None,
        owner_id=str(row.get("owner_id", "")),
        portfolio_name=str(row.get("portfolio_name", "")),
        captured_at=str(row.get("captured_at", "")),
        event_type=str(row.get("event_type", "")),
        total_value_krw=float(row.get("total_value_krw") or 0.0),
        total_position_value_krw=float(row.get("total_position_value_krw") or 0.0),
        cash_krw=float(row.get("cash_krw") or 0.0),
        cash_usd=float(row.get("cash_usd") or 0.0),
        cash_total_krw=float(row.get("cash_total_krw") or 0.0),
        usd_krw=float(row.get("usd_krw") or 0.0),
        day_change_krw=float(row["day_change_krw"]) if row.get("day_change_krw") is not None else None,
        day_change_pct=float(row["day_change_pct"]) if row.get("day_change_pct") is not None else None,
        holdings_count=int(row.get("holdings_count") or 0),
        stale_quote_count=int(row.get("stale_quote_count") or 0),
        payload_json=dict(payload_json) if isinstance(payload_json, Mapping) else {},
        fingerprint=str(row.get("fingerprint", "")),
    )


class SupabasePortfolioHistoryStore:
    def __init__(self, config: SupabaseStorageConfig, *, table_name: str = DEFAULT_HISTORY_TABLE_NAME) -> None:
        if not has_supabase_credentials(config):
            raise PortfolioHistoryStoreError("Supabase storage is not configured")
        self._table_name = table_name
        try:
            self._client = create_supabase_client(config)
        except PortfolioStoreError as exc:
            raise PortfolioHistoryStoreError("Failed to create Supabase client") from exc

    def _table(self):
        return self._client.table(self._table_name)

    def save_snapshot(self, record: PortfolioHistoryRecord) -> PortfolioHistoryRecord:
        try:
            existing = (
                self._table()
                .select("*")
                .eq("owner_id", record.owner_id)
                .eq("portfolio_name", record.portfolio_name)
                .eq("fingerprint", record.fingerprint)
                .limit(1)
                .execute()
            )
            if existing.data:
                return _record_from_row(existing.data[0])
            result = self._table().insert(_record_to_row(record)).execute()
        except Exception as exc:
            raise PortfolioHistoryStoreError("Failed to save portfolio history snapshot") from exc
        rows = result.data or [_record_to_row(record)]
        return _record_from_row(rows[0])

    def list_history(
        self,
        owner_id: str,
        portfolio_name: str,
        *,
        period: HistoryPeriod = "all",
    ) -> list[PortfolioHistoryRecord]:
        try:
            query = (
                self._table()
                .select("*")
                .eq("owner_id", owner_id)
                .eq("portfolio_name", portfolio_name)
                .order("captured_at", desc=False)
            )
            start = period_start(period)
            if start is not None:
                query = query.gte("captured_at", start.isoformat())
            result = query.execute()
        except Exception as exc:
            raise PortfolioHistoryStoreError("Failed to list portfolio history") from exc
        return [_record_from_row(row) for row in (result.data or [])]


def build_supabase_history_store(config: SupabaseStorageConfig) -> SupabasePortfolioHistoryStore | None:
    if not has_supabase_credentials(config):
        return None
    return SupabasePortfolioHistoryStore(config)
