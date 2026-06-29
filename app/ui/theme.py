from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

SEMANTIC_COLORS = {
    "positive": "#16A34A",
    "negative": "#DC2626",
    "neutral": "#64748B",
    "primary": "#1D4ED8",
    "secondary": "#0F766E",
    "warning": "#D97706",
    "cash": "#F59E0B",
    "missing": "#94A3B8",
    "surface": "#F8FAFC",
    "ink": "#111827",
}

CATEGORY_COLORS = [
    "#1D4ED8",
    "#0F766E",
    "#B45309",
    "#16A34A",
    "#BE123C",
    "#6D28D9",
    "#0891B2",
    "#C026D3",
    "#65A30D",
    "#475569",
]

CURRENCY_COLORS = {
    "KRW": "#0F766E",
    "USD": "#1D4ED8",
    "CASH": "#F59E0B",
}

STATUS_COLORS = {
    "updated": SEMANTIC_COLORS["positive"],
    "cached": SEMANTIC_COLORS["primary"],
    "stale": SEMANTIC_COLORS["warning"],
    "failed": SEMANTIC_COLORS["negative"],
    "missing": SEMANTIC_COLORS["missing"],
    "missing_api_key": SEMANTIC_COLORS["missing"],
    "manual": SEMANTIC_COLORS["neutral"],
}


@dataclass(frozen=True)
class ChartDimensions:
    compact_height: int = 300
    default_height: int = 410
    tall_height: int = 500
    row_height: int = 38
    max_table_height: int = 520


DIMENSIONS = ChartDimensions()


def deterministic_color(key: object, palette: Iterable[str] = CATEGORY_COLORS) -> str:
    colors = list(palette)
    if not colors:
        raise ValueError("palette must contain at least one color")
    digest = hashlib.sha256(str(key).upper().encode("utf-8")).hexdigest()
    return colors[int(digest[:8], 16) % len(colors)]


def signed_color(value: float | None) -> str:
    if value is None or value == 0:
        return SEMANTIC_COLORS["neutral"]
    return SEMANTIC_COLORS["positive"] if value > 0 else SEMANTIC_COLORS["negative"]


def status_color(status: object) -> str:
    return STATUS_COLORS.get(str(status or "").lower(), SEMANTIC_COLORS["neutral"])


def chart_config() -> dict[str, object]:
    return {
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    }
