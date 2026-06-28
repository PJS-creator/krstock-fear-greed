from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .analytics import SUPPORTED_CURRENCIES
from .models import Position, Quote

QUOTE_STATUS_UPDATED = "updated"
QUOTE_STATUS_CACHED = "cached"
QUOTE_STATUS_STALE = "stale"
QUOTE_STATUS_FAILED = "failed"
QUOTE_STATUS_MISSING = "missing"
QUOTE_STATUS_MISSING_API_KEY = "missing_api_key"
QUOTE_STATUS_MANUAL = "manual"
QUOTE_STATUSES = {
    QUOTE_STATUS_UPDATED,
    QUOTE_STATUS_CACHED,
    QUOTE_STATUS_STALE,
    QUOTE_STATUS_FAILED,
    QUOTE_STATUS_MISSING,
    QUOTE_STATUS_MISSING_API_KEY,
    QUOTE_STATUS_MANUAL,
}

QUICK_INPUT_COLUMNS = ["market", "ticker", "quantity"]
HOLDING_COLUMNS = [
    "ticker",
    "quantity",
    "market",
    "currency",
    "display_name",
    "account_name",
    "target_weight",
    "avg_price",
    "strategy_tag",
    "note",
    "current_price",
    "previous_close",
    "quote_status",
    "fetched_at",
    "provider",
]


@dataclass(frozen=True)
class CashBalances:
    cash_krw: float = 0.0
    cash_usd: float = 0.0

    @property
    def as_payload(self) -> dict[str, float]:
        return {"KRW": self.cash_krw, "USD": self.cash_usd}


@dataclass(frozen=True)
class HoldingMetric:
    holding: dict[str, object]
    market_value_krw: float | None
    day_change_krw: float | None
    day_change_pct: float | None
    weight: float
    cost_basis_krw: float | None
    total_pnl_krw: float | None
    total_pnl_pct: float | None
    usd_exposure_krw: float


@dataclass(frozen=True)
class PortfolioMetrics:
    rows: list[HoldingMetric]
    cash: CashBalances
    usd_krw: float
    cash_total_krw: float
    total_position_value_krw: float
    total_value_krw: float
    day_change_krw: float | None
    day_change_pct: float | None
    usd_exposure_krw: float
    usd_exposure_pct: float
    holdings_count: int
    priced_count: int
    stale_quote_count: int
    failed_quote_count: int
    missing_quote_count: int
    cost_basis_coverage: float
    total_cost_krw: float
    total_pnl_krw: float | None
    total_pnl_pct: float | None
    last_price_refresh_at: str | None


def clean_text(value: object | None) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def normalize_ticker(value: object) -> str:
    ticker = clean_text(value).upper()
    if not ticker:
        raise ValueError("ticker is required")
    if any(char.isspace() for char in ticker):
        raise ValueError("ticker must not contain spaces")
    return ticker


def normalize_korea_ticker(value: object) -> str:
    ticker = normalize_ticker(value)
    if ticker.startswith("KR:"):
        ticker = ticker[3:]
    for suffix in (".KS", ".KQ"):
        if ticker.endswith(suffix):
            ticker = ticker[: -len(suffix)]
            break
    if re.fullmatch(r"\d{6}", ticker) is None:
        raise ValueError("KR ticker must be a 6-digit stock code")
    return ticker


def _normalize_ticker_for_market(value: object, market: str) -> str:
    if market == "KR":
        return normalize_korea_ticker(value)
    return normalize_ticker(value)


def parse_non_negative_float(field_name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def parse_optional_non_negative_float(field_name: str, value: object) -> float | None:
    if value is None or clean_text(value) == "":
        return None
    return parse_non_negative_float(field_name, value)


def _normalize_market(value: object | None) -> str:
    market = clean_text(value).upper() or "US"
    if market == "USA":
        return "US"
    if market in {"KRX", "KOSPI", "KOSDAQ"}:
        return "KR"
    if market not in {"KR", "US"}:
        raise ValueError(f"Unsupported market: {market}")
    return market


def _normalize_currency(value: object | None, market: str) -> str:
    default_currency = "KRW" if market == "KR" else "USD"
    currency = clean_text(value).upper() or default_currency
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    return currency


def _normalize_quote_status(value: object | None, current_price: float | None) -> str:
    status = clean_text(value).lower()
    if status in QUOTE_STATUSES:
        return status
    return QUOTE_STATUS_MANUAL if current_price is not None else QUOTE_STATUS_MISSING


def normalize_holding_row(row: Mapping[str, Any]) -> dict[str, object]:
    market = _normalize_market(row.get("market"))
    ticker = _normalize_ticker_for_market(row.get("ticker") or row.get("symbol"), market)
    currency = _normalize_currency(row.get("currency"), market)
    quantity = parse_non_negative_float("quantity", row.get("quantity"))
    display_name = clean_text(row.get("display_name") or row.get("name")) or ticker
    current_price = parse_optional_non_negative_float("current_price", row.get("current_price"))
    previous_close = parse_optional_non_negative_float("previous_close", row.get("previous_close"))
    avg_price = parse_optional_non_negative_float("avg_price", row.get("avg_price"))
    target_weight = parse_optional_non_negative_float("target_weight", row.get("target_weight")) or 0.0
    quote_status = _normalize_quote_status(row.get("quote_status"), current_price)

    return {
        "ticker": ticker,
        "symbol": ticker,
        "market": market,
        "currency": currency,
        "display_name": display_name,
        "name": display_name,
        "quantity": quantity,
        "avg_price": avg_price,
        "current_price": current_price,
        "previous_close": previous_close,
        "target_weight": target_weight,
        "strategy_tag": clean_text(row.get("strategy_tag")) or "Manual",
        "account_name": clean_text(row.get("account_name")) or "Manual",
        "note": clean_text(row.get("note")),
        "quote_status": quote_status,
        "fetched_at": clean_text(row.get("fetched_at")) or None,
        "provider": clean_text(row.get("provider")) or ("manual" if current_price is not None else None),
    }


def normalize_holding_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized_rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, start=1):
        try:
            normalized = normalize_holding_row(row)
        except ValueError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc
        key = (str(normalized["market"]), str(normalized["ticker"]))
        if key in seen:
            raise ValueError(f"Row {index}: duplicate ticker: {key[0]}/{key[1]}")
        seen.add(key)
        normalized_rows.append(normalized)
    return normalized_rows


