from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Protocol

from .models import PortfolioHistoryRecord

HistoryPeriod = Literal["1w", "1m", "3m", "all"]


def period_start(period: HistoryPeriod, *, now: datetime | None = None) -> datetime | None:
    if period == "all":
        return None
    current = now or datetime.now(timezone.utc)
    if period == "1w":
        return current - timedelta(days=7)
    if period == "1m":
        return current - timedelta(days=31)
    if period == "3m":
        return current - timedelta(days=93)
    raise ValueError(f"Unsupported history period: {period}")


class PortfolioHistoryStoreError(RuntimeError):
    pass


class PortfolioHistoryStore(Protocol):
    def save_snapshot(self, record: PortfolioHistoryRecord) -> PortfolioHistoryRecord:
        ...

    def list_history(
        self,
        owner_id: str,
        portfolio_name: str,
        *,
        period: HistoryPeriod = "all",
    ) -> list[PortfolioHistoryRecord]:
        ...
