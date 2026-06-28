from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from .models import CashSnapshotRow, HistoricalHoldingsError, HoldingSnapshotRow


HOLDINGS_COLUMNS = [
    "as_of_date",
    "market",
    "ticker",
    "quantity",
    "display_name",
    "currency",
    "account_name",
    "strategy_tag",
    "note",
]
CASH_COLUMNS = ["as_of_date", "cash_krw", "cash_usd", "usd_krw"]


def clean_text(value: object | None) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def parse_date(value: object, *, field_name: str = "as_of_date") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if not text:
        raise HistoricalHoldingsError(f"{field_name} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise HistoricalHoldingsError(f"{field_name} must be YYYY-MM-DD") from exc


def infer_market_from_ticker(value: object) -> str:
    text = clean_text(value).upper()
    if text.startswith("KR:"):
        text = text[3:]
    for suffix in (".KS", ".KQ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return "KR" if re.fullmatch(r"\d{6}", text) else "US"


def normalize_market(value: object | None, ticker: object) -> str:
    market = clean_text(value).upper() or infer_market_from_ticker(ticker)
    if market in {"KRX", "KOSPI", "KOSDAQ"}:
        market = "KR"
    if market in {"USA", "NASDAQ", "NYSE", "AMEX"}:
        market = "US"
    if market not in {"KR", "US"}:
        raise HistoricalHoldingsError(f"Unsupported market: {market}")
    return market


def normalize_ticker(value: object, market: str) -> str:
    ticker = clean_text(value).upper()
    if not ticker:
        raise HistoricalHoldingsError("ticker is required")
    if market == "KR":
        if ticker.startswith("KR:"):
            ticker = ticker[3:]
        for suffix in (".KS", ".KQ"):
            if ticker.endswith(suffix):
                ticker = ticker[: -len(suffix)]
                break
        if re.fullmatch(r"\d{6}", ticker) is None:
            raise HistoricalHoldingsError("KR ticker must be a 6-digit stock code")
        return ticker
    if any(char.isspace() for char in ticker):
        raise HistoricalHoldingsError("ticker must not contain spaces")
    return ticker


def infer_currency(market: str, value: object | None = None) -> str:
    currency = clean_text(value).upper() or ("KRW" if market == "KR" else "USD")
    if currency not in {"KRW", "USD"}:
        raise HistoricalHoldingsError(f"Unsupported currency: {currency}")
    return currency


def parse_non_negative_float(value: object, *, field_name: str, default: float | None = None) -> float:
    text = clean_text(value)
    if text == "" and default is not None:
        return default
    if isinstance(value, bool):
        raise HistoricalHoldingsError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalHoldingsError(f"{field_name} must be a number") from exc
    if not math.isfinite(number) or number < 0:
        raise HistoricalHoldingsError(f"{field_name} must be non-negative")
    return number


def parse_optional_positive_float(value: object, *, field_name: str) -> float | None:
    if clean_text(value) == "":
        return None
    number = parse_non_negative_float(value, field_name=field_name)
    if number <= 0:
        raise HistoricalHoldingsError(f"{field_name} must be positive")
    return number


def normalize_holding_snapshots(rows: Iterable[Mapping[str, Any]]) -> list[HoldingSnapshotRow]:
    normalized: list[HoldingSnapshotRow] = []
    seen: set[tuple[date, str, str]] = set()
    for index, row in enumerate(rows, start=1):
        if not any(clean_text(row.get(column)) for column in ("as_of_date", "ticker", "quantity")):
            continue
        as_of = parse_date(row.get("as_of_date"))
        market = normalize_market(row.get("market"), row.get("ticker"))
        ticker = normalize_ticker(row.get("ticker"), market)
        key = (as_of, market, ticker)
        if key in seen:
            raise HistoricalHoldingsError(f"{index}행: duplicate as_of_date + market + ticker: {as_of} {market} {ticker}")
        seen.add(key)
        quantity = parse_non_negative_float(row.get("quantity"), field_name="quantity")
        currency = infer_currency(market, row.get("currency"))
        normalized.append(
            HoldingSnapshotRow(
                as_of_date=as_of,
                market=market,
                ticker=ticker,
                quantity=quantity,
                display_name=clean_text(row.get("display_name")) or ticker,
                currency=currency,
                account_name=clean_text(row.get("account_name")),
                strategy_tag=clean_text(row.get("strategy_tag")),
                note=clean_text(row.get("note")),
            )
        )
    normalized.sort(key=lambda item: (item.as_of_date, item.market, item.ticker))
    if not normalized:
        raise HistoricalHoldingsError("at least one holding snapshot row is required")
    return normalized


def normalize_cash_snapshots(rows: Iterable[Mapping[str, Any]]) -> list[CashSnapshotRow]:
    normalized: list[CashSnapshotRow] = []
    seen: set[date] = set()
    for index, row in enumerate(rows, start=1):
        if not any(clean_text(row.get(column)) for column in CASH_COLUMNS):
            continue
        as_of = parse_date(row.get("as_of_date"))
        if as_of in seen:
            raise HistoricalHoldingsError(f"{index}행: duplicate cash as_of_date: {as_of}")
        seen.add(as_of)
        normalized.append(
            CashSnapshotRow(
                as_of_date=as_of,
                cash_krw=parse_non_negative_float(row.get("cash_krw"), field_name="cash_krw", default=0.0),
                cash_usd=parse_non_negative_float(row.get("cash_usd"), field_name="cash_usd", default=0.0),
                usd_krw=parse_optional_positive_float(row.get("usd_krw"), field_name="usd_krw"),
            )
        )
    normalized.sort(key=lambda item: item.as_of_date)
    return normalized


def rows_to_csv(rows: Iterable[Mapping[str, Any]], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()


def csv_to_rows(content: str | bytes) -> list[dict[str, str]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return [dict(row) for row in reader]


def holding_snapshots_to_dicts(rows: Iterable[HoldingSnapshotRow]) -> list[dict[str, object]]:
    return [{**asdict(row), "as_of_date": row.as_of_date.isoformat()} for row in rows]


def cash_snapshots_to_dicts(rows: Iterable[CashSnapshotRow]) -> list[dict[str, object]]:
    return [{**asdict(row), "as_of_date": row.as_of_date.isoformat(), "usd_krw": row.usd_krw or ""} for row in rows]


def holding_template_csv() -> str:
    return rows_to_csv(
        [
            {
                "as_of_date": "2026-06-01",
                "market": "KR",
                "ticker": "005930",
                "quantity": "100",
                "display_name": "가상 삼성전자",
                "currency": "KRW",
            },
            {
                "as_of_date": "2026-06-16",
                "market": "KR",
                "ticker": "000660",
                "quantity": "10",
                "display_name": "가상 SK하이닉스",
                "currency": "KRW",
            },
        ],
        HOLDINGS_COLUMNS,
    )


def cash_template_csv() -> str:
    return rows_to_csv(
        [{"as_of_date": "2026-06-01", "cash_krw": "1000000", "cash_usd": "0", "usd_krw": "1380"}],
        CASH_COLUMNS,
    )