def merge_quick_rows_with_existing(
    quick_rows: Iterable[Mapping[str, Any]],
    existing_rows: Iterable[Mapping[str, Any]],
    *,
    duplicate_policy: str = "replace",
) -> list[dict[str, object]]:
    if duplicate_policy not in {"replace", "add"}:
        raise ValueError("duplicate_policy must be replace or add")
    existing_normalized = normalize_holding_rows(existing_rows)
    existing_by_key = {(str(row["market"]), str(row["ticker"])): row for row in existing_normalized}
    incoming_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for index, row in enumerate(quick_rows, start=1):
        market = _normalize_market(row.get("market"))
        ticker = _normalize_ticker_for_market(row.get("ticker") or row.get("symbol"), market)
        key = (market, ticker)
        if key in incoming_by_key and duplicate_policy == "replace":
            raise ValueError(f"Row {index}: duplicate ticker: {market}/{ticker}")
        base = dict(existing_by_key.get(key, {}))
        base.update({"market": market, "ticker": ticker, "quantity": row.get("quantity")})
        if duplicate_policy == "add" and key in existing_by_key:
            base["quantity"] = float(existing_by_key[key].get("quantity") or 0) + parse_non_negative_float("quantity", row.get("quantity"))
        if duplicate_policy == "add" and key in incoming_by_key:
            base = dict(incoming_by_key[key])
            base["quantity"] = float(base.get("quantity") or 0) + parse_non_negative_float("quantity", row.get("quantity"))
        if row.get("currency"):
            base["currency"] = row.get("currency")
        if row.get("display_name"):
            base["display_name"] = row.get("display_name")
            base["name"] = row.get("display_name")
        incoming_by_key[key] = normalize_holding_row(base)

    output: list[dict[str, object]] = []
    for row in existing_normalized:
        key = (str(row["market"]), str(row["ticker"]))
        output.append(incoming_by_key.pop(key, row))
    output.extend(incoming_by_key.values())
    return output


def holding_to_position(row: Mapping[str, Any]) -> Position:
    normalized = normalize_holding_row(row)
    return Position(
        market=normalized["market"],
        symbol=normalized["ticker"],
        name=normalized["display_name"],
        quantity=normalized["quantity"],
        avg_price=normalized["avg_price"],
        currency=normalized["currency"],
        target_weight=normalized["target_weight"],
        strategy_tag=normalized["strategy_tag"],
        account_name=normalized["account_name"],
        note=normalized["note"],
    )


def holding_to_quote(row: Mapping[str, Any]) -> Quote | None:
    normalized = normalize_holding_row(row)
    current_price = normalized["current_price"]
    previous_close = normalized["previous_close"]
    if current_price is None or previous_close is None:
        return None
    fetched_at = normalized.get("fetched_at")
    parsed_fetched_at = None
    if isinstance(fetched_at, str) and fetched_at:
        try:
            parsed_fetched_at = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        except ValueError:
            parsed_fetched_at = None
    return Quote(
        market=normalized["market"],
        symbol=normalized["ticker"],
        price=current_price,
        previous_close=previous_close,
        currency=normalized["currency"],
        provider=str(normalized.get("provider") or "manual"),
        fetched_at=parsed_fetched_at or datetime.now().astimezone(),
    )


def _currency_to_krw_rate(currency: str, usd_krw: float) -> float:
    return 1.0 if currency == "KRW" else usd_krw


