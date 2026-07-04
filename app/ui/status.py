from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from portfolio.diagnostics import DiagnosticItem
from portfolio.holdings import (
    QUOTE_STATUS_FAILED,
    QUOTE_STATUS_MANUAL,
    QUOTE_STATUS_MISSING,
    QUOTE_STATUS_MISSING_API_KEY,
    QUOTE_STATUS_STALE,
    normalize_korea_ticker,
    normalize_ticker,
)
from portfolio.symbols import build_input_preview, parse_symbol_quantity_lines, preview_rows_to_holdings

from .formatters import format_kst

STATUS_LABELS = {
    "updated": "정상_최근종가",
    "cached": "정상_캐시",
    "stale": "이전저장값사용",
    "failed": "조회실패",
    "missing": "티커미확인",
    "missing_api_key": "API key 없음",
    "manual": "수동입력값",
}

ISSUE_STATUSES = {"stale", "failed", "missing", "missing_api_key"}
DEFAULT_PRICE_REFRESH_STATUSES = {
    "",
    QUOTE_STATUS_MISSING,
    QUOTE_STATUS_MISSING_API_KEY,
    QUOTE_STATUS_FAILED,
    QUOTE_STATUS_STALE,
    QUOTE_STATUS_MANUAL,
}
PRIMARY_DIAGNOSTIC_KEYS = {
    "max_position_weight",
    "top3_weight",
    "hhi",
    "cash_weight",
    "usd_exposure",
    "quote_freshness",
}


@dataclass(frozen=True)
class PriceStatusSummary:
    total: int
    updated: int
    cached: int
    stale: int
    failed: int
    missing: int
    manual: int

    @property
    def success(self) -> int:
        return self.updated + self.cached

    @property
    def has_issues(self) -> bool:
        return bool(self.stale or self.failed or self.missing)

    @property
    def short_text(self) -> str:
        return f"성공 {self.success} · 캐시 {self.cached} · 실패 {self.failed}"

    @property
    def detail_text(self) -> str:
        return f"정상 {self.updated} · 캐시 {self.cached} · 이전저장값 {self.stale} · 실패 {self.failed} · 미조회 {self.missing}"


@dataclass(frozen=True)
class DiagnosticPresentation:
    key: str
    label: str
    value: str
    severity_label: str
    help_text: str
    is_primary: bool


@dataclass(frozen=True)
class BulkInputResult:
    rows: list[dict[str, object]]
    errors: list[str]


def _get_value(obj: object, name: str, default: object = None) -> object:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def aggregate_price_statuses(statuses: Iterable[object]) -> PriceStatusSummary:
    counts = Counter(str(_get_value(status, "status", "")).lower() for status in statuses)
    missing = counts["missing"] + counts["missing_api_key"]
    total = sum(counts.values())
    return PriceStatusSummary(
        total=total,
        updated=counts["updated"],
        cached=counts["cached"],
        stale=counts["stale"],
        failed=counts["failed"],
        missing=missing,
        manual=counts["manual"],
    )


def quote_status_label(status: object) -> str:
    return STATUS_LABELS.get(str(status or "").lower(), str(status or "미조회"))


def select_price_refresh_rows(rows: Iterable[Mapping[str, Any]], mode: str) -> list[Mapping[str, Any]]:
    all_rows = list(rows)
    if mode == "실패 종목만":
        return [row for row in all_rows if str(row.get("quote_status") or "").lower() == QUOTE_STATUS_FAILED]
    if mode == "전체 강제 재조회":
        return all_rows
    return [
        row
        for row in all_rows
        if str(row.get("quote_status") or "").lower() in DEFAULT_PRICE_REFRESH_STATUSES
        or row.get("current_price") is None
    ]


def build_price_log_rows(statuses: Iterable[object], holdings_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    holdings_by_ticker = {str(row.get("ticker") or row.get("symbol") or "").upper(): row for row in holdings_rows}
    rows: list[dict[str, object]] = []
    for status in statuses:
        symbol = str(_get_value(status, "symbol", "")).upper()
        holding = holdings_by_ticker.get(symbol, {})
        rows.append(
            {
                "ticker": symbol,
                "종목명": holding.get("display_name") or holding.get("name") or symbol,
                "시장": _get_value(status, "market", holding.get("market", "")),
                "provider": holding.get("provider") or "-",
                "상태": quote_status_label(_get_value(status, "status", "")),
                "조회 시각": format_kst(_get_value(status, "fetched_at", holding.get("fetched_at")), compact=True),
                "가격 기준일": _get_value(status, "price_date", holding.get("price_date")) or "-",
                "기준시각": format_kst(_get_value(status, "as_of_timestamp", holding.get("as_of_timestamp")), compact=True),
                "출처": _get_value(status, "source", holding.get("source") or holding.get("provider") or "-"),
                "오류": _get_value(status, "error_message", holding.get("error_message")) or "",
                "message": str(_get_value(status, "message", "")).strip(),
                "raw_status": str(_get_value(status, "status", "")).lower(),
            }
        )
    return rows


def infer_market_from_ticker(value: object) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("KR:"):
        text = text[3:]
    for suffix in (".KS", ".KQ"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return "KR" if re.fullmatch(r"\d{6}", text) else "US"


def prepare_quick_input_records(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized_rows = [
        {
            "ticker_or_name": row.get("ticker_or_name") or row.get("ticker") or row.get("symbol"),
            "quantity": row.get("quantity"),
            "row_number": index,
        }
        for index, row in enumerate(rows, start=1)
    ]
    preview = build_input_preview(normalized_rows)
    if preview.errors:
        raise ValueError("; ".join(preview.errors))
    prepared: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for row in preview_rows_to_holdings(preview.rows):
        key = (str(row["market"]), str(row["ticker"]))
        if key in seen:
            raise ValueError(f"duplicate ticker: {key[0]}/{key[1]}")
        seen.add(key)
        prepared.append(row)
    return prepared


def parse_bulk_input(text: str) -> BulkInputResult:
    preview = build_input_preview(parse_symbol_quantity_lines(text))
    latest_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for row in preview_rows_to_holdings(preview.rows):
        latest_by_key[(str(row["market"]), str(row["ticker"]))] = row
    return BulkInputResult(rows=list(latest_by_key.values()), errors=preview.errors)


def dirty_signature(payload: Mapping[str, Any]) -> str:
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def diagnostic_severity_label(level: str) -> str:
    if level == "warning":
        return "확인 필요"
    if level == "info":
        return "데이터 부족"
    return "양호"


def present_diagnostic(item: DiagnosticItem, *, priced_count: int | None = None, holdings_count: int | None = None) -> DiagnosticPresentation:
    value = item.value
    help_text = item.message
    if item.key == "quote_freshness" and priced_count is not None and holdings_count is not None:
        value = f"{priced_count}/{holdings_count} 정상" if holdings_count else "데이터 부족"
        help_text = f"{item.message} · 세부 상태: {item.value}"
    return DiagnosticPresentation(
        key=item.key,
        label=item.label,
        value=value,
        severity_label=diagnostic_severity_label(item.level),
        help_text=help_text,
        is_primary=item.key in PRIMARY_DIAGNOSTIC_KEYS,
    )


def split_diagnostics(items: Iterable[DiagnosticPresentation]) -> tuple[list[DiagnosticPresentation], list[DiagnosticPresentation]]:
    primary: list[DiagnosticPresentation] = []
    details: list[DiagnosticPresentation] = []
    for item in items:
        if item.is_primary:
            primary.append(item)
        else:
            details.append(item)
    return primary, details
