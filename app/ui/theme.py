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


APP_THEME_KEY = "app_theme_mode"
DEFAULT_THEME_MODE = "dark"


@dataclass(frozen=True)
class AppTheme:
    mode: str
    background: str
    background_accent: str
    surface: str
    surface_alt: str
    panel: str
    panel_strong: str
    text: str
    heading: str
    muted: str
    border: str
    border_strong: str
    primary: str
    primary_hover: str
    primary_soft: str
    positive: str
    negative: str
    neutral: str
    warning: str
    cash: str
    missing: str
    input_bg: str
    table_header: str
    table_hover: str
    chart_grid: str
    chart_zero: str
    chart_hover_bg: str
    chart_hover_border: str
    shadow: str
    summary_card_bg: str
    summary_panel_bg: str
    summary_heatmap_bg: str
    summary_heatmap_border: str
    up_text: str
    up_bg: str
    up_border: str
    down_text: str
    down_bg: str
    down_border: str
    neutral_badge_bg: str

    def css_variables(self) -> dict[str, str]:
        return {
            "app-bg": self.background,
            "app-bg-accent": self.background_accent,
            "app-surface": self.surface,
            "app-surface-alt": self.surface_alt,
            "app-panel": self.panel,
            "app-panel-strong": self.panel_strong,
            "app-text": self.text,
            "app-heading": self.heading,
            "app-muted": self.muted,
            "app-border": self.border,
            "app-border-strong": self.border_strong,
            "app-primary": self.primary,
            "app-primary-hover": self.primary_hover,
            "app-primary-soft": self.primary_soft,
            "app-positive": self.positive,
            "app-negative": self.negative,
            "app-neutral": self.neutral,
            "app-warning": self.warning,
            "app-cash": self.cash,
            "app-missing": self.missing,
            "app-input-bg": self.input_bg,
            "app-table-header": self.table_header,
            "app-table-hover": self.table_hover,
            "app-chart-grid": self.chart_grid,
            "app-chart-zero": self.chart_zero,
            "app-chart-hover-bg": self.chart_hover_bg,
            "app-chart-hover-border": self.chart_hover_border,
            "app-shadow": self.shadow,
            "summary-card-bg": self.summary_card_bg,
            "summary-panel-bg": self.summary_panel_bg,
            "summary-heatmap-bg": self.summary_heatmap_bg,
            "summary-heatmap-border": self.summary_heatmap_border,
            "summary-up-text": self.up_text,
            "summary-up-bg": self.up_bg,
            "summary-up-border": self.up_border,
            "summary-down-text": self.down_text,
            "summary-down-bg": self.down_bg,
            "summary-down-border": self.down_border,
            "summary-neutral-badge-bg": self.neutral_badge_bg,
        }


