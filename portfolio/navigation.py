from __future__ import annotations


QUICK_NAV_TARGETS: dict[str, tuple[str, str | None]] = {
    "profit": ("analysis", "profit"),
    "tax": ("analysis", "tax"),
    "dividend": ("analysis", "dividend"),
    "trend": ("analysis", "trend"),
    "allocation": ("analysis", "allocation"),
    "journal": ("journal", None),
    "cash": ("input", "cash_fx"),
    "trade": ("input", "transactions"),
}


def resolve_quick_nav_target(key: str) -> tuple[str, str | None] | None:
    return QUICK_NAV_TARGETS.get(str(key))
