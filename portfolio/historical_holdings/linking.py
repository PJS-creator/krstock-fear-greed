from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from portfolio.holdings import normalize_holding_rows

from .models import HistoricalHoldingsError
from .normalization import (
    cash_snapshots_to_dicts,
    holding_snapshots_to_dicts,
    normalize_cash_snapshots,
    normalize_holding_snapshots,
    parse_date,
)


def _normalize_existing_holding_snapshots(rows: Iterable[Mapping[str, Any]]):
    try:
        return normalize_holding_snapshots(rows)
    except HistoricalHoldingsError as exc:
        if "at least one holding snapshot row is required" in str(exc):
            return []
        raise


def current_holdings_to_historical_snapshot(
    rows: Iterable[Mapping[str, Any]],
    as_of_date: object,
) -> list[dict[str, object]]:
    snapshot_date = parse_date(as_of_date)
    current_rows = normalize_holding_rows(rows)
    return [
        {
            "as_of_date": snapshot_date.isoformat(),
            "market": row["market"],
            "ticker": row["ticker"],
            "quantity": row["quantity"],
            "display_name": row["display_name"],
            "currency": row["currency"],
            "account_name": row.get("account_name", ""),
            "strategy_tag": row.get("strategy_tag", ""),
            "note": row.get("note", ""),
        }
        for row in current_rows
    ]


def current_cash_to_historical_snapshot(
    *,
    as_of_date: object,
    cash_krw: object,
    cash_usd: object,
    usd_krw: object,
) -> dict[str, object]:
    snapshot_date = parse_date(as_of_date)
    normalized = normalize_cash_snapshots(
        [
            {
                "as_of_date": snapshot_date.isoformat(),
                "cash_krw": cash_krw,
                "cash_usd": cash_usd,
                "usd_krw": usd_krw,
            }
        ]
    )
    return cash_snapshots_to_dicts(normalized)[0]


def upsert_historical_snapshot(
    existing_rows: Iterable[Mapping[str, Any]],
    snapshot_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, object]]:
    normalized_snapshot = normalize_holding_snapshots(snapshot_rows)
    snapshot_dates = {row.as_of_date for row in normalized_snapshot}
    kept_rows = [
        row
        for row in _normalize_existing_holding_snapshots(existing_rows)
        if row.as_of_date not in snapshot_dates
    ]
    return holding_snapshots_to_dicts(
        sorted([*kept_rows, *normalized_snapshot], key=lambda row: (row.as_of_date, row.market, row.ticker))
    )


def upsert_cash_snapshot(
    existing_rows: Iterable[Mapping[str, Any]],
    cash_row: Mapping[str, Any],
) -> list[dict[str, object]]:
    normalized_cash = normalize_cash_snapshots([cash_row])
    if not normalized_cash:
        raise HistoricalHoldingsError("cash snapshot is required")
    snapshot_date = normalized_cash[0].as_of_date
    kept_rows = [
        row
        for row in normalize_cash_snapshots(existing_rows)
        if row.as_of_date != snapshot_date
    ]
    return cash_snapshots_to_dicts(sorted([*kept_rows, normalized_cash[0]], key=lambda row: row.as_of_date))


def historical_snapshot_to_current_holdings(
    rows: Iterable[Mapping[str, Any]],
    as_of_date: object | None = None,
) -> tuple[date, list[dict[str, object]]]:
    normalized = normalize_holding_snapshots(rows)
    target_date = parse_date(as_of_date) if as_of_date is not None else max(row.as_of_date for row in normalized)
    available_dates = [row.as_of_date for row in normalized if row.as_of_date <= target_date]
    if not available_dates:
        raise HistoricalHoldingsError("No holding snapshot is available on or before the selected date")
    snapshot_date = max(available_dates)
    current_rows = [
        {
            "market": row.market,
            "ticker": row.ticker,
            "quantity": row.quantity,
            "display_name": row.display_name,
            "currency": row.currency,
            "account_name": row.account_name,
            "strategy_tag": row.strategy_tag,
            "note": row.note,
            "current_price": None,
            "previous_close": None,
            "quote_status": "missing",
            "fetched_at": None,
            "provider": None,
        }
        for row in normalized
        if row.as_of_date == snapshot_date
    ]
    return snapshot_date, normalize_holding_rows(current_rows)


def historical_cash_to_current_cash(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of_date: object,
    current_usd_krw: float,
) -> tuple[date, dict[str, float]] | None:
    normalized = normalize_cash_snapshots(rows)
    if not normalized:
        return None
    target_date = parse_date(as_of_date)
    available = [row for row in normalized if row.as_of_date <= target_date]
    if not available:
        return None
    cash_row = max(available, key=lambda row: row.as_of_date)
    return (
        cash_row.as_of_date,
        {
            "cash_krw": float(cash_row.cash_krw),
            "cash_usd": float(cash_row.cash_usd),
            "usd_krw": float(cash_row.usd_krw or current_usd_krw),
        },
    )
