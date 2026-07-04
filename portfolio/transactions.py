from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

from portfolio.analytics import SUPPORTED_CURRENCIES
from portfolio.holdings import (
    clean_text,
    normalize_holding_rows,
    normalize_korea_ticker,
    normalize_ticker,
    parse_non_negative_float,
)
from portfolio.symbols import InputPreviewResult, resolve_symbol


TRANSACTION_TYPES = {"buy", "sell"}
TRANSACTION_TYPE_LABELS = {"buy": "매입", "sell": "매도"}
TRANSACTION_CSV_COLUMNS = ["transaction_type", "ticker_or_name", "unit_price", "quantity", "occurred_at"]
TRANSACTION_COLUMNS = [
    "transaction_type",
    "ticker",
    "market",
    "currency",
    "display_name",
    "unit_price",
    "quantity",
    "fee",
    "tax",
    "occurred_at",
    "note",
]
MARKET_AUTO_LABELS = {"", "auto", "자동", "자동감지"}
CURRENCY_AUTO_LABELS = {"", "auto", "자동", "시장 기준 자동"}


def normalize_transaction_type(value: object) -> str:
    text = clean_text(value).lower()
    mapping = {
        "buy": "buy",
        "b": "buy",
        "매입": "buy",
        "매수": "buy",
        "구매": "buy",
        "sell": "sell",
        "s": "sell",
        "매도": "sell",
        "판매": "sell",
    }
    if text not in mapping:
        raise ValueError("transaction_type must be buy/sell or 매입/매도")
    return mapping[text]


def parse_positive_float(field_name: str, value: object) -> float:
    number = parse_non_negative_float(field_name, value)
    if number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _optional_non_negative_float(field_name: str, value: object | None) -> float:
    if clean_text(value) == "":
        return 0.0
    return parse_non_negative_float(field_name, value)


def _first_present(*values: object | None) -> object | None:
    for value in values:
        if clean_text(value) != "":
            return value
    return None


def _normalize_currency(value: object | None, market: str) -> str:
    currency = clean_text(value).upper() or ("KRW" if market == "KR" else "USD")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    return currency


def _normalize_currency_hint(value: object | None) -> str:
    text = clean_text(value)
    if text.lower() in CURRENCY_AUTO_LABELS:
        return ""
    currency = text.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")
    return currency


def _normalize_market(value: object | None, ticker: str) -> str:
    market = clean_text(value).upper()
    if market in {"KRX", "KOSPI", "KOSDAQ"}:
        market = "KR"
    if market in {"USA"}:
        market = "US"
    if not market:
        return "KR" if re.fullmatch(r"\d{6}", ticker) else "US"
    if market not in {"KR", "US"}:
        raise ValueError(f"Unsupported market: {market}")
    return market


def _normalize_market_hint(value: object | None) -> str:
    market = clean_text(value)
    if market.lower() in MARKET_AUTO_LABELS:
        return ""
    normalized = market.upper()
    if normalized in {"KRX", "KOSPI", "KOSDAQ"}:
        normalized = "KR"
    if normalized in {"USA"}:
        normalized = "US"
    if normalized not in {"KR", "US"}:
        raise ValueError(f"Unsupported market: {normalized}")
    return normalized


