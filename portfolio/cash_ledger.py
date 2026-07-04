from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from portfolio.transactions import normalize_transaction_row

CASH_CURRENCIES = {"KRW", "USD"}
CASH_LEDGER_EVENT_TYPES = {
    "opening_balance",
    "deposit",
    "withdrawal",
    "buy_settlement",
    "sell_settlement",
    "dividend",
    "interest",
    "fee",
    "tax",
    "fx_conversion_in",
    "fx_conversion_out",
    "manual_adjustment",
}
CASH_INCREASE_EVENT_TYPES = {"deposit", "sell_settlement", "dividend", "interest", "fx_conversion_in"}
CASH_DECREASE_EVENT_TYPES = {"withdrawal", "buy_settlement", "fee", "tax", "fx_conversion_out"}
TRADE_SETTLEMENT_EVENT_TYPES = {"buy_settlement", "sell_settlement"}
ZERO = Decimal("0")


def _clean_text(value: object | None) -> str:
    return str(value or "").strip()


def _to_decimal(field_name: str, value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not number.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return number


def _decimal_to_storage(value: Decimal) -> str:
    if value == value.to_integral_value():
        return format(value.quantize(Decimal("1")), "f")
    return format(value.normalize(), "f")


def _normalize_event_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _clean_text(value).replace("/", "-")
    if not text:
        raise ValueError("event_date is required")
    try:
        if len(text) >= 10:
            return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValueError("event_date must be YYYY-MM-DD or ISO datetime") from exc
    raise ValueError("event_date must be YYYY-MM-DD or ISO datetime")


def _optional_decimal(field_name: str, value: object | None) -> Decimal | None:
    if _clean_text(value) == "":
        return None
    number = _to_decimal(field_name, value)
    if number <= ZERO:
        raise ValueError(f"{field_name} must be positive")
    return number


def _validate_amount_sign(event_type: str, amount: Decimal) -> None:
    if event_type in CASH_INCREASE_EVENT_TYPES and amount <= ZERO:
        raise ValueError(f"{event_type} amount must be positive")
    if event_type in CASH_DECREASE_EVENT_TYPES and amount >= ZERO:
        raise ValueError(f"{event_type} amount must be negative")
    if event_type in {"opening_balance", "manual_adjustment"}:
        return
    if amount == ZERO:
        raise ValueError("amount must not be zero")


def validate_cash_ledger_entry(entry: Mapping[str, Any]) -> dict[str, object]:
    """Validate and normalize one cash ledger row.

    The returned `amount` and `fx_rate_to_krw` values are Decimals so accounting
    calculations can stay exact until UI formatting or JSON serialization.
    """

    event_type = _clean_text(entry.get("event_type"))
    if event_type not in CASH_LEDGER_EVENT_TYPES:
        raise ValueError(f"Unsupported cash ledger event_type: {event_type}")

    currency = _clean_text(entry.get("currency")).upper()
    if currency not in CASH_CURRENCIES:
        raise ValueError(f"Unsupported cash ledger currency: {currency}")

    amount = _to_decimal("amount", entry.get("amount"))
    _validate_amount_sign(event_type, amount)

    normalized: dict[str, object] = {
        "event_date": _normalize_event_date(entry.get("event_date")),
        "currency": currency,
        "event_type": event_type,
        "amount": amount,
    }
    for key in ("id", "user_id", "portfolio_id", "linked_transaction_id", "memo", "created_at", "updated_at"):
        if key in entry and entry.get(key) is not None:
            normalized[key] = entry.get(key)
    fx_rate = _optional_decimal("fx_rate_to_krw", entry.get("fx_rate_to_krw"))
    if fx_rate is not None:
        normalized["fx_rate_to_krw"] = fx_rate
    return normalized


def normalize_cash_ledger_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not any(_clean_text(row.get(field)) for field in ("event_date", "currency", "event_type", "amount")):
            continue
        try:
            normalized.append(validate_cash_ledger_entry(row))
        except ValueError as exc:
            raise ValueError(f"Cash ledger row {index}: {exc}") from exc
    return sorted(normalized, key=lambda row: (str(row["event_date"]), str(row["currency"]), str(row["event_type"])))


def serialize_cash_ledger_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for row in normalize_cash_ledger_rows(rows):
        next_row = dict(row)
        next_row["amount"] = _decimal_to_storage(Decimal(next_row["amount"]))
        if next_row.get("fx_rate_to_krw") is not None:
            next_row["fx_rate_to_krw"] = _decimal_to_storage(Decimal(next_row["fx_rate_to_krw"]))
        serialized.append(next_row)
    return serialized


def calculate_cash_balances(cash_ledger_rows: Iterable[Mapping[str, Any]]) -> dict[str, Decimal]:
    balances = {"KRW": ZERO, "USD": ZERO}
    for row in normalize_cash_ledger_rows(cash_ledger_rows):
        balances[str(row["currency"])] += Decimal(row["amount"])
    return balances


def _trade_decimal(transaction: Mapping[str, Any], field_name: str) -> Decimal:
    number = _to_decimal(field_name, transaction.get(field_name, 0))
    if number < ZERO:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def create_cash_ledger_entries_for_trade(
    trade: Mapping[str, Any],
    *,
    user_id: str | None = None,
    portfolio_id: str | None = None,
) -> list[dict[str, object]]:
    transaction = normalize_transaction_row(trade)
    quantity = _trade_decimal(transaction, "quantity")
    unit_price = _trade_decimal(transaction, "unit_price")
    fee = _trade_decimal(transaction, "fee")
    tax = _trade_decimal(transaction, "tax")
    gross = unit_price * quantity
    transaction_type = str(transaction["transaction_type"])
    if transaction_type == "buy":
        event_type = "buy_settlement"
        amount = -(gross + fee + tax)
    elif transaction_type == "sell":
        event_type = "sell_settlement"
        amount = gross - fee - tax
    else:
        raise ValueError(f"Unsupported transaction_type: {transaction_type}")

    entry: dict[str, object] = {
        "event_date": str(transaction["occurred_at"])[:10],
        "currency": transaction["currency"],
        "event_type": event_type,
        "amount": amount,
        "memo": transaction.get("note") or f"{transaction['display_name']} {transaction_type}",
    }
    linked_transaction_id = trade.get("id") or trade.get("transaction_id") or trade.get("linked_transaction_id")
    if linked_transaction_id:
        entry["linked_transaction_id"] = linked_transaction_id
    if user_id:
        entry["user_id"] = user_id
    if portfolio_id:
        entry["portfolio_id"] = portfolio_id
    if trade.get("fx_rate_to_krw") not in (None, ""):
        entry["fx_rate_to_krw"] = trade.get("fx_rate_to_krw")
    return [validate_cash_ledger_entry(entry)]


def create_cash_movement_entry(
    *,
    event_type: str,
    currency: str,
    amount: object,
    event_date: object,
    user_id: str | None = None,
    portfolio_id: str | None = None,
    memo: str | None = None,
    fx_rate_to_krw: object | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "event_date": event_date,
        "currency": currency,
        "event_type": event_type,
        "amount": amount,
    }
    if user_id:
        entry["user_id"] = user_id
    if portfolio_id:
        entry["portfolio_id"] = portfolio_id
    if memo:
        entry["memo"] = memo
    if fx_rate_to_krw not in (None, ""):
        entry["fx_rate_to_krw"] = fx_rate_to_krw
    return validate_cash_ledger_entry(entry)


def create_opening_balance_entries(
    cash_balances: Mapping[str, object],
    *,
    event_date: object,
    user_id: str | None = None,
    portfolio_id: str | None = None,
    memo: str = "기존 수동 현금 잔고를 현금 원장 시작 잔고로 이전",
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for currency in ("KRW", "USD"):
        amount = _to_decimal(currency, cash_balances.get(currency, 0))
        if amount == ZERO:
            continue
        entries.append(
            create_cash_movement_entry(
                event_type="opening_balance",
                currency=currency,
                amount=amount,
                event_date=event_date,
                user_id=user_id,
                portfolio_id=portfolio_id,
                memo=memo,
            )
        )
    return entries


def create_balance_adjustment_entries(
    target_cash_balances: Mapping[str, object],
    existing_cash_ledger_rows: Iterable[Mapping[str, Any]],
    *,
    event_date: object,
    user_id: str | None = None,
    portfolio_id: str | None = None,
    memo: str = "현금 잔고 수동 조정",
) -> list[dict[str, object]]:
    existing_rows = normalize_cash_ledger_rows(existing_cash_ledger_rows)
    if not existing_rows:
        return create_opening_balance_entries(
            target_cash_balances,
            event_date=event_date,
            user_id=user_id,
            portfolio_id=portfolio_id,
            memo="현금 원장 시작 잔고",
        )

    current_balances = calculate_cash_balances(existing_rows)
    entries: list[dict[str, object]] = []
    for currency in ("KRW", "USD"):
        target = _to_decimal(currency, target_cash_balances.get(currency, 0))
        diff = target - current_balances[currency]
        if math.isclose(float(diff), 0.0, abs_tol=1e-9):
            continue
        entries.append(
            create_cash_movement_entry(
                event_type="manual_adjustment",
                currency=currency,
                amount=diff,
                event_date=event_date,
                user_id=user_id,
                portfolio_id=portfolio_id,
                memo=memo,
            )
        )
    return entries
