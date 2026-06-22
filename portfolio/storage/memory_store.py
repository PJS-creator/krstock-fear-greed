from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .base import PortfolioRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_record(record: PortfolioRecord) -> PortfolioRecord:
    return PortfolioRecord(
        owner_id=record.owner_id,
        portfolio_name=record.portfolio_name,
        payload_json=deepcopy(record.payload_json),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class MemoryPortfolioStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], PortfolioRecord] = {}

    def list_portfolios(self, owner_id: str) -> list[PortfolioRecord]:
        records = [record for (record_owner_id, _), record in self._records.items() if record_owner_id == owner_id]
        records.sort(key=lambda record: record.updated_at or "", reverse=True)
        return [_copy_record(record) for record in records]

    def get_portfolio(self, owner_id: str, portfolio_name: str) -> PortfolioRecord | None:
        record = self._records.get((owner_id, portfolio_name))
        if record is None:
            return None
        return _copy_record(record)

    def save_portfolio(
        self,
        owner_id: str,
        portfolio_name: str,
        payload_json: Mapping[str, Any],
    ) -> PortfolioRecord:
        clean_name = portfolio_name.strip()
        if not clean_name:
            raise ValueError("portfolio_name is required")

        now = _utc_now_iso()
        existing = self._records.get((owner_id, clean_name))
        record = PortfolioRecord(
            owner_id=owner_id,
            portfolio_name=clean_name,
            payload_json=deepcopy(dict(payload_json)),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._records[(owner_id, clean_name)] = record
        return _copy_record(record)

    def delete_portfolio(self, owner_id: str, portfolio_name: str) -> bool:
        return self._records.pop((owner_id, portfolio_name), None) is not None
