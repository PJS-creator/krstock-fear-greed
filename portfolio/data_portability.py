from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from portfolio.cash_ledger import normalize_cash_ledger_rows, serialize_cash_ledger_rows
from portfolio.rebalancing import serialize_target_allocations
from portfolio.transactions import build_transaction_preview, normalize_transaction_rows, preview_rows_to_transactions

TRANSACTION_IMPORT_COLUMNS = [
    "external_id",
    "transaction_type",
    "ticker_or_name",
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
CASH_LEDGER_IMPORT_COLUMNS = [
    "external_id",
    "event_date",
    "currency",
    "event_type",
    "amount",
    "fx_rate_to_krw",
    "memo",
]


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    level: Literal["error", "duplicate"]
    message: str


@dataclass(frozen=True)
class ImportPreview:
    rows: list[dict[str, object]]
    valid_rows: list[dict[str, object]]
    issues: list[ImportIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.level == "error")

    @property
    def duplicate_count(self) -> int:
        return sum(1 for issue in self.issues if issue.level == "duplicate")


def csv_to_rows(content: str | bytes) -> list[dict[str, str]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return [dict(row) for row in reader]


def rows_to_csv(rows: Iterable[Mapping[str, Any]], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()


def transaction_duplicate_key(row: Mapping[str, Any]) -> tuple[object, ...]:
    external_id = str(row.get("external_id") or "").strip()
    if external_id:
        return ("external_id", external_id)
    return (
        str(row.get("occurred_at") or "")[:10],
        str(row.get("ticker") or row.get("symbol") or "").strip().upper(),
        str(row.get("transaction_type") or "").strip().lower(),
        f"{float(row.get('quantity') or 0):.8f}",
        f"{float(row.get('unit_price') or 0):.8f}",
        str(row.get("note") or "").strip(),
    )


def cash_ledger_duplicate_key(row: Mapping[str, Any]) -> tuple[object, ...]:
    external_id = str(row.get("external_id") or "").strip()
    if external_id:
        return ("external_id", external_id)
    return (
        str(row.get("event_date") or "")[:10],
        str(row.get("currency") or "").strip().upper(),
        str(row.get("event_type") or "").strip(),
        str(row.get("amount") or "").strip(),
        str(row.get("memo") or "").strip(),
    )


def preview_transaction_import(
    rows: Iterable[Mapping[str, Any]],
    *,
    existing_transactions: Iterable[Mapping[str, Any]] = (),
    korea_listing_records: Iterable[Mapping[str, str]] | None = None,
) -> ImportPreview:
    raw_rows = list(rows)
    preview = build_transaction_preview(raw_rows, korea_listing_records=korea_listing_records)
    existing_keys = {transaction_duplicate_key(row) for row in normalize_transaction_rows(existing_transactions)}
    seen_keys: set[tuple[object, ...]] = set()
    issues = [ImportIssue(int(row.get("row_number") or index), "error", str(row.get("message") or "입력 오류")) for index, row in enumerate(preview.rows, start=1) if row.get("status") == "error"]
    valid_rows: list[dict[str, object]] = []
    display_rows: list[dict[str, object]] = []
    for index, row in enumerate(preview.rows, start=1):
        next_row = dict(row)
        row_number = int(next_row.get("row_number") or index)
        if next_row.get("status") != "ok":
            display_rows.append(next_row)
            continue
        transactions = preview_rows_to_transactions([next_row])
        transaction = transactions[0] if transactions else None
        if transaction is None:
            issues.append(ImportIssue(row_number, "error", "거래 행을 정규화할 수 없습니다."))
            next_row["status"] = "error"
            next_row["message"] = "거래 행을 정규화할 수 없습니다."
            display_rows.append(next_row)
            continue
        raw_external_id = str(raw_rows[index - 1].get("external_id") or "").strip() if index - 1 < len(raw_rows) else ""
        if raw_external_id:
            transaction["external_id"] = raw_external_id
        key = transaction_duplicate_key(transaction)
        if key in existing_keys or key in seen_keys:
            issues.append(ImportIssue(row_number, "duplicate", "이미 저장된 거래 또는 업로드 파일 내 중복 거래입니다."))
            next_row["status"] = "duplicate"
            next_row["message"] = "중복 거래로 저장하지 않습니다."
            display_rows.append(next_row)
            continue
        seen_keys.add(key)
        valid_rows.append(transaction)
        display_rows.append(next_row)
    return ImportPreview(display_rows, valid_rows, issues)


def preview_cash_ledger_import(
    rows: Iterable[Mapping[str, Any]],
    *,
    existing_cash_ledger: Iterable[Mapping[str, Any]] = (),
) -> ImportPreview:
    existing_keys = {cash_ledger_duplicate_key(row) for row in normalize_cash_ledger_rows(existing_cash_ledger)}
    seen_keys: set[tuple[object, ...]] = set()
    issues: list[ImportIssue] = []
    valid_rows: list[dict[str, object]] = []
    display_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not any(str(row.get(field) or "").strip() for field in CASH_LEDGER_IMPORT_COLUMNS):
            continue
        try:
            clean_rows = serialize_cash_ledger_rows([row])
        except ValueError as exc:
            issues.append(ImportIssue(index, "error", str(exc)))
            display_rows.append({**dict(row), "row_number": index, "status": "error", "message": str(exc)})
            continue
        clean = clean_rows[0]
        key = cash_ledger_duplicate_key(clean)
        if key in existing_keys or key in seen_keys:
            issues.append(ImportIssue(index, "duplicate", "이미 저장된 원장 또는 업로드 파일 내 중복 원장입니다."))
            display_rows.append({**clean, "row_number": index, "status": "duplicate", "message": "중복 원장으로 저장하지 않습니다."})
            continue
        seen_keys.add(key)
        valid_rows.append(clean)
        display_rows.append({**clean, "row_number": index, "status": "ok", "message": "저장 가능"})
    return ImportPreview(display_rows, valid_rows, issues)


def build_full_export_payload(
    *,
    holdings: Iterable[Mapping[str, Any]],
    transactions: Iterable[Mapping[str, Any]],
    cash_ledger: Iterable[Mapping[str, Any]],
    target_allocations: Iterable[Mapping[str, Any]],
    portfolio_snapshot: Mapping[str, Any],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "transactions": normalize_transaction_rows(transactions),
        "cash_ledger": serialize_cash_ledger_rows(cash_ledger),
        "target_allocations": serialize_target_allocations(target_allocations),
        "portfolio_snapshot": dict(portfolio_snapshot),
        "holdings": list(holdings),
    }
