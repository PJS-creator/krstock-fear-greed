from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping
from io import StringIO
from typing import Any

from .analytics import SUPPORTED_CURRENCIES
from .models import Position, Quote

PORTFOLIO_CSV_COLUMNS = [
    "market",
    "symbol",
    "name",
    "currency",
    "quantity",
    "avg_price",
    "current_price",
    "previous_close",
    "target_weight",
    "strategy_tag",
]

DEFAULT_STRATEGY_TAG = "Manual"


def _cell(row: Mapping[str, Any], column: str) -> str:
    if column not in row:
        raise ValueError(f"Missing CSV column: {column}")
    value = row[column]
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _required_text(row: Mapping[str, Any], column: str) -> str:
    value = _cell(row, column)
    if not value:
        raise ValueError(f"{column} is required")
    return value


def _currency(row: Mapping[str, Any]) -> str:
    currency = _required_text(row, "currency").upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    return currency


def _non_negative_float(row: Mapping[str, Any], column: str) -> float:
    raw_value = _cell(row, column)
    if raw_value == "":
        raise ValueError(f"{column} is required")
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{column} must be a number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{column} must be a finite number")
    if value < 0:
        raise ValueError(f"{column} must be non-negative")
    return value


def row_to_position_quote(row: Mapping[str, Any]) -> tuple[Position, Quote]:
    market = _required_text(row, "market").upper()
    symbol = _required_text(row, "symbol").upper()
    name = _required_text(row, "name")
    currency = _currency(row)
    quantity = _non_negative_float(row, "quantity")
    avg_price = _non_negative_float(row, "avg_price")
    current_price = _non_negative_float(row, "current_price")
    previous_close = _non_negative_float(row, "previous_close")
    target_weight = _non_negative_float(row, "target_weight")
    strategy_tag = _cell(row, "strategy_tag") or DEFAULT_STRATEGY_TAG

    position = Position(
        market=market,
        symbol=symbol,
        name=name,
        quantity=quantity,
        avg_price=avg_price,
        currency=currency,
        target_weight=target_weight,
        strategy_tag=strategy_tag,
    )
    quote = Quote(
        market=market,
        symbol=symbol,
        price=current_price,
        previous_close=previous_close,
        currency=currency,
        provider="manual",
    )
    return position, quote


def normalize_portfolio_row(row: Mapping[str, Any]) -> dict[str, object]:
    position, quote = row_to_position_quote(row)
    return {
        "market": position.market,
        "symbol": position.symbol,
        "name": position.name,
        "currency": position.currency,
        "quantity": position.quantity,
        "avg_price": position.avg_price,
        "current_price": quote.price,
        "previous_close": quote.previous_close,
        "target_weight": position.target_weight,
        "strategy_tag": position.strategy_tag,
    }


def normalize_portfolio_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized_rows = []
    for index, row in enumerate(rows, start=1):
        try:
            normalized_rows.append(normalize_portfolio_row(row))
        except ValueError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc
    rows_to_positions_quotes(normalized_rows)
    return normalized_rows


def rows_to_positions_quotes(rows: Iterable[Mapping[str, Any]]) -> tuple[list[Position], dict[tuple[str, str], Quote]]:
    positions: list[Position] = []
    quotes: dict[tuple[str, str], Quote] = {}
    for index, row in enumerate(rows, start=1):
        try:
            position, quote = row_to_position_quote(row)
        except ValueError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc
        key = (position.market, position.symbol)
        if key in quotes:
            raise ValueError(f"Row {index}: duplicate market/symbol: {position.market}/{position.symbol}")
        positions.append(position)
        quotes[key] = quote
    return positions, quotes


def positions_quotes_to_rows(positions: Iterable[Position], quotes: Mapping[tuple[str, str], Quote]) -> list[dict[str, object]]:
    rows = []
    for position in positions:
        quote = quotes[(position.market, position.symbol)]
        rows.append(
            {
                "market": position.market,
                "symbol": position.symbol,
                "name": position.name,
                "currency": position.currency,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
                "current_price": quote.price,
                "previous_close": quote.previous_close,
                "target_weight": position.target_weight,
                "strategy_tag": position.strategy_tag,
            }
        )
    return rows


def rows_to_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=PORTFOLIO_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in normalize_portfolio_rows(rows):
        writer.writerow({column: row[column] for column in PORTFOLIO_CSV_COLUMNS})
    return output.getvalue()


def csv_template() -> str:
    return rows_to_csv([])
