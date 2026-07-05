from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from portfolio.cash_ledger import normalize_cash_ledger_rows
from portfolio.transactions import normalize_transaction_rows


NOTE_TAGS = {"전략", "복기", "실수", "뉴스", "기타"}


@dataclass(frozen=True)
class JournalEvent:
    event_id: str
    event_date: str
    event_type: str
    title: str
    subtitle: str
    symbol: str | None
    market: str | None
    currency: str | None
    amount: float | None
    quantity: float | None
    price: float | None
    realized_pnl: float | None
    cash_impact: float | None
    source_type: str
    source_id: str | None
    tags: tuple[str, ...]
    detail: Mapping[str, Any]


def _stable_id(prefix: str, values: Iterable[object]) -> str:
    text = "|".join(str(value) for value in values)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _clean_text(value: object | None) -> str:
    return str(value or "").strip()


def _event_day(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = _clean_text(value)
    if not text:
        raise ValueError("event date is required")
    return text[:10]


def _to_float(value: object | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _tags(value: object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_tags = [part.strip() for part in value.replace(";", ",").split(",")]
    elif isinstance(value, Iterable):
        raw_tags = [str(part).strip() for part in value]
    else:
        raw_tags = [str(value).strip()]
    clean = []
    for tag in raw_tags:
        if not tag:
            continue
        clean.append(tag if tag in NOTE_TAGS else "기타")
    return tuple(dict.fromkeys(clean))


def normalize_journal_note(row: Mapping[str, Any]) -> dict[str, object]:
    note_date = _event_day(row.get("note_date") or row.get("event_date") or row.get("date"))
    title = _clean_text(row.get("title"))
    if not title:
        raise ValueError("title is required")
    note_id = _clean_text(row.get("id")) or _stable_id("note", [note_date, title, row.get("body")])
    return {
        "id": note_id,
        "note_date": note_date,
        "title": title,
        "body": _clean_text(row.get("body")),
        "symbol": _clean_text(row.get("symbol")) or None,
        "market": _clean_text(row.get("market")) or None,
        "linked_transaction_id": _clean_text(row.get("linked_transaction_id")) or None,
        "linked_cash_ledger_id": _clean_text(row.get("linked_cash_ledger_id")) or None,
        "tags": list(_tags(row.get("tags"))),
    }


def normalize_journal_notes(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized = []
    for index, row in enumerate(rows, start=1):
        if not any(_clean_text(row.get(field)) for field in ("title", "body", "note_date", "date")):
            continue
        try:
            normalized.append(normalize_journal_note(row))
        except ValueError as exc:
            raise ValueError(f"Journal note row {index}: {exc}") from exc
    return sorted(normalized, key=lambda row: (str(row["note_date"]), str(row["title"])))


def _transaction_event(row: Mapping[str, Any]) -> JournalEvent:
    tx_type = str(row["transaction_type"])
    side_label = "매수" if tx_type == "buy" else "매도"
    quantity = float(row["quantity"])
    price = float(row["unit_price"])
    fee = float(row.get("fee") or 0.0)
    tax = float(row.get("tax") or 0.0)
    gross = quantity * price
    cash_impact = -(gross + fee + tax) if tx_type == "buy" else gross - fee - tax
    tx_id = _clean_text(row.get("id") or row.get("transaction_id") or row.get("external_id"))
    event_id = tx_id or _stable_id("transaction", [row["occurred_at"], row["market"], row["ticker"], tx_type, quantity, price, row.get("note")])
    title = f"{side_label} · {row['display_name']}"
    subtitle = f"{quantity:g}주 x {price:g} {row['currency']}"
    return JournalEvent(
        event_id=f"transaction:{event_id}",
        event_date=_event_day(row["occurred_at"]),
        event_type=tx_type,
        title=title,
        subtitle=subtitle,
        symbol=str(row["ticker"]),
        market=str(row["market"]),
        currency=str(row["currency"]),
        amount=gross,
        quantity=quantity,
        price=price,
        realized_pnl=None,
        cash_impact=cash_impact,
        source_type="transaction",
        source_id=tx_id or None,
        tags=(),
        detail=dict(row),
    )


def _settlement_event_type(transaction_type: object) -> str | None:
    if str(transaction_type) == "buy":
        return "buy_settlement"
    if str(transaction_type) == "sell":
        return "sell_settlement"
    return None


def _amount_key(value: object) -> float:
    return round(abs(float(value)), 6)


def _transaction_settlement_keys(rows: Iterable[Mapping[str, Any]]) -> set[tuple[str, str, str, float]]:
    keys: set[tuple[str, str, str, float]] = set()
    for row in rows:
        event_type = _settlement_event_type(row.get("transaction_type"))
        if event_type is None:
            continue
        quantity = float(row["quantity"])
        price = float(row["unit_price"])
        fee = float(row.get("fee") or 0.0)
        tax = float(row.get("tax") or 0.0)
        gross = quantity * price
        amount = -(gross + fee + tax) if event_type == "buy_settlement" else gross - fee - tax
        keys.add((_event_day(row["occurred_at"]), str(row["currency"]), event_type, _amount_key(amount)))
    return keys


def _cash_settlement_key(row: Mapping[str, Any]) -> tuple[str, str, str, float]:
    return (_event_day(row["event_date"]), str(row["currency"]), str(row["event_type"]), _amount_key(row["amount"]))


def _ledger_label(event_type: str) -> str:
    return {
        "opening_balance": "시작 잔고",
        "deposit": "입금",
        "withdrawal": "출금",
        "buy_settlement": "매수 정산",
        "sell_settlement": "매도 정산",
        "dividend": "배당",
        "interest": "이자",
        "fee": "수수료",
        "tax": "세금",
        "fx_conversion_in": "환전 입금",
        "fx_conversion_out": "환전 출금",
        "manual_adjustment": "수동 조정",
    }.get(event_type, event_type)


def _cash_event(row: Mapping[str, Any]) -> JournalEvent:
    event_type = str(row["event_type"])
    amount = float(row["amount"])
    row_id = _clean_text(row.get("id") or row.get("external_id"))
    event_id = row_id or _stable_id("cash", [row["event_date"], row["currency"], event_type, amount, row.get("memo")])
    label = _ledger_label(event_type)
    return JournalEvent(
        event_id=f"cash:{event_id}",
        event_date=_event_day(row["event_date"]),
        event_type=event_type,
        title=label,
        subtitle=_clean_text(row.get("memo")) or f"{amount:g} {row['currency']}",
        symbol=_clean_text(row.get("ticker") or row.get("symbol")) or None,
        market=_clean_text(row.get("market")) or None,
        currency=str(row["currency"]),
        amount=amount,
        quantity=None,
        price=None,
        realized_pnl=None,
        cash_impact=amount,
        source_type="cash_ledger",
        source_id=row_id or None,
        tags=(),
        detail=dict(row),
    )


def _fx_pair_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    memo = _clean_text(row.get("memo")).replace(" 출금", "").replace(" 입금", "")
    return (_event_day(row["event_date"]), str(row.get("fx_rate_to_krw") or ""), memo)


def _fx_conversion_events(rows: list[dict[str, object]]) -> tuple[list[JournalEvent], set[int]]:
    out_rows: dict[tuple[str, str, str], tuple[int, dict[str, object]]] = {}
    in_rows: dict[tuple[str, str, str], tuple[int, dict[str, object]]] = {}
    for index, row in enumerate(rows):
        if row["event_type"] == "fx_conversion_out":
            out_rows[_fx_pair_key(row)] = (index, row)
        if row["event_type"] == "fx_conversion_in":
            in_rows[_fx_pair_key(row)] = (index, row)

    events: list[JournalEvent] = []
    used: set[int] = set()
    for key, (out_index, out_row) in out_rows.items():
        if key not in in_rows:
            continue
        in_index, in_row = in_rows[key]
        used.update({out_index, in_index})
        source_id = _stable_id("fx", [key, out_row.get("amount"), in_row.get("amount")])
        events.append(
            JournalEvent(
                event_id=source_id,
                event_date=_event_day(out_row["event_date"]),
                event_type="fx_conversion",
                title="환전",
                subtitle=f"{abs(float(out_row['amount'])):g} {out_row['currency']} -> {float(in_row['amount']):g} {in_row['currency']}",
                symbol=None,
                market=None,
                currency=f"{out_row['currency']}/{in_row['currency']}",
                amount=float(in_row["amount"]),
                quantity=None,
                price=_to_float(out_row.get("fx_rate_to_krw")),
                realized_pnl=None,
                cash_impact=None,
                source_type="cash_ledger",
                source_id=source_id,
                tags=(),
                detail={"out": out_row, "in": in_row},
            )
        )
    return events, used


def _note_event(row: Mapping[str, Any]) -> JournalEvent:
    return JournalEvent(
        event_id=f"note:{row['id']}",
        event_date=str(row["note_date"]),
        event_type="note",
        title=str(row["title"]),
        subtitle=str(row.get("body") or ""),
        symbol=_clean_text(row.get("symbol")) or None,
        market=_clean_text(row.get("market")) or None,
        currency=None,
        amount=None,
        quantity=None,
        price=None,
        realized_pnl=None,
        cash_impact=None,
        source_type="note",
        source_id=str(row["id"]),
        tags=tuple(str(tag) for tag in row.get("tags") or []),
        detail=dict(row),
    )


def build_journal_events(
    *,
    transactions: Iterable[Mapping[str, Any]] = (),
    cash_ledger: Iterable[Mapping[str, Any]] = (),
    journal_notes: Iterable[Mapping[str, Any]] = (),
    newest_first: bool = True,
) -> list[JournalEvent]:
    transaction_rows = normalize_transaction_rows(transactions)
    transaction_settlement_keys = _transaction_settlement_keys(transaction_rows)
    events = [_transaction_event(row) for row in transaction_rows]
    ledger_rows = normalize_cash_ledger_rows(cash_ledger)
    fx_events, fx_used = _fx_conversion_events(ledger_rows)
    events.extend(fx_events)
    for index, row in enumerate(ledger_rows):
        event_type = str(row["event_type"])
        if index in fx_used:
            continue
        if event_type in {"buy_settlement", "sell_settlement"} and _clean_text(row.get("linked_transaction_id")):
            continue
        if event_type in {"buy_settlement", "sell_settlement"} and _cash_settlement_key(row) in transaction_settlement_keys:
            continue
        events.append(_cash_event(row))
    events.extend(_note_event(row) for row in normalize_journal_notes(journal_notes))
    return sorted(events, key=lambda event: (event.event_date, event.event_id), reverse=newest_first)


def filter_journal_events(
    events: Iterable[JournalEvent],
    *,
    event_group: str = "전체",
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[JournalEvent]:
    group_types = {
        "매수/매도": {"buy", "sell"},
        "입금/출금": {"deposit", "withdrawal", "opening_balance", "manual_adjustment"},
        "환전": {"fx_conversion", "fx_conversion_in", "fx_conversion_out"},
        "배당/이자": {"dividend", "interest"},
        "메모": {"note"},
    }
    allowed = group_types.get(event_group)
    normalized_symbol = _clean_text(symbol).upper()
    output: list[JournalEvent] = []
    for event in events:
        if allowed is not None and event.event_type not in allowed:
            continue
        if normalized_symbol and _clean_text(event.symbol).upper() != normalized_symbol:
            continue
        if start_date and event.event_date < start_date:
            continue
        if end_date and event.event_date > end_date:
            continue
        output.append(event)
    return output