def normalize_occurred_at(value: object) -> str:
    text = clean_text(value)
    if not text:
        raise ValueError("occurred_at is required")
    text = text.replace("/", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return date.fromisoformat(text).isoformat()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise ValueError("occurred_at must be YYYY-MM-DD or ISO datetime") from exc


def _sort_timestamp(value: object) -> str:
    text = normalize_occurred_at(value)
    return f"{text}T00:00:00" if len(text) == 10 else text


def normalize_transaction_row(row: Mapping[str, Any]) -> dict[str, object]:
    ticker_value = row.get("ticker") or row.get("symbol")
    market_value = row.get("market")
    display_name = clean_text(row.get("display_name") or row.get("name"))
    currency = clean_text(row.get("currency")).upper()

    if ticker_value:
        market = _normalize_market(market_value, clean_text(ticker_value))
        ticker = normalize_korea_ticker(ticker_value) if market == "KR" else normalize_ticker(ticker_value)
        display_name = display_name or ticker
    else:
        resolution = resolve_symbol(row.get("ticker_or_name"))
        if not resolution.is_resolved:
            raise ValueError(resolution.message)
        market = str(resolution.market)
        ticker = str(resolution.ticker)
        display_name = display_name or str(resolution.display_name or ticker)

    currency = _normalize_currency(currency, market)
    normalized = {
        "transaction_type": normalize_transaction_type(row.get("transaction_type") or row.get("side")),
        "ticker": ticker,
        "symbol": ticker,
        "market": market,
        "currency": currency,
        "display_name": display_name,
        "name": display_name,
        "unit_price": parse_positive_float("unit_price", _first_present(row.get("unit_price"), row.get("avg_price"), row.get("price"))),
        "quantity": parse_positive_float("quantity", row.get("quantity")),
        "fee": _optional_non_negative_float("fee", _first_present(row.get("fee"), row.get("fee_amount"))),
        "tax": _optional_non_negative_float("tax", _first_present(row.get("tax"), row.get("tax_amount"))),
        "occurred_at": normalize_occurred_at(row.get("occurred_at") or row.get("date") or row.get("timestamp")),
        "note": clean_text(row.get("note")),
    }
    if clean_text(row.get("external_id")):
        normalized["external_id"] = clean_text(row.get("external_id"))
    return normalized


def normalize_trade_input(row: Mapping[str, Any]) -> dict[str, object]:
    """Normalize the standard Streamlit trade form into the internal transaction shape.

    The app keeps the legacy `unit_price` field for storage/calculation compatibility,
    while the UI labels this value as 체결단가.
    """

    ticker_or_name = clean_text(
        row.get("ticker_or_name")
        or row.get("ticker")
        or row.get("symbol")
        or row.get("selected_ticker")
        or row.get("selected_holding")
    )
    if not ticker_or_name:
        raise ValueError("종목명 또는 티커를 입력하세요.")

    market_hint = _normalize_market_hint(row.get("market"))
    currency_hint = _normalize_currency_hint(row.get("currency"))
    transaction: dict[str, object] = {
        "transaction_type": normalize_transaction_type(row.get("transaction_type") or row.get("trade_type") or row.get("side")),
        "ticker_or_name": ticker_or_name,
        "unit_price": parse_positive_float("unit_price", _first_present(row.get("unit_price"), row.get("execution_price"), row.get("price"))),
        "quantity": parse_positive_float("quantity", row.get("quantity")),
        "fee": _optional_non_negative_float("fee", _first_present(row.get("fee"), row.get("fee_amount"))),
        "tax": _optional_non_negative_float("tax", _first_present(row.get("tax"), row.get("tax_amount"))),
        "occurred_at": normalize_occurred_at(row.get("occurred_at") or row.get("trade_date") or row.get("date")),
        "note": clean_text(row.get("note")),
    }
    if market_hint:
        transaction["market"] = market_hint
        if market_hint == "KR" and re.fullmatch(r"(KR:)?\d{6}(\.(KS|KQ))?", ticker_or_name.upper()):
            transaction["ticker"] = ticker_or_name
            transaction.pop("ticker_or_name", None)
        elif market_hint == "US" and re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]*", ticker_or_name):
            transaction["ticker"] = ticker_or_name
            transaction.pop("ticker_or_name", None)
    if currency_hint:
        transaction["currency"] = currency_hint
    elif market_hint:
        transaction["currency"] = "KRW" if market_hint == "KR" else "USD"
    if row.get("display_name"):
        transaction["display_name"] = clean_text(row.get("display_name"))
    return transaction


def validate_trade_input(
    row: Mapping[str, Any],
    *,
    existing_holdings: Iterable[Mapping[str, Any]] = (),
    korea_listing_records: Iterable[Mapping[str, str]] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        transaction = normalize_trade_input(row)
    except ValueError as exc:
        return [str(exc)]

    try:
        normalized = normalize_transaction_row(transaction)
    except ValueError as exc:
        preview = build_transaction_preview([transaction], korea_listing_records=korea_listing_records)
        if not preview.rows:
            return [str(exc)]
        first_row = preview.rows[0]
        if first_row.get("status") == "candidate_required":
            return errors
        if first_row.get("status") == "error":
            return [str(first_row.get("message") or exc)]
        try:
            normalized = preview_rows_to_transactions(preview.rows)[0]
        except (IndexError, ValueError) as preview_exc:
            return [str(preview_exc)]

    if normalized["transaction_type"] != "sell":
        return errors

    market = str(normalized["market"])
    ticker = str(normalized["ticker"])
    available_quantity = 0.0
    for holding in normalize_holding_rows(existing_holdings):
        if str(holding["market"]) == market and str(holding["ticker"]) == ticker:
            available_quantity += float(holding["quantity"])
    requested_quantity = float(normalized["quantity"])
    if requested_quantity - available_quantity > 1e-9:
        errors.append(f"현재 보유 수량 {available_quantity:g}주를 초과해 매도할 수 없습니다.")
    return errors


def normalize_transaction_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not any(clean_text(row.get(field)) for field in ("transaction_type", "side", "ticker_or_name", "ticker", "symbol", "quantity", "unit_price", "avg_price", "occurred_at", "date")):
            continue
        try:
            normalized.append(normalize_transaction_row(row))
        except ValueError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc
    return sorted(normalized, key=lambda row: (_sort_timestamp(row["occurred_at"]), str(row["market"]), str(row["ticker"])))


def parse_transaction_lines(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"[,\t ]+", line) if part.strip()]
        if len(parts) < 5:
            rows.append({"row_number": str(line_number), "error": "매입/매도, 주식명, 체결단가, 수량, 시점을 입력하세요."})
            continue
        if len(parts) >= 6 and re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", parts[-2]) and re.fullmatch(r"\d{2}:\d{2}(:\d{2})?", parts[-1]):
            occurred_at = f"{parts[-2].replace('/', '-')}T{parts[-1]}"
            quantity = parts[-3]
            unit_price = parts[-4]
            ticker_or_name = " ".join(parts[1:-4])
        else:
            occurred_at = parts[-1]
            quantity = parts[-2]
            unit_price = parts[-3]
            ticker_or_name = " ".join(parts[1:-3])
        rows.append(
            {
                "row_number": str(line_number),
                "transaction_type": parts[0],
                "ticker_or_name": ticker_or_name,
                "unit_price": unit_price,
                "quantity": quantity,
                "occurred_at": occurred_at,
            }
        )
    return rows


