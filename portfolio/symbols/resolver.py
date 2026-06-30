from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from portfolio.holdings import normalize_korea_ticker, normalize_ticker

from .korea_listing import search_korea_listing
from .models import InputPreviewResult, SymbolCandidate, SymbolResolution


SIMPLE_PORTFOLIO_COLUMNS = ["ticker_or_name", "quantity", "avg_price"]
SIMPLE_HISTORICAL_COLUMNS = ["as_of_date", "ticker_or_name", "quantity"]
EVENT_COLUMNS = ["date", "ticker_or_name", "quantity_after"]


def clean_symbol_input(value: object) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _contains_hangul(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))


def _parse_non_negative(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def _parse_optional_non_negative(value: object, field_name: str) -> float | None:
    if clean_symbol_input(value) == "":
        return None
    return _parse_non_negative(value, field_name)


def _looks_like_number(value: object) -> bool:
    try:
        _parse_non_negative(value, "value")
    except ValueError:
        return False
    return True


def _resolution_from_candidate(raw_input: str, candidate: SymbolCandidate, *, confidence: float, message: str) -> SymbolResolution:
    return SymbolResolution(
        raw_input=raw_input,
        market=candidate.market,
        ticker=candidate.ticker,
        display_name=candidate.display_name,
        currency=candidate.currency,
        confidence=confidence,
        candidates=[candidate],
        status="resolved",
        message=message,
    )


def resolve_symbol(raw_input: object, korea_listing_records: Iterable[Mapping[str, str]] | None = None) -> SymbolResolution:
    text = clean_symbol_input(raw_input)
    if not text:
        return SymbolResolution(raw_input="", status="invalid", message="종목명 또는 티커를 입력하세요.")

    upper = text.upper()
    try:
        if upper.startswith("KR:") or upper.endswith(".KS") or upper.endswith(".KQ") or re.fullmatch(r"\d{6}", upper):
            ticker = normalize_korea_ticker(upper)
            return SymbolResolution(
                raw_input=text,
                market="KR",
                ticker=ticker,
                display_name=ticker,
                currency="KRW",
                confidence=0.95,
                status="resolved",
                message="국내 6자리 종목코드로 인식했습니다.",
            )
        if re.fullmatch(r"[A-Z][A-Z0-9.\-]*", upper):
            ticker = normalize_ticker(upper)
            return SymbolResolution(
                raw_input=text,
                market="US",
                ticker=ticker,
                display_name=ticker,
                currency="USD",
                confidence=0.9,
                status="resolved",
                message="미국 ticker로 인식했습니다.",
            )
    except ValueError as exc:
        return SymbolResolution(raw_input=text, status="invalid", message=str(exc))

    if _contains_hangul(text):
        candidates = search_korea_listing(text, korea_listing_records or [])
        if len(candidates) == 1:
            return _resolution_from_candidate(text, candidates[0], confidence=1.0, message="국내 종목명 1개 후보를 자동 적용했습니다.")
        if len(candidates) > 1:
            return SymbolResolution(
                raw_input=text,
                candidates=candidates,
                status="ambiguous",
                message="여러 국내 종목 후보가 있습니다. 하나를 직접 선택하세요.",
            )
        return SymbolResolution(raw_input=text, status="not_found", message="국내 종목명 후보를 찾지 못했습니다. 6자리 ticker를 입력하세요.")

    return SymbolResolution(raw_input=text, status="invalid", message="종목명 또는 ticker 형식을 확인하세요.")


def parse_symbol_quantity_lines(text: str, *, with_date: bool = False, quantity_name: str = "quantity") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"[,\t ]+", line) if part.strip()]
        if with_date:
            if len(parts) < 3:
                rows.append({"row_number": str(line_number), "error": "기준일, 종목명 또는 티커, 수량을 입력하세요."})
                continue
            rows.append(
                {
                    "row_number": str(line_number),
                    "as_of_date": parts[0],
                    "ticker_or_name": " ".join(parts[1:-1]),
                    quantity_name: parts[-1],
                }
            )
        else:
            if len(parts) < 2:
                rows.append({"row_number": str(line_number), "error": "종목명 또는 티커와 수량을 입력하세요."})
                continue
            row = {"row_number": str(line_number), "ticker_or_name": " ".join(parts[:-1]), quantity_name: parts[-1]}
            if len(parts) >= 3 and _looks_like_number(parts[-2]) and _looks_like_number(parts[-1]):
                row = {
                    "row_number": str(line_number),
                    "ticker_or_name": " ".join(parts[:-2]),
                    quantity_name: parts[-2],
                    "avg_price": parts[-1],
                }
            rows.append(row)
    return rows


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


