from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


SCHEMA_VERSION = 1


class HistoricalHoldingsError(ValueError):
    pass


class HistoricalPriceProviderError(RuntimeError):
    pass


class HistoricalReconstructionError(RuntimeError):
    pass


@dataclass(frozen=True)
class HoldingSnapshotRow:
    as_of_date: date
    market: str
    ticker: str
    quantity: float
    display_name: str
    currency: str
    account_name: str = ""
    strategy_tag: str = ""
    note: str = ""


@dataclass(frozen=True)
class CashSnapshotRow:
    as_of_date: date
    cash_krw: float = 0.0
    cash_usd: float = 0.0
    usd_krw: float | None = None


@dataclass(frozen=True)
class DailyValuationRow:
    date: date
    total_value_krw: float
    position_value_krw: float
    cash_total_krw: float
    cash_krw: float
    cash_usd: float
    usd_krw: float
    holdings_count: int
    priced_count: int
    missing_price_count: int
    applied_snapshot_date: date


@dataclass(frozen=True)
class HoldingValuationRow:
    date: date
    market: str
    ticker: str
    display_name: str
    quantity: float
    close_price: float | None
    currency: str
    fx_rate: float
    market_value_krw: float | None
    price_status: str
    applied_snapshot_date: date


@dataclass(frozen=True)
class ReconstructionWarning:
    code: str
    message: str
    date: date | None = None
    ticker: str | None = None


@dataclass(frozen=True)
class ReconstructionResult:
    daily_rows: list[DailyValuationRow]
    holding_rows: list[HoldingValuationRow]
    warnings: list[ReconstructionWarning]
    failed_tickers: list[str]
    snapshot_dates: list[date]


@dataclass(frozen=True)
class HistoricalScheduleRecord:
    owner_id: str
    schedule_name: str
    payload_json: dict[str, Any]
    created_at: str | None = None
    updated_at: str | None = None
    id: int | None = None

