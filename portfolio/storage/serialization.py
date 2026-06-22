from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from portfolio.manual_input import normalize_portfolio_rows

SCHEMA_VERSION = 1


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


def serialize_portfolio_payload(
    rows: Iterable[Mapping[str, Any]],
    usd_krw: object,
    cash_krw: object,
) -> dict[str, object]:
    try:
        normalized_rows = normalize_portfolio_rows(rows)
    except ValueError as exc:
        raise PortfolioPayloadError(str(exc)) from exc

    return {
        "schema_version": SCHEMA_VERSION,
        "rows": normalized_rows,
        "usd_krw": _positive_float("usd_krw", usd_krw),
        "cash_krw": _non_negative_float("cash_krw", cash_krw),
    }


def deserialize_portfolio_payload(payload_json: Mapping[str, Any]) -> tuple[list[dict[str, object]], float, float]:
    if not isinstance(payload_json, Mapping):
        raise PortfolioPayloadError("payload_json must be an object")

    schema_version = payload_json.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise PortfolioPayloadError(f"Unsupported payload schema_version: {schema_version}")

    rows_value = payload_json.get("rows")
    if not isinstance(rows_value, list):
        raise PortfolioPayloadError("payload rows must be a list")

    try:
        rows = normalize_portfolio_rows(rows_value)
    except ValueError as exc:
        raise PortfolioPayloadError(str(exc)) from exc

    usd_krw = _positive_float("usd_krw", payload_json.get("usd_krw"))
    cash_krw = _non_negative_float("cash_krw", payload_json.get("cash_krw"))
    return rows, usd_krw, cash_krw