def build_input_preview(
    rows: Iterable[Mapping[str, Any]],
    *,
    korea_listing_records: Iterable[Mapping[str, str]] | None = None,
    require_date: bool = False,
    quantity_field: str = "quantity",
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
        raw_input = row.get("ticker_or_name") or row.get("ticker") or row.get("symbol")
        if not any(clean_symbol_input(row.get(field)) for field in ("as_of_date", "ticker_or_name", "ticker", "symbol", quantity_field, "avg_price")):
            continue
        as_of_date = ""
        if require_date:
            try:
                as_of_date = date.fromisoformat(clean_symbol_input(row.get("as_of_date") or row.get("date"))[:10]).isoformat()
            except ValueError:
                message = "기준일은 YYYY-MM-DD 형식이어야 합니다."
                errors.append(f"{row_number}행: {message}")
                preview_rows.append({"row_number": row_number, "status": "error", "message": message, "raw_input": clean_symbol_input(raw_input)})
                counts["error"] += 1
                continue
        try:
            quantity = _parse_non_negative(row.get(quantity_field), quantity_field)
        except ValueError as exc:
            errors.append(f"{row_number}행: {exc}")
            preview_rows.append({"row_number": row_number, "status": "error", "message": str(exc), "raw_input": clean_symbol_input(raw_input)})
            counts["error"] += 1
            continue
        try:
            avg_price = _parse_optional_non_negative(row.get("avg_price"), "avg_price")
        except ValueError as exc:
            errors.append(f"{row_number}행: {exc}")
            preview_rows.append({"row_number": row_number, "status": "error", "message": str(exc), "raw_input": clean_symbol_input(raw_input)})
            counts["error"] += 1
            continue
        resolution = resolve_symbol(raw_input, korea_listing_records)
        status = "ok" if resolution.is_resolved else ("candidate_required" if resolution.status == "ambiguous" else "error")
        if status == "error":
            errors.append(f"{row_number}행: {resolution.message}")
        preview_row = {
            "row_number": row_number,
            "as_of_date": as_of_date,
            "raw_input": resolution.raw_input,
            "ticker": resolution.ticker,
            "display_name": resolution.display_name,
            "market": resolution.market,
            "currency": resolution.currency,
            quantity_field: quantity,
            "avg_price": avg_price,
            "status": status,
            "message": resolution.message,
            "candidates": [candidate.__dict__ for candidate in resolution.candidates],
        }
        preview_rows.append(preview_row)
        counts[status] += 1
    summary = {
        "total": len(preview_rows),
        "ok": counts["ok"],
        "candidate_required": counts["candidate_required"],
        "error": counts["error"],
    }
    return InputPreviewResult(rows=preview_rows, errors=errors, summary=summary)


def preview_rows_to_holdings(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    holdings: list[dict[str, object]] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        holdings.append(
            {
                "ticker": row.get("ticker"),
                "market": row.get("market"),
                "currency": row.get("currency"),
                "display_name": row.get("display_name") or row.get("ticker"),
                "quantity": row.get("quantity"),
                "avg_price": row.get("avg_price"),
            }
        )
    return holdings


def preview_rows_to_historical_snapshots(rows: Iterable[Mapping[str, Any]], *, quantity_field: str = "quantity") -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        snapshots.append(
            {
                "as_of_date": row.get("as_of_date"),
                "ticker": row.get("ticker"),
                "market": row.get("market"),
                "currency": row.get("currency"),
                "display_name": row.get("display_name") or row.get("ticker"),
                "quantity": row.get(quantity_field),
            }
        )
    return snapshots


def copy_previous_snapshot(rows: Iterable[Mapping[str, Any]], new_date: str | date) -> list[dict[str, object]]:
    target_date = new_date.isoformat() if isinstance(new_date, date) else str(new_date)[:10]
    source_rows = [dict(row) for row in rows if clean_symbol_input(row.get("as_of_date"))]
    if not source_rows:
        return []
    dates = sorted({str(row.get("as_of_date"))[:10] for row in source_rows if str(row.get("as_of_date"))[:10] < target_date})
    source_date = dates[-1] if dates else sorted({str(row.get("as_of_date"))[:10] for row in source_rows})[-1]
    copied = []
    for row in source_rows:
        if str(row.get("as_of_date"))[:10] == source_date:
            next_row = dict(row)
            next_row["as_of_date"] = target_date
            copied.append(next_row)
    return copied


def snapshot_diff(previous_rows: Iterable[Mapping[str, Any]], current_rows: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    previous = {(str(row.get("market") or ""), str(row.get("ticker") or "")): float(row.get("quantity") or 0) for row in previous_rows}
    current = {(str(row.get("market") or ""), str(row.get("ticker") or "")): float(row.get("quantity") or 0) for row in current_rows}
    added = sorted(f"{market}/{ticker}" for market, ticker in current.keys() - previous.keys())
    removed = sorted(f"{market}/{ticker}" for market, ticker in previous.keys() - current.keys())
    increased = sorted(f"{market}/{ticker}" for market, ticker in current.keys() & previous.keys() if current[(market, ticker)] > previous[(market, ticker)])
    decreased = sorted(f"{market}/{ticker}" for market, ticker in current.keys() & previous.keys() if current[(market, ticker)] < previous[(market, ticker)])
    unchanged = sorted(f"{market}/{ticker}" for market, ticker in current.keys() & previous.keys() if current[(market, ticker)] == previous[(market, ticker)])
    return {"new": added, "removed": removed, "increased": increased, "decreased": decreased, "unchanged": unchanged}


def event_rows_to_snapshots(event_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    events = sorted(
        [dict(row) for row in event_rows if row.get("status") == "ok" or row.get("ticker")],
        key=lambda row: (str(row.get("as_of_date") or row.get("date"))[:10], str(row.get("market") or ""), str(row.get("ticker") or "")),
    )
    holdings_by_key: dict[tuple[str, str], dict[str, object]] = {}
    snapshots: list[dict[str, object]] = []
    current_date = ""
    pending_events: list[dict[str, object]] = []

    def flush(date_text: str, rows_for_date: list[dict[str, object]]) -> None:
        for event in rows_for_date:
            market = str(event.get("market") or "")
            ticker = str(event.get("ticker") or "")
            quantity = float(event.get("quantity_after", event.get("quantity", 0)) or 0)
            key = (market, ticker)
            if quantity == 0:
                holdings_by_key.pop(key, None)
            else:
                holdings_by_key[key] = {
                    "as_of_date": date_text,
                    "market": market,
                    "ticker": ticker,
                    "display_name": event.get("display_name") or ticker,
                    "currency": event.get("currency") or ("KRW" if market == "KR" else "USD"),
                    "quantity": quantity,
                }
        for _, row in sorted(holdings_by_key.items()):
            snapshot_row = dict(row)
            snapshot_row["as_of_date"] = date_text
            snapshots.append(snapshot_row)

    for event in events:
        date_text = str(event.get("as_of_date") or event.get("date"))[:10]
        if current_date and date_text != current_date:
            flush(current_date, pending_events)
            pending_events = []
        current_date = date_text
        pending_events.append(event)
    if current_date:
        flush(current_date, pending_events)
    return snapshots