def csv_to_rows(content: str | bytes) -> list[dict[str, str]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return [dict(row) for row in reader]


def rows_to_csv(rows: Iterable[Mapping[str, Any]], columns: list[str] = TRANSACTION_CSV_COLUMNS) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()


def build_transaction_preview(
    rows: Iterable[Mapping[str, Any]],
    *,
    korea_listing_records: Iterable[Mapping[str, str]] | None = None,
) -> InputPreviewResult:
    preview_rows: list[dict[str, object]] = []
    errors: list[str] = []
    counts: Counter[str] = Counter()
    for index, row in enumerate(rows, start=1):
        row_number = int(str(row.get("row_number") or index))
        if row.get("error"):
            message = str(row["error"])
            errors.append(f"{row_number}행: {message}")
            preview_rows.append({"row_number": row_number, "status": "error", "message": message, "raw_input": ""})
            counts["error"] += 1
            continue
        if not any(clean_text(row.get(field)) for field in ("transaction_type", "side", "ticker_or_name", "ticker", "symbol", "quantity", "unit_price", "avg_price", "occurred_at", "date")):
            continue
        raw_input = row.get("ticker_or_name") or row.get("ticker") or row.get("symbol")
        try:
            transaction_type = normalize_transaction_type(row.get("transaction_type") or row.get("side"))
            unit_price = parse_positive_float("unit_price", _first_present(row.get("unit_price"), row.get("avg_price"), row.get("price")))
            quantity = parse_positive_float("quantity", row.get("quantity"))
            fee = _optional_non_negative_float("fee", _first_present(row.get("fee"), row.get("fee_amount")))
            tax = _optional_non_negative_float("tax", _first_present(row.get("tax"), row.get("tax_amount")))
            occurred_at = normalize_occurred_at(row.get("occurred_at") or row.get("date") or row.get("timestamp"))
            market_hint = _normalize_market_hint(row.get("market"))
            currency_hint = _normalize_currency_hint(row.get("currency"))
        except ValueError as exc:
            errors.append(f"{row_number}행: {exc}")
            preview_rows.append({"row_number": row_number, "status": "error", "message": str(exc), "raw_input": clean_text(raw_input)})
            counts["error"] += 1
            continue

        resolution = resolve_symbol(raw_input, korea_listing_records)
        status = "ok" if resolution.is_resolved else ("candidate_required" if resolution.status == "ambiguous" else "error")
        message = resolution.message
        if market_hint and resolution.market and resolution.market != market_hint:
            status = "error"
            message = f"선택한 시장({market_hint})과 인식된 시장({resolution.market})이 다릅니다."
        if status == "error":
            errors.append(f"{row_number}행: {message}")
        preview_rows.append(
            {
                "row_number": row_number,
                "transaction_type": transaction_type,
                "transaction_label": TRANSACTION_TYPE_LABELS[transaction_type],
                "raw_input": resolution.raw_input,
                "ticker": resolution.ticker,
                "display_name": resolution.display_name,
                "market": resolution.market,
                "currency": currency_hint or resolution.currency,
                "unit_price": unit_price,
                "quantity": quantity,
                "fee": fee,
                "tax": tax,
                "occurred_at": occurred_at,
                "status": status,
                "message": message,
                "note": clean_text(row.get("note")),
                "candidates": [candidate.__dict__ for candidate in resolution.candidates],
            }
        )
        counts[status] += 1
    return InputPreviewResult(
        rows=preview_rows,
        errors=errors,
        summary={
            "total": len(preview_rows),
            "ok": counts["ok"],
            "candidate_required": counts["candidate_required"],
            "error": counts["error"],
        },
    )


def preview_rows_to_transactions(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    transactions: list[dict[str, object]] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        transactions.append(
            normalize_transaction_row(
                {
                    "transaction_type": row.get("transaction_type"),
                    "ticker": row.get("ticker"),
                    "market": row.get("market"),
                    "currency": row.get("currency"),
                    "display_name": row.get("display_name"),
                    "unit_price": row.get("unit_price"),
                    "quantity": row.get("quantity"),
                    "fee": row.get("fee"),
                    "tax": row.get("tax"),
                    "occurred_at": row.get("occurred_at"),
                    "note": row.get("note"),
                }
            )
        )
    return transactions


def transactions_to_holdings(
    transactions: Iterable[Mapping[str, Any]],
    *,
    previous_holdings: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, object]]:
    normalized_transactions = normalize_transaction_rows(transactions)
    previous_by_key = {
        (str(row["market"]), str(row["ticker"])): row
        for row in normalize_holding_rows(previous_holdings)
    }
    state: dict[tuple[str, str], dict[str, object]] = {}
    for transaction in normalized_transactions:
        key = (str(transaction["market"]), str(transaction["ticker"]))
        entry = state.setdefault(
            key,
            {
                "market": transaction["market"],
                "ticker": transaction["ticker"],
                "currency": transaction["currency"],
                "display_name": transaction["display_name"],
                "quantity": 0.0,
                "cost_total": 0.0,
            },
        )
        if entry["currency"] != transaction["currency"]:
            raise ValueError(f"{key[0]}/{key[1]} has mixed currencies")
        quantity = float(transaction["quantity"])
        amount = float(transaction["unit_price"]) * quantity
        current_quantity = float(entry["quantity"])
        current_cost = float(entry["cost_total"])
        if transaction["transaction_type"] == "buy":
            entry["quantity"] = current_quantity + quantity
            entry["cost_total"] = current_cost + amount
            entry["display_name"] = transaction["display_name"]
        else:
            if quantity - current_quantity > 1e-9:
                raise ValueError(f"{key[0]}/{key[1]} sell quantity exceeds current holdings")
            average_cost = current_cost / current_quantity if current_quantity else 0.0
            next_quantity = current_quantity - quantity
            entry["quantity"] = 0.0 if abs(next_quantity) < 1e-9 else next_quantity
            entry["cost_total"] = 0.0 if entry["quantity"] == 0 else max(current_cost - average_cost * quantity, 0.0)

    holdings: list[dict[str, object]] = []
    for key, entry in sorted(state.items()):
        quantity = float(entry["quantity"])
        if quantity <= 0:
            continue
        previous = dict(previous_by_key.get(key, {}))
        avg_price = float(entry["cost_total"]) / quantity if quantity else None
        previous.update(
            {
                "market": entry["market"],
                "ticker": entry["ticker"],
                "symbol": entry["ticker"],
                "currency": entry["currency"],
                "display_name": entry["display_name"],
                "name": entry["display_name"],
                "quantity": quantity,
                "avg_price": avg_price,
            }
        )
        holdings.append(previous)
    return normalize_holding_rows(holdings)


def transaction_cashflow_rows(transactions: Iterable[Mapping[str, Any]], *, usd_krw: float) -> list[dict[str, object]]:
    if usd_krw <= 0:
        raise ValueError("usd_krw must be positive")
    by_date: dict[str, dict[str, object]] = {}
    for transaction in normalize_transaction_rows(transactions):
        day = str(transaction["occurred_at"])[:10]
        row = by_date.setdefault(
            day,
            {
                "date": day,
                "buy_amount_krw": 0.0,
                "sell_amount_krw": 0.0,
                "net_delta_krw": 0.0,
                "buy_count": 0,
                "sell_count": 0,
            },
        )
        fx_rate = 1.0 if transaction["currency"] == "KRW" else usd_krw
        amount_krw = float(transaction["unit_price"]) * float(transaction["quantity"]) * fx_rate
        if not math.isfinite(amount_krw):
            raise ValueError("transaction amount must be finite")
        if transaction["transaction_type"] == "buy":
            row["buy_amount_krw"] = float(row["buy_amount_krw"]) + amount_krw
            row["net_delta_krw"] = float(row["net_delta_krw"]) + amount_krw
            row["buy_count"] = int(row["buy_count"]) + 1
        else:
            row["sell_amount_krw"] = float(row["sell_amount_krw"]) + amount_krw
            row["net_delta_krw"] = float(row["net_delta_krw"]) - amount_krw
            row["sell_count"] = int(row["sell_count"]) + 1
    rows = [by_date[key] for key in sorted(by_date)]
    cumulative = 0.0
    for row in rows:
        cumulative += float(row["net_delta_krw"])
        row["cumulative_net_invested_krw"] = cumulative
    return rows