def build_portfolio_metrics(
    holdings: Iterable[Mapping[str, Any]],
    *,
    cash_krw: float = 0.0,
    cash_usd: float = 0.0,
    usd_krw: float,
) -> PortfolioMetrics:
    if usd_krw <= 0:
        raise ValueError("usd_krw must be positive")
    cash = CashBalances(
        cash_krw=parse_non_negative_float("cash_krw", cash_krw),
        cash_usd=parse_non_negative_float("cash_usd", cash_usd),
    )
    rows = normalize_holding_rows(holdings)
    partial: list[tuple[dict[str, object], float | None, float | None, float | None, float | None, float | None, float | None, float]] = []
    total_position_value_krw = 0.0
    day_change_krw_values: list[float] = []
    usd_exposure_krw = cash.cash_usd * usd_krw
    latest_fetched_at: str | None = None

    for row in rows:
        fx_rate = _currency_to_krw_rate(str(row["currency"]), usd_krw)
        quantity = float(row["quantity"])
        current_price = row.get("current_price")
        previous_close = row.get("previous_close")
        avg_price = row.get("avg_price")
        market_value_krw = None
        day_change_krw = None
        day_change_pct = None
        cost_basis_krw = None
        total_pnl_krw = None
        total_pnl_pct = None
        if current_price is not None:
            market_value_krw = float(current_price) * quantity * fx_rate
            total_position_value_krw += market_value_krw
            if row["currency"] == "USD":
                usd_exposure_krw += market_value_krw
        if current_price is not None and previous_close is not None:
            day_change_krw = (float(current_price) - float(previous_close)) * quantity * fx_rate
            previous_value = float(previous_close) * quantity * fx_rate
            day_change_pct = day_change_krw / previous_value if previous_value else None
            day_change_krw_values.append(day_change_krw)
        if current_price is not None and avg_price is not None:
            cost_basis_krw = float(avg_price) * quantity * fx_rate
            total_pnl_krw = market_value_krw - cost_basis_krw if market_value_krw is not None else None
            total_pnl_pct = total_pnl_krw / cost_basis_krw if cost_basis_krw else 0.0
        fetched_at = row.get("fetched_at")
        if isinstance(fetched_at, str) and fetched_at:
            latest_fetched_at = max(latest_fetched_at, fetched_at) if latest_fetched_at else fetched_at
        partial.append((row, market_value_krw, day_change_krw, day_change_pct, cost_basis_krw, total_pnl_krw, total_pnl_pct, usd_exposure_krw))

    cash_total_krw = cash.cash_krw + cash.cash_usd * usd_krw
    total_value_krw = total_position_value_krw + cash_total_krw
    metric_rows = [
        HoldingMetric(
            holding=row,
            market_value_krw=market_value_krw,
            day_change_krw=day_change_krw,
            day_change_pct=day_change_pct,
            weight=(market_value_krw / total_value_krw if market_value_krw is not None and total_value_krw else 0.0),
            cost_basis_krw=cost_basis_krw,
            total_pnl_krw=total_pnl_krw,
            total_pnl_pct=total_pnl_pct,
            usd_exposure_krw=(market_value_krw or 0.0) if row["currency"] == "USD" else 0.0,
        )
        for row, market_value_krw, day_change_krw, day_change_pct, cost_basis_krw, total_pnl_krw, total_pnl_pct, _ in partial
    ]
    cost_basis_value = sum(row.market_value_krw or 0.0 for row in metric_rows if row.cost_basis_krw is not None)
    total_cost_krw = sum(row.cost_basis_krw or 0.0 for row in metric_rows if row.cost_basis_krw is not None)
    known_pnl_rows = [row for row in metric_rows if row.total_pnl_krw is not None]
    total_pnl_krw = sum(row.total_pnl_krw or 0.0 for row in known_pnl_rows) if known_pnl_rows else None
    total_pnl_pct = (total_pnl_krw or 0.0) / total_cost_krw if known_pnl_rows and total_cost_krw else (0.0 if known_pnl_rows else None)
    day_change_krw = sum(day_change_krw_values) if day_change_krw_values else None
    previous_total = total_value_krw - (day_change_krw or 0.0)
    day_change_pct = day_change_krw / previous_total if day_change_krw is not None and previous_total else None
    statuses = [str(row.get("quote_status")) for row in rows]

    return PortfolioMetrics(
        rows=metric_rows,
        cash=cash,
        usd_krw=usd_krw,
        cash_total_krw=cash_total_krw,
        total_position_value_krw=total_position_value_krw,
        total_value_krw=total_value_krw,
        day_change_krw=day_change_krw,
        day_change_pct=day_change_pct,
        usd_exposure_krw=usd_exposure_krw,
        usd_exposure_pct=usd_exposure_krw / total_value_krw if total_value_krw else 0.0,
        holdings_count=len(rows),
        priced_count=sum(1 for row in rows if row.get("current_price") is not None),
        stale_quote_count=statuses.count(QUOTE_STATUS_STALE),
        failed_quote_count=statuses.count(QUOTE_STATUS_FAILED),
        missing_quote_count=statuses.count(QUOTE_STATUS_MISSING) + statuses.count(QUOTE_STATUS_MISSING_API_KEY),
        cost_basis_coverage=cost_basis_value / total_position_value_krw if total_position_value_krw else 0.0,
        total_cost_krw=total_cost_krw,
        total_pnl_krw=total_pnl_krw,
        total_pnl_pct=total_pnl_pct,
        last_price_refresh_at=latest_fetched_at,
    )
