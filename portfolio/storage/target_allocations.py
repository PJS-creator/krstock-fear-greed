from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any, Protocol

from portfolio.rebalancing import serialize_target_allocations

from .base import PortfolioStoreError
from .supabase_store import SupabaseStorageConfig, create_supabase_client, has_supabase_credentials

DEFAULT_TARGET_ALLOCATIONS_TABLE = "target_allocations"


class TargetAllocationStore(Protocol):
    def list_target_allocations(self, user_id: str, portfolio_id: str) -> list[dict[str, object]]:
        ...

    def replace_target_allocations(
        self,
        user_id: str,
        portfolio_id: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, object]]:
        ...


def _clean_identity(user_id: object | None, portfolio_id: object | None) -> tuple[str, str]:
    clean_user = str(user_id or "").strip()
    clean_portfolio = str(portfolio_id or "main").strip() or "main"
    if not clean_user:
        raise PortfolioStoreError("user_id is required")
    return clean_user, clean_portfolio


def _db_row(user_id: str, portfolio_id: str, row: Mapping[str, Any]) -> dict[str, object]:
    clean = serialize_target_allocations([row])[0]
    return {
        "user_id": user_id,
        "portfolio_id": portfolio_id,
        "asset_type": clean["asset_type"],
        "symbol": clean.get("symbol"),
        "market": clean.get("market"),
        "currency": clean["currency"],
        "display_name": clean.get("display_name"),
        "target_weight_pct": clean["target_weight_pct"],
        "current_price": clean.get("current_price"),
        "is_enabled": clean.get("is_enabled", True),
    }


def _allocation_from_db_row(row: Mapping[str, Any]) -> dict[str, object]:
    return serialize_target_allocations(
        [
            {
                "asset_type": row.get("asset_type"),
                "symbol": row.get("symbol"),
                "market": row.get("market"),
                "currency": row.get("currency"),
                "display_name": row.get("display_name"),
                "target_weight_pct": row.get("target_weight_pct"),
                "current_price": row.get("current_price"),
                "is_enabled": row.get("is_enabled", True),
            }
        ]
    )[0]


class MemoryTargetAllocationStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], list[dict[str, object]]] = {}

    def list_target_allocations(self, user_id: str, portfolio_id: str) -> list[dict[str, object]]:
        clean_user, clean_portfolio = _clean_identity(user_id, portfolio_id)
        return deepcopy(self._records.get((clean_user, clean_portfolio), []))

    def replace_target_allocations(
        self,
        user_id: str,
        portfolio_id: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, object]]:
        clean_user, clean_portfolio = _clean_identity(user_id, portfolio_id)
        clean_rows = serialize_target_allocations(rows)
        self._records[(clean_user, clean_portfolio)] = deepcopy(clean_rows)
        return deepcopy(clean_rows)


class SupabaseTargetAllocationStore:
    def __init__(self, config: SupabaseStorageConfig, *, table_name: str = DEFAULT_TARGET_ALLOCATIONS_TABLE) -> None:
        if not has_supabase_credentials(config):
            raise PortfolioStoreError("Supabase storage is not configured")
        self._client = create_supabase_client(config)
        self._table_name = table_name

    def _table(self):
        return self._client.table(self._table_name)

    def list_target_allocations(self, user_id: str, portfolio_id: str) -> list[dict[str, object]]:
        clean_user, clean_portfolio = _clean_identity(user_id, portfolio_id)
        try:
            result = (
                self._table()
                .select("asset_type, symbol, market, currency, display_name, target_weight_pct, current_price, is_enabled")
                .eq("user_id", clean_user)
                .eq("portfolio_id", clean_portfolio)
                .execute()
            )
        except Exception as exc:
            raise PortfolioStoreError("Failed to load target allocations") from exc
        return [_allocation_from_db_row(row) for row in (result.data or [])]

    def replace_target_allocations(
        self,
        user_id: str,
        portfolio_id: str,
        rows: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, object]]:
        clean_user, clean_portfolio = _clean_identity(user_id, portfolio_id)
        clean_rows = serialize_target_allocations(rows)
        try:
            self._table().delete().eq("user_id", clean_user).eq("portfolio_id", clean_portfolio).execute()
            if not clean_rows:
                return []
            db_rows = [_db_row(clean_user, clean_portfolio, row) for row in clean_rows]
            result = self._table().insert(db_rows).execute()
        except Exception as exc:
            raise PortfolioStoreError("Failed to save target allocations") from exc
        saved_rows = result.data or db_rows
        return [_allocation_from_db_row(row) for row in saved_rows]


def build_target_allocation_store(config: SupabaseStorageConfig) -> SupabaseTargetAllocationStore | None:
    if not has_supabase_credentials(config):
        return None
    return SupabaseTargetAllocationStore(config)


def load_target_allocations_prefer_table(
    target_store: TargetAllocationStore | None,
    user_id: str | None,
    portfolio_id: str,
    payload_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, object]]:
    payload_allocations = serialize_target_allocations(payload_rows or [])
    if target_store is None or not user_id:
        return payload_allocations
    try:
        table_allocations = target_store.list_target_allocations(user_id, portfolio_id)
    except PortfolioStoreError:
        return payload_allocations
    if table_allocations:
        return table_allocations
    if payload_allocations:
        try:
            target_store.replace_target_allocations(user_id, portfolio_id, payload_allocations)
        except PortfolioStoreError:
            pass
    return payload_allocations


def save_target_allocations_if_available(
    target_store: TargetAllocationStore | None,
    user_id: str | None,
    portfolio_id: str,
    rows: Iterable[Mapping[str, Any]],
) -> bool:
    if target_store is None or not user_id:
        return False
    try:
        target_store.replace_target_allocations(user_id, portfolio_id, rows)
    except PortfolioStoreError:
        return False
    return True