APP_THEMES = {
    "dark": AppTheme(
        mode="dark",
        background="#050B16",
        background_accent="radial-gradient(circle at 15% -10%, rgba(37, 99, 235, 0.22), transparent 32%), linear-gradient(180deg, #06101D 0%, #08111E 42%, #030713 100%)",
        surface="#08111E",
        surface_alt="#0D1728",
        panel="#101B2D",
        panel_strong="#15233A",
        text="#E5E7EB",
        heading="#F8FAFC",
        muted="#94A3B8",
        border="rgba(148, 163, 184, 0.22)",
        border_strong="rgba(148, 163, 184, 0.34)",
        primary="#3B82F6",
        primary_hover="#60A5FA",
        primary_soft="rgba(59, 130, 246, 0.16)",
        positive="#34D399",
        negative="#F87171",
        neutral="#94A3B8",
        warning="#F59E0B",
        cash="#FBBF24",
        missing="#64748B",
        input_bg="#0B1424",
        table_header="rgba(15, 23, 42, 0.78)",
        table_hover="rgba(59, 130, 246, 0.10)",
        chart_grid="rgba(148, 163, 184, 0.18)",
        chart_zero="rgba(148, 163, 184, 0.46)",
        chart_hover_bg="rgba(8, 17, 30, 0.96)",
        chart_hover_border="rgba(148, 163, 184, 0.28)",
        shadow="0 20px 60px rgba(2, 8, 23, 0.42)",
        summary_card_bg="radial-gradient(circle at 18% 0%, rgba(22, 55, 92, 0.34), transparent 38%), linear-gradient(135deg, #050B16 0%, #091321 52%, #030713 100%)",
        summary_panel_bg="linear-gradient(180deg, rgba(20, 31, 51, 0.92), rgba(9, 17, 31, 0.92))",
        summary_heatmap_bg="#050A13",
        summary_heatmap_border="#000000",
        up_text="#FEE2E2",
        up_bg="rgba(220, 90, 94, 0.36)",
        up_border="rgba(248, 113, 113, 0.38)",
        down_text="#DBEAFE",
        down_bg="rgba(59, 130, 246, 0.28)",
        down_border="rgba(96, 165, 250, 0.34)",
        neutral_badge_bg="rgba(75, 85, 99, 0.35)",
    ),
    "light": AppTheme(
        mode="light",
        background="#F4F7FB",
        background_accent="radial-gradient(circle at 15% -10%, rgba(59, 130, 246, 0.16), transparent 32%), linear-gradient(180deg, #F8FAFC 0%, #EFF4FA 44%, #E9EEF6 100%)",
        surface="#FFFFFF",
        surface_alt="#F8FAFC",
        panel="#FFFFFF",
        panel_strong="#EFF4FA",
        text="#172033",
        heading="#0F172A",
        muted="#64748B",
        border="rgba(100, 116, 139, 0.22)",
        border_strong="rgba(100, 116, 139, 0.36)",
        primary="#2563EB",
        primary_hover="#1D4ED8",
        primary_soft="rgba(37, 99, 235, 0.12)",
        positive="#059669",
        negative="#DC2626",
        neutral="#64748B",
        warning="#D97706",
        cash="#D97706",
        missing="#94A3B8",
        input_bg="#FFFFFF",
        table_header="rgba(241, 245, 249, 0.96)",
        table_hover="rgba(37, 99, 235, 0.07)",
        chart_grid="rgba(100, 116, 139, 0.18)",
        chart_zero="rgba(100, 116, 139, 0.42)",
        chart_hover_bg="rgba(15, 23, 42, 0.94)",
        chart_hover_border="rgba(255, 255, 255, 0.28)",
        shadow="0 18px 46px rgba(15, 23, 42, 0.10)",
        summary_card_bg="linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 52%, #EEF4FB 100%)",
        summary_panel_bg="linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(241, 245, 249, 0.96))",
        summary_heatmap_bg="#E2E8F0",
        summary_heatmap_border="rgba(100, 116, 139, 0.22)",
        up_text="#991B1B",
        up_bg="rgba(254, 226, 226, 0.92)",
        up_border="rgba(248, 113, 113, 0.34)",
        down_text="#1D4ED8",
        down_bg="rgba(219, 234, 254, 0.96)",
        down_border="rgba(96, 165, 250, 0.36)",
        neutral_badge_bg="rgba(226, 232, 240, 0.95)",
    ),
}


def normalize_theme_mode(value: object | None) -> str:
    mode = str(value or DEFAULT_THEME_MODE).strip().lower()
    return mode if mode in APP_THEMES else DEFAULT_THEME_MODE


def get_app_theme(mode: object | None = None) -> AppTheme:
    return APP_THEMES[normalize_theme_mode(mode)]


def get_active_theme() -> AppTheme:
    try:
        import streamlit as st

        return get_app_theme(st.session_state.get(APP_THEME_KEY, DEFAULT_THEME_MODE))
    except Exception:
        return get_app_theme(DEFAULT_THEME_MODE)


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
