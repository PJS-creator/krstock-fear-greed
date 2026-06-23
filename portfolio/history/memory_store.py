from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from .base import HistoryPeriod, period_start
from .models import PortfolioHistoryRecord


def _copy_record(record: PortfolioHistoryRecord) -> PortfolioHistoryRecord:
    return PortfolioHistoryRecord(
        id=record.id,
        owner_id=record.owner_id,
        portfolio_name=record.portfolio_name,
        captured_at=record.captured_at,
        event_type=record.event_type,
        total_value_krw=record.total_value_krw,
        total_position_value_krw=record.total_position_value_krw,
        cash_krw=record.cash_krw,
        cash_usd=record.cash_usd,
        cash_total_krw=record.cash_total_krw,
        usd_krw=record.usd_krw,
        day_change_krw=record.day_change_krw,
        day_change_pct=record.day_change_pct,
        holdings_count=record.holdings_count,
        stale_quote_count=record.stale_quote_count,
        payload_json=deepcopy(record.payload_json),
        fingerprint=record.fingerprint,
    )


class MemoryPortfolioHistoryStore:
    def __init__(self) -> None:
        self._records: list[PortfolioHistoryRecord] = []
        self._next_id = 1

    def save_snapshot(self, record: PortfolioHistoryRecord) -> PortfolioHistoryRecord:
        for existing in self._records:
            if (
                existing.owner_id == record.owner_id
                and existing.portfolio_name == record.portfolio_name
                and existing.fingerprint == record.fingerprint
            ):
                return _copy_record(existing)
        saved = PortfolioHistoryRecord(**{**record.__dict__, "id": self._next_id})
        self._next_id += 1
        self._records.append(saved)
        return _copy_record(saved)

    def list_history(
        self,
        owner_id: str,
        portfolio_name: str,
        *,
        period: HistoryPeriod = "all",
    ) -> list[PortfolioHistoryRecord]:
        start = period_start(period)
        records = [
            record
            for record in self._records
            if record.owner_id == owner_id and record.portfolio_name == portfolio_name
        ]
        if start is not None:
            records = [
                record
                for record in records
                if datetime.fromisoformat(record.captured_at.replace("Z", "+00:00")) >= start
            ]
        records.sort(key=lambda record: record.captured_at)
        return [_copy_record(record) for record in records]
