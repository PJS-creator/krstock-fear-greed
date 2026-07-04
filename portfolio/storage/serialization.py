from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from portfolio.cash_ledger import serialize_cash_ledger_rows
from portfolio.holdings import normalize_holding_rows, parse_non_negative_float
from portfolio.manual_input import normalize_portfolio_rows
from portfolio.transactions import normalize_transaction_rows

SCHEMA_VERSION_V1 = 1
SCHEMA_VERSION_V2 = 2
SCHEMA_VERSION = 3


class PortfolioPayloadError(ValueError):
    pass


def _finite_float(field_name: str, value: object) -> float:
    if isinstance(value, bool):
        raise PortfolioPayloadError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PortfolioPayloadError(f"{field_name} must be a number") from exc
    if not math.isfinite(number):
        raise PortfolioPayloadError(f"{field_name} must be a finite number")
    return number


def _positive_float(field_name: str, value: object) -> float:
    number = _finite_float(field_name, value)
    if number <= 0:
        raise PortfolioPayloadError(f"{field_name} must be positive")
    return number


def _non_negative_float(field_name: str, value: object) -> float:
    number = _finite_float(field_name, value)
    if number < 0:
        raise PortfolioPayloadError(f"{field_name} must be non-negative")
    return number


def _last_known_quotes(holdings: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, object]]:
    quotes: dict[str, dict[str, object]] = {}
    for row in holdings:
        ticker = str(row["ticker"])
        if row.get("current_price") is None:
            continue
        quotes[ticker] = {
            "current_price": row.get("current_price"),
            "previous_close": row.get("previous_close"),
            "currency": row.get("currency"),
            "provider": row.get("provider"),
            "fetched_at": row.get("fetched_at"),
            "price_date": row.get("price_date"),
            "as_of_timestamp": row.get("as_of_timestamp"),
            "source": row.get("source") or row.get("provider"),
            "status": row.get("quote_status"),
            "error_message": row.get("error_message"),
        }
    return quotes


def _quote_status(holdings: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    return {str(row["ticker"]): str(row.get("quote_status") or "missing") for row in holdings}


def serialize_portfolio_payload(
    rows: Iterable[Mapping[str, Any]],
    usd_krw: object,
    cash_krw: object,
    cash_usd: object = 0.0,
    transactions: Iterable[Mapping[str, Any]] | None = None,
    cash_ledger: Iterable[Mapping[str, Any]] | None = None,
    fx_metadata: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    try:
        holdings = normalize_holding_rows(rows)
    except ValueError:
        try:
            holdings = normalize_holding_rows(normalize_portfolio_rows(rows))
        except ValueError as exc:
            raise PortfolioPayloadError(str(exc)) from exc

    clean_usd_krw = _positive_float("usd_krw", usd_krw)
    clean_cash_krw = _non_negative_float("cash_krw", cash_krw)
    clean_cash_usd = _non_negative_float("cash_usd", cash_usd)
    try:
        clean_transactions = normalize_transaction_rows(transactions or [])
    except ValueError as exc:
        raise PortfolioPayloadError(str(exc)) from exc
    try:
        clean_cash_ledger = serialize_cash_ledger_rows(cash_ledger or [])
    except ValueError as exc:
        raise PortfolioPayloadError(str(exc)) from exc
    return {
        "schema_version": SCHEMA_VERSION,
        "holdings": holdings,
        "transactions": clean_transactions,
        "cash_ledger": clean_cash_ledger,
        "cash_balances": {"KRW": clean_cash_krw, "USD": clean_cash_usd},
        "last_known_quotes": _last_known_quotes(holdings),
        "quote_status": _quote_status(holdings),
        "usd_krw": clean_usd_krw,
        "fx_metadata": dict(fx_metadata or {}),
    }


def migrate_v1_payload_to_v2(payload_json: Mapping[str, Any]) -> dict[str, object]:
    if not isinstance(payload_json, Mapping):
        raise PortfolioPayloadError("payload_json must be an object")
    rows_value = payload_json.get("rows")
    if not isinstance(rows_value, list):
        raise PortfolioPayloadError("payload rows must be a list")
    try:
        legacy_rows = normalize_portfolio_rows(rows_value)
        holdings = normalize_holding_rows(legacy_rows)
    except ValueError as exc:
        raise PortfolioPayloadError(str(exc)) from exc
    return serialize_portfolio_payload(
        holdings,
        usd_krw=_positive_float("usd_krw", payload_json.get("usd_krw")),
        cash_krw=_non_negative_float("cash_krw", payload_json.get("cash_krw", 0.0)),
        cash_usd=0.0,
    )


def deserialize_portfolio_payload_v2(payload_json: Mapping[str, Any]) -> dict[str, object]:
    if not isinstance(payload_json, Mapping):
        raise PortfolioPayloadError("payload_json must be an object")

    schema_version = payload_json.get("schema_version")
    if schema_version == SCHEMA_VERSION_V1:
        return migrate_v1_payload_to_v2(payload_json)
    if schema_version not in {SCHEMA_VERSION_V2, SCHEMA_VERSION}:
        raise PortfolioPayloadError(f"Unsupported payload schema_version: {schema_version}")

    holdings_value = payload_json.get("holdings")
    if not isinstance(holdings_value, list):
        raise PortfolioPayloadError("payload holdings must be a list")
    try:
        holdings = normalize_holding_rows(holdings_value)
    except ValueError as exc:
        raise PortfolioPayloadError(str(exc)) from exc

    cash_balances = payload_json.get("cash_balances") or {}
    if not isinstance(cash_balances, Mapping):
        raise PortfolioPayloadError("cash_balances must be an object")
    clean_payload = serialize_portfolio_payload(
        holdings,
        usd_krw=_positive_float("usd_krw", payload_json.get("usd_krw")),
        cash_krw=parse_non_negative_float("cash_krw", cash_balances.get("KRW", 0.0)),
        cash_usd=parse_non_negative_float("cash_usd", cash_balances.get("USD", 0.0)),
        transactions=payload_json.get("transactions") if schema_version == SCHEMA_VERSION else [],
        cash_ledger=payload_json.get("cash_ledger") if schema_version == SCHEMA_VERSION else [],
        fx_metadata=payload_json.get("fx_metadata") if isinstance(payload_json.get("fx_metadata"), Mapping) else {},
    )
    last_known_quotes = payload_json.get("last_known_quotes")
    quote_status = payload_json.get("quote_status")
    if isinstance(last_known_quotes, Mapping):
        clean_payload["last_known_quotes"] = dict(last_known_quotes)
    if isinstance(quote_status, Mapping):
        clean_payload["quote_status"] = {str(key): str(value) for key, value in quote_status.items()}
    return clean_payload


def deserialize_portfolio_payload(payload_json: Mapping[str, Any]) -> tuple[list[dict[str, object]], float, float]:
    payload = deserialize_portfolio_payload_v2(payload_json)
    cash_balances = payload["cash_balances"]
    if not isinstance(cash_balances, Mapping):
        raise PortfolioPayloadError("cash_balances must be an object")
    return (
        list(payload["holdings"]),
        _positive_float("usd_krw", payload.get("usd_krw")),
        _non_negative_float("cash_krw", cash_balances.get("KRW", 0.0)),
    )
