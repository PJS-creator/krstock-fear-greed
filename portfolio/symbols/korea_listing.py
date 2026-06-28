from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import SymbolCandidate


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def korea_listing_records_from_frame(frame: Any) -> list[dict[str, str]]:
    if frame is None or not hasattr(frame, "columns"):
        return []
    code_column = "Code" if "Code" in frame.columns else "Symbol" if "Symbol" in frame.columns else None
    if code_column is None or "Name" not in frame.columns:
        return []
    records: list[dict[str, str]] = []
    for _, row in frame.iterrows():
        ticker = _clean(row.get(code_column)).zfill(6)
        name = _clean(row.get("Name"))
        if len(ticker) == 6 and ticker.isdigit() and name:
            records.append({"ticker": ticker, "display_name": name})
    records.sort(key=lambda item: (item["display_name"], item["ticker"]))
    return records


def load_korea_listing_records(listing_loader) -> list[dict[str, str]]:
    return korea_listing_records_from_frame(listing_loader("KRX"))


def search_korea_listing(query: str, records: Iterable[Mapping[str, str]]) -> list[SymbolCandidate]:
    needle = _clean(query)
    if not needle:
        return []
    normalized_needle = needle.replace(" ", "").casefold()
    exact: list[SymbolCandidate] = []
    partial: list[SymbolCandidate] = []
    for record in records:
        ticker = _clean(record.get("ticker")).zfill(6)
        display_name = _clean(record.get("display_name") or record.get("name"))
        if not ticker or not display_name:
            continue
        candidate = SymbolCandidate(market="KR", ticker=ticker, display_name=display_name, currency="KRW")
        normalized_name = display_name.replace(" ", "").casefold()
        if normalized_name == normalized_needle:
            exact.append(candidate)
        elif normalized_needle in normalized_name:
            partial.append(candidate)
    return exact or partial
