from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from threading import RLock

from .base import PORTFOLIO_CONFLICT_MESSAGE, PortfolioConflictError, PortfolioRecord


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
        self._lock = RLock()

    def save_portfolio_if_unchanged(
        self, owner_id: str, portfolio_name: str, payload_json: Mapping[str, Any],
        *, expected_updated_at: str | None,
    ) -> PortfolioRecord:
        with self._lock:
            existing = self._records.get((owner_id, portfolio_name.strip()))
            if (existing is None) != (expected_updated_at is None) or (
                existing is not None and existing.updated_at != expected_updated_at
            ):
                raise PortfolioConflictError(PORTFOLIO_CONFLICT_MESSAGE)
            return self.save_portfolio(owner_id, portfolio_name, payload_json)

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
        with self._lock:
            return self._save_portfolio(owner_id, portfolio_name, payload_json)

    def _save_portfolio(self, owner_id, portfolio_name, payload_json) -> PortfolioRecord:
        clean_name = portfolio_name.strip()
        if not clean_name:
            raise ValueError("portfolio_name is required")

        now = _utc_now_iso()
        existing = self._records.get((owner_id, clean_name))
        if existing and existing.updated_at:
            previous = datetime.fromisoformat(existing.updated_at)
            # Every write needs a new CAS version even if the clock stalls or moves back.
            if datetime.fromisoformat(now) <= previous:
                now = (previous + timedelta(microseconds=1)).isoformat()
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
        with self._lock:
            return self._records.pop((owner_id, portfolio_name), None) is not None
