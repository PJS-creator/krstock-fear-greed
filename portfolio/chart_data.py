from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .history import HistoryPeriod, PortfolioHistoryRecord, period_start
from .holdings import PortfolioMetrics


def holdings_allocation_frame(metrics: PortfolioMetrics) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in metrics.rows:
        if item.market_value_krw is None or item.market_value_krw <= 0:
            continue
        rows.append(
            {
                "ticker": item.holding["ticker"],
                "display_name": item.holding["display_name"],
                "market_value_krw": item.market_value_krw,
                "weight": item.weight,
                "currency": item.holding["currency"],
            }
        )
    return pd.DataFrame(rows)


def contribution_frame(metrics: PortfolioMetrics) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in metrics.rows:
        if item.day_change_krw is None:
            continue
        rows.append(
            {
                "ticker": item.holding["ticker"],
                "display_name": item.holding["display_name"],
                "day_change_krw": item.day_change_krw,
                "day_change_pct": item.day_change_pct,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("day_change_krw")


def currency_exposure_frame(metrics: PortfolioMetrics) -> pd.DataFrame:
    krw_position_value = sum(
        item.market_value_krw or 0.0
        for item in metrics.rows
        if item.holding.get("currency") == "KRW"
    )
    usd_position_value = sum(
        item.market_value_krw or 0.0
        for item in metrics.rows
        if item.holding.get("currency") == "USD"
    )
    rows = [
        {"currency": "KRW 자산", "value_krw": krw_position_value + metrics.cash.cash_krw},
        {"currency": "USD 자산", "value_krw": usd_position_value + metrics.cash.cash_usd * metrics.usd_krw},
    ]
    return pd.DataFrame([row for row in rows if row["value_krw"] > 0])


def history_frame(
    records: Iterable[PortfolioHistoryRecord],
    *,
    period: HistoryPeriod = "all",
    now: datetime | None = None,
) -> pd.DataFrame:
    start = period_start(period, now=now or datetime.now(timezone.utc))
    rows = []
    for record in records:
        captured_at = datetime.fromisoformat(record.captured_at.replace("Z", "+00:00"))
        if start is not None and captured_at < start:
            continue
        rows.append(
            {
                "captured_at": captured_at,
                "event_type": record.event_type,
                "total_value_krw": record.total_value_krw,
                "total_position_value_krw": record.total_position_value_krw,
                "cash_total_krw": record.cash_total_krw,
                "day_change_krw": record.day_change_krw,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("captured_at")


def demo_history_records(metrics: PortfolioMetrics, portfolio_name: str = "sample") -> list[dict[str, Any]]:
    current = datetime.now(timezone.utc)
    return [
        {
            "captured_at": current - timedelta(days=offset),
            "portfolio_name": portfolio_name,
            "total_value_krw": metrics.total_value_krw * (1 - offset * 0.002),
        }
        for offset in reversed(range(5))
    ]
