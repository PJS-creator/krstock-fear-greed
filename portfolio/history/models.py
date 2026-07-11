from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from portfolio.holdings import PortfolioMetrics


@dataclass(frozen=True)
class PortfolioHistoryRecord:
    owner_id: str
    portfolio_name: str
    captured_at: str
    event_type: str
    total_value_krw: float
    total_position_value_krw: float
    cash_krw: float
    cash_usd: float
    cash_total_krw: float
    usd_krw: float
    day_change_krw: float | None
    day_change_pct: float | None
    holdings_count: int
    stale_quote_count: int
    payload_json: dict[str, Any]
    fingerprint: str
    id: int | None = None


VALID_EVENT_TYPES = {"price_refresh", "portfolio_save", "manual_capture", "holdings_changed"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def build_history_fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def history_payload_from_metrics(metrics: PortfolioMetrics) -> dict[str, object]:
    return {
        "schema_version": 1,
        "holdings": [row.holding for row in metrics.rows],
        "cash_balances": metrics.cash.as_payload,
        "usd_krw": metrics.usd_krw,
        "totals": {
            "total_value_krw": metrics.total_value_krw,
            "total_position_value_krw": metrics.total_position_value_krw,
            "cash_total_krw": metrics.cash_total_krw,
            "day_change_krw": metrics.day_change_krw,
            "day_change_pct": metrics.day_change_pct,
            "usd_exposure_krw": metrics.usd_exposure_krw,
            "usd_exposure_pct": metrics.usd_exposure_pct,
        },
        "quote_counts": {
            "priced": metrics.priced_count,
            "stale": metrics.stale_quote_count,
            "failed": metrics.failed_quote_count,
            "missing": metrics.missing_quote_count,
        },
    }


def build_history_record(
    *,
    owner_id: str,
    portfolio_name: str,
    event_type: str,
    metrics: PortfolioMetrics,
    captured_at: str | None = None,
    portfolio_payload: Mapping[str, Any] | None = None,
) -> PortfolioHistoryRecord:
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {event_type}")
    payload = history_payload_from_metrics(metrics)
    fingerprint_payload = {
        "portfolio_name": portfolio_name,
        "total_value_krw": metrics.total_value_krw,
        "total_position_value_krw": metrics.total_position_value_krw,
        "cash_balances": metrics.cash.as_payload,
        "usd_krw": metrics.usd_krw,
        "holdings": payload["holdings"],
    }
    if portfolio_payload is not None:
        payload["schema_version"] = 2
        payload["portfolio_backup"] = deepcopy(dict(portfolio_payload))
        fingerprint_payload["portfolio_backup"] = payload["portfolio_backup"]
    fingerprint = build_history_fingerprint(fingerprint_payload)
    return PortfolioHistoryRecord(
        owner_id=owner_id,
        portfolio_name=portfolio_name,
        captured_at=captured_at or utc_now_iso(),
        event_type=event_type,
        total_value_krw=metrics.total_value_krw,
        total_position_value_krw=metrics.total_position_value_krw,
        cash_krw=metrics.cash.cash_krw,
        cash_usd=metrics.cash.cash_usd,
        cash_total_krw=metrics.cash_total_krw,
        usd_krw=metrics.usd_krw,
        day_change_krw=metrics.day_change_krw,
        day_change_pct=metrics.day_change_pct,
        holdings_count=metrics.holdings_count,
        stale_quote_count=metrics.stale_quote_count,
        payload_json=payload,
        fingerprint=fingerprint,
    )
