from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable

APP_THEME_KEY = "app_theme_mode"
THEME_MODE_ALIAS_KEY = "theme_mode"
DEFAULT_THEME_MODE = "dark"
PNL_COLOR_MODE = "kr"


def _transparent(hex_color: str, alpha: float) -> str:
    color = hex_color.lstrip("#")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {alpha:.2f})"


@dataclass(frozen=True)
class AppTheme:
    mode: str
    values: dict[str, str]

    def token(self, name: str) -> str:
        return self.values[name]

    def tokens(self) -> dict[str, str]:
        tokens = dict(self.values)
        tokens.update(
            {
                "positive": tokens["profit"],
                "positive_bg": tokens["profit_soft"],
                "negative": tokens["loss"],
                "negative_bg": tokens["loss_soft"],
                "neutral": tokens["neutral_value"],
                "success_bg": tokens["success_soft"],
                "danger_bg": tokens["danger_soft"],
                "warning_bg": tokens["warning_soft"],
                "info_bg": tokens["info_soft"],
                "surface_alt": tokens["surface_raised"],
                "panel": tokens["card_bg"],
                "panel_strong": tokens["surface_raised"],
                "table_hover": tokens["surface_hover"],
            }
        )
        return tokens

    def css_variables(self) -> dict[str, str]:
        tokens = self.tokens()
        variables = {
            "app-bg": tokens["bg"],
            "app-bg-accent": tokens["bg_subtle"],
            "app-surface": tokens["surface"],
            "app-surface-alt": tokens["surface_raised"],
            "app-panel": tokens["card_bg"],
            "app-panel-strong": tokens["surface_raised"],
            "app-text": tokens["text"],
            "app-heading": tokens["heading"],
            "app-muted": tokens["text_muted"],
            "app-border": tokens["border"],
            "app-border-strong": tokens["border_strong"],
            "app-primary": tokens["primary"],
            "app-primary-hover": tokens["primary_hover"],
            "app-primary-active": tokens["primary_active"],
            "app-primary-soft": tokens["primary_soft"],
            "app-primary-text": tokens["primary_text"],
            "app-accent": tokens["accent"],
            "app-accent-soft": tokens["accent_soft"],
            "app-profit": tokens["profit"],
            "app-profit-soft": tokens["profit_soft"],
            "app-profit-text": tokens["profit_text"],
            "app-loss": tokens["loss"],
            "app-loss-soft": tokens["loss_soft"],
            "app-loss-text": tokens["loss_text"],
            "app-positive": tokens["profit"],
            "app-negative": tokens["loss"],
            "app-success": tokens["success"],
            "app-warning": tokens["warning"],
            "app-danger": tokens["danger"],
            "app-info": tokens["info"],
            "app-neutral": tokens["neutral_value"],
            "app-cash": tokens["cash"],
            "app-missing": tokens["text_subtle"],
            "app-input-bg": tokens["input_bg"],
            "app-table-header": tokens["table_header_bg"],
            "app-table-hover": tokens["surface_hover"],
            "app-chart-grid": tokens["chart_grid"],
            "app-chart-zero": tokens["chart_axis"],
            "app-chart-hover-bg": tokens["chart_tooltip_bg"],
            "app-chart-hover-border": tokens["border_strong"],
            "app-shadow": tokens["card_shadow"],
            "app-shadow-sm": tokens["shadow_sm"],
            "app-primary-shadow": tokens["primary_shadow"],
            "summary-card-bg": tokens["summary_card_bg"],
            "summary-panel-bg": tokens["summary_panel_bg"],
            "summary-heatmap-bg": tokens["summary_heatmap_bg"],
            "summary-heatmap-border": tokens["summary_heatmap_border"],
            "summary-heatmap-tile-border": tokens["summary_heatmap_tile_border"],
            "summary-up-text": tokens["profit_text"],
            "summary-up-bg": tokens["profit_soft"],
            "summary-up-border": tokens["profit_border"],
            "summary-down-text": tokens["loss_text"],
            "summary-down-bg": tokens["loss_soft"],
            "summary-down-border": tokens["loss_border"],
            "summary-neutral-badge-bg": tokens["neutral_value_soft"],
        }
        variables.update({f"token-{name.replace('_', '-')}": value for name, value in tokens.items()})
        return variables

    def __getattr__(self, name: str) -> str:
        alias = {
            "background": "bg",
            "background_accent": "bg_subtle",
            "surface_alt": "surface_raised",
            "panel": "card_bg",
            "panel_strong": "surface_raised",
            "muted": "text_muted",
            "positive": "profit",
            "negative": "loss",
            "neutral": "neutral_value",
            "cash": "cash",
            "missing": "text_subtle",
            "table_header": "table_header_bg",
            "table_hover": "surface_hover",
            "chart_zero": "chart_axis",
            "chart_hover_bg": "chart_tooltip_bg",
            "chart_hover_border": "border_strong",
            "shadow": "card_shadow",
            "summary_card_bg": "summary_card_bg",
            "summary_panel_bg": "summary_panel_bg",
            "summary_heatmap_bg": "summary_heatmap_bg",
            "summary_heatmap_border": "summary_heatmap_border",
            "summary_heatmap_tile_border": "summary_heatmap_tile_border",
            "up_text": "profit_text",
            "up_bg": "profit_soft",
            "up_border": "profit_border",
            "down_text": "loss_text",
            "down_bg": "loss_soft",
            "down_border": "loss_border",
            "neutral_badge_bg": "neutral_value_soft",
        }
        if name in alias:
            return self.values[alias[name]]
        if name in self.values:
            return self.values[name]
        raise AttributeError(name)


def _theme_values(
    *,
    mode: str,
    bg: str,
    bg_subtle: str,
    surface: str,
    surface_raised: str,
    surface_sunken: str,
    surface_hover: str,
    text: str,
    text_muted: str,
    text_subtle: str,
    border: str,
    border_strong: str,
    primary: str,
    primary_hover: str,
    primary_active: str,
    primary_soft: str,
    accent: str,
    accent_hover: str,
    accent_soft: str,
    profit: str,
    profit_soft: str,
    profit_text: str,
    loss: str,
    loss_soft: str,
    loss_text: str,
    success: str,
    success_soft: str,
    success_text: str,
    warning: str,
    warning_soft: str,
    warning_text: str,
    danger: str,
    danger_soft: str,
    danger_text: str,
    info: str,
    info_soft: str,
    info_text: str,
    cash: str,
    cash_soft: str,
    krw: str,
    krw_soft: str,
    usd: str,
    usd_soft: str,
    shadow: str,
    shadow_sm: str,
    primary_shadow: str,
    summary_card_bg: str,
    summary_panel_bg: str,
    summary_heatmap_bg: str,
    summary_heatmap_border: str,
    summary_heatmap_tile_border: str,
) -> dict[str, str]:
    neutral_value = text_subtle
    values = {
        "mode": mode,
        "bg": bg,
        "bg_subtle": bg_subtle,
        "surface": surface,
        "surface_raised": surface_raised,
        "surface_sunken": surface_sunken,
        "surface_hover": surface_hover,
        "text": text,
        "heading": "#F8FAFC" if mode == "dark" else "#0F172A",
        "text_muted": text_muted,
        "text_subtle": text_subtle,
        "text_inverse": "#0F172A" if mode == "dark" else "#FFFFFF",
        "border": border,
        "border_strong": border_strong,
        "divider": border,
        "shadow": shadow,
        "shadow_sm": shadow_sm,
        "overlay": "rgba(2, 8, 23, 0.64)" if mode == "dark" else "rgba(15, 23, 42, 0.30)",
        "primary": primary,
        "primary_hover": primary_hover,
        "primary_active": primary_active,
        "primary_soft": primary_soft,
        "primary_border": primary_hover,
        "primary_text": "#0F172A" if mode == "dark" else "#FFFFFF",
        "primary_shadow": primary_shadow,
        "accent": accent,
        "accent_hover": accent_hover,
        "accent_soft": accent_soft,
        "accent_text": "#0F172A" if mode == "dark" else "#0F766E",
        "profit": profit,
        "profit_soft": profit_soft,
        "profit_text": profit_text,
        "profit_border": _transparent(profit, 0.36),
        "loss": loss,
        "loss_soft": loss_soft,
        "loss_text": loss_text,
        "loss_border": _transparent(loss, 0.36),
        "neutral_value": neutral_value,
        "neutral_value_soft": _transparent(neutral_value, 0.16 if mode == "dark" else 0.14),
        "success": success,
        "success_soft": success_soft,
        "success_text": success_text,
        "warning": warning,
        "warning_soft": warning_soft,
        "warning_text": warning_text,
        "danger": danger,
        "danger_soft": danger_soft,
        "danger_text": danger_text,
        "info": info,
        "info_soft": info_soft,
        "info_text": info_text,
        "stock": primary,
        "stock_soft": primary_soft,
        "cash": cash,
        "cash_soft": cash_soft,
        "krw": krw,
        "krw_soft": krw_soft,
        "usd": usd,
        "usd_soft": usd_soft,
        "chart_grid": _transparent(text_subtle, 0.18),
        "chart_axis": text_muted,
        "chart_text": text,
        "chart_tooltip_bg": "#111827" if mode == "light" else "#0B1220",
        "chart_tooltip_text": "#F8FAFC",
        "chart_palette_primary": "|".join([primary, primary_hover, primary_active, accent, cash, text_subtle]),
        "chart_palette_allocation": "|".join([primary, primary_hover, primary_active, accent, cash, usd, text_subtle, border_strong]),
        "chart_palette_diverging": "|".join([profit, neutral_value, loss]),
        "chart_palette_status": "|".join([success, warning, danger, info, neutral_value]),
        "button_primary_bg": primary,
        "button_primary_text": "#0F172A" if mode == "dark" else "#FFFFFF",
        "button_secondary_bg": surface_raised,
        "button_secondary_text": text,
        "button_secondary_border": border,
        "button_danger_bg": danger,
        "button_danger_text": "#FFFFFF",
        "tab_active": primary,
        "tab_inactive": text_muted,
        "tab_border": border,
        "card_bg": surface,
        "card_border": border,
        "card_shadow": shadow,
        "table_header_bg": surface_raised,
        "table_header_text": text,
        "table_row_bg": surface,
        "table_row_alt_bg": surface_raised,
        "table_text": text,
        "input_bg": surface,
        "input_text": text,
        "input_border": border if mode == "light" else border_strong,
        "input_focus": primary,
        "badge_bg": surface_raised,
        "badge_text": text,
        "summary_card_bg": summary_card_bg,
        "summary_panel_bg": summary_panel_bg,
        "summary_heatmap_bg": summary_heatmap_bg,
        "summary_heatmap_border": summary_heatmap_border,
        "summary_heatmap_tile_border": summary_heatmap_tile_border,
        "space_0": "0",
        "space_1": "4px",
        "space_2": "8px",
        "space_3": "12px",
        "space_4": "16px",
        "space_5": "20px",
        "space_6": "24px",
        "space_8": "32px",
        "space_10": "40px",
        "space_12": "48px",
        "radius_sm": "6px",
        "radius_md": "10px",
        "radius_lg": "14px",
        "radius_xl": "18px",
        "radius_pill": "999px",
        "font_xs": "11px",
        "font_sm": "12px",
        "font_base": "14px",
        "font_md": "15px",
        "font_lg": "18px",
        "font_xl": "22px",
        "font_2xl": "28px",
        "font_3xl": "36px",
        "line_height_tight": "1.2",
        "line_height_normal": "1.45",
        "line_height_loose": "1.65",
        "control_height_sm": "32px",
        "control_height_md": "40px",
        "control_height_lg": "48px",
        "button_height_sm": "32px",
        "button_height_md": "40px",
        "button_height_lg": "44px",
        "input_height_md": "40px",
        "tab_height": "42px",
        "subtab_height": "38px",
        "page_max_width": "1240px",
        "page_padding_x_desktop": "32px",
        "page_padding_x_tablet": "24px",
        "page_padding_x_mobile": "16px",
        "section_gap": "28px",
        "card_gap": "16px",
        "card_padding": "18px",
        "card_padding_compact": "14px",
        "table_min_row_height": "40px",
        "table_compact_row_height": "34px",
        "chart_height_sm": "300px",
        "chart_height_md": "380px",
        "chart_height_lg": "460px",
    }
    return values


APP_THEMES = {
    "light": AppTheme(
        "light",
        _theme_values(
            mode="light",
            bg="#F6F8FC",
            bg_subtle="linear-gradient(180deg, #F6F8FC 0%, #EEF3FA 100%)",
            surface="#FFFFFF",
            surface_raised="#F8FAFC",
            surface_sunken="#EEF3FA",
            surface_hover="#F1F5F9",
            text="#0F172A",
            text_muted="#475569",
            text_subtle="#64748B",
            border="#E2E8F0",
            border_strong="#CBD5E1",
            primary="#2563EB",
            primary_hover="#1D4ED8",
            primary_active="#1E40AF",
            primary_soft="#DBEAFE",
            accent="#14B8A6",
            accent_hover="#0F766E",
            accent_soft="#CCFBF1",
            profit="#E11D48",
            profit_soft="#FFE4E6",
            profit_text="#9F1239",
            loss="#0284C7",
            loss_soft="#E0F2FE",
            loss_text="#075985",
            success="#059669",
            success_soft="#D1FAE5",
            success_text="#047857",
            warning="#D97706",
            warning_soft="#FEF3C7",
            warning_text="#92400E",
            danger="#DC2626",
            danger_soft="#FEE2E2",
            danger_text="#991B1B",
            info="#2563EB",
            info_soft="#DBEAFE",
            info_text="#1D4ED8",
            cash="#64748B",
            cash_soft="#F1F5F9",
            krw="#334155",
            krw_soft="#E2E8F0",
            usd="#4F46E5",
            usd_soft="#E0E7FF",
            shadow="0 16px 40px rgba(15, 23, 42, 0.08)",
            shadow_sm="0 8px 20px rgba(15, 23, 42, 0.06)",
            primary_shadow="0 10px 22px rgba(37, 99, 235, 0.18)",
            summary_card_bg="linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 52%, #EEF3FA 100%)",
            summary_panel_bg="linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98))",
            summary_heatmap_bg="#E2E8F0",
            summary_heatmap_border="#CBD5E1",
            summary_heatmap_tile_border="rgba(255, 255, 255, 0.94)",
        ),
    ),
    "dark": AppTheme(
        "dark",
        _theme_values(
            mode="dark",
            bg="#0B1220",
            bg_subtle="linear-gradient(180deg, #0B1220 0%, #0F172A 100%)",
            surface="#111827",
            surface_raised="#172033",
            surface_sunken="#0B1220",
            surface_hover="#1E293B",
            text="#E5E7EB",
            text_muted="#CBD5E1",
            text_subtle="#94A3B8",
            border="#263244",
            border_strong="#334155",
            primary="#60A5FA",
            primary_hover="#3B82F6",
            primary_active="#2563EB",
            primary_soft="rgba(96, 165, 250, 0.16)",
            accent="#2DD4BF",
            accent_hover="#14B8A6",
            accent_soft="rgba(45, 212, 191, 0.14)",
            profit="#FB7185",
            profit_soft="rgba(251, 113, 133, 0.14)",
            profit_text="#FDA4AF",
            loss="#38BDF8",
            loss_soft="rgba(56, 189, 248, 0.14)",
            loss_text="#7DD3FC",
            success="#34D399",
            success_soft="rgba(52, 211, 153, 0.14)",
            success_text="#6EE7B7",
            warning="#FBBF24",
            warning_soft="rgba(251, 191, 36, 0.15)",
            warning_text="#FCD34D",
            danger="#F87171",
            danger_soft="rgba(248, 113, 113, 0.14)",
            danger_text="#FCA5A5",
            info="#60A5FA",
            info_soft="rgba(96, 165, 250, 0.14)",
            info_text="#93C5FD",
            cash="#CBD5E1",
            cash_soft="rgba(148, 163, 184, 0.12)",
            krw="#CBD5E1",
            krw_soft="rgba(203, 213, 225, 0.12)",
            usd="#A5B4FC",
            usd_soft="rgba(165, 180, 252, 0.14)",
            shadow="0 18px 48px rgba(2, 8, 23, 0.38)",
            shadow_sm="0 10px 28px rgba(2, 8, 23, 0.28)",
            primary_shadow="0 10px 24px rgba(59, 130, 246, 0.20)",
            summary_card_bg="linear-gradient(135deg, #0B1220 0%, #0F172A 56%, #111827 100%)",
            summary_panel_bg="linear-gradient(180deg, rgba(23, 32, 51, 0.94), rgba(15, 23, 42, 0.94))",
            summary_heatmap_bg="#0B1220",
            summary_heatmap_border="#020617",
            summary_heatmap_tile_border="#020617",
        ),
    ),
}


REQUIRED_THEME_TOKEN_KEYS = set(next(iter(APP_THEMES.values())).tokens())


def normalize_theme_mode(value: object | None) -> str:
    mode = str(value or DEFAULT_THEME_MODE).strip().lower()
    return mode if mode in APP_THEMES else DEFAULT_THEME_MODE


def get_theme_mode() -> str:
    try:
        import streamlit as st

        return normalize_theme_mode(st.session_state.get(APP_THEME_KEY, DEFAULT_THEME_MODE))
    except Exception:
        return DEFAULT_THEME_MODE


def get_app_theme(mode: object | None = None) -> AppTheme:
    return APP_THEMES[normalize_theme_mode(mode)]


def get_theme_tokens(mode: str) -> dict[str, str]:
    theme = get_app_theme(mode)
    tokens = theme.tokens()
    assert_theme_tokens(tokens)
    return tokens


def theme_tokens(mode: object | None = None) -> dict[str, str]:
    return get_theme_tokens(normalize_theme_mode(mode))


def get_active_theme() -> AppTheme:
    return get_app_theme(get_theme_mode())


def assert_theme_tokens(tokens: dict[str, str]) -> None:
    missing = REQUIRED_THEME_TOKEN_KEYS - set(tokens)
    if missing:
        raise ValueError(f"missing theme tokens: {', '.join(sorted(missing))}")
    empty = [key for key, value in tokens.items() if value in (None, "")]
    if empty:
        raise ValueError(f"empty theme tokens: {', '.join(sorted(empty))}")


def inject_theme_css(tokens: dict[str, str]) -> None:
    assert_theme_tokens(tokens)
    try:
        import streamlit as st
    except Exception:
        return
    css = "\n".join(f"            --token-{key.replace('_', '-')}: {value};" for key, value in tokens.items())
    st.markdown(f"<style>:root {{\n{css}\n}}</style>", unsafe_allow_html=True)


def _split_palette(value: str) -> list[str]:
    return [color for color in value.split("|") if color]


def get_chart_palette(tokens: dict[str, str], kind: str = "default") -> list[str]:
    assert_theme_tokens(tokens)
    key = {
        "default": "chart_palette_primary",
        "primary": "chart_palette_primary",
        "allocation": "chart_palette_allocation",
        "diverging": "chart_palette_diverging",
        "status": "chart_palette_status",
    }.get(kind, "chart_palette_primary")
    return _split_palette(tokens[key])


def get_pnl_color(value: float | None, tokens: dict[str, str], *, mode: str = PNL_COLOR_MODE) -> str:
    del mode
    if value is None:
        return tokens["neutral_value"]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return tokens["neutral_value"]
    if not math.isfinite(number) or number == 0:
        return tokens["neutral_value"]
    return tokens["profit"] if number > 0 else tokens["loss"]


def get_status_color(status: str, tokens: dict[str, str]) -> dict[str, str]:
    normalized = str(status or "neutral").strip().lower()
    mapping = {
        "success": ("success", "success_soft", "success_text"),
        "updated": ("success", "success_soft", "success_text"),
        "ok": ("success", "success_soft", "success_text"),
        "warning": ("warning", "warning_soft", "warning_text"),
        "stale": ("warning", "warning_soft", "warning_text"),
        "danger": ("danger", "danger_soft", "danger_text"),
        "error": ("danger", "danger_soft", "danger_text"),
        "failed": ("danger", "danger_soft", "danger_text"),
        "info": ("info", "info_soft", "info_text"),
        "cached": ("info", "info_soft", "info_text"),
    }
    color_key, bg_key, text_key = mapping.get(normalized, ("neutral_value", "neutral_value_soft", "text_muted"))
    return {"color": tokens[color_key], "background": tokens[bg_key], "text": tokens[text_key]}


@dataclass(frozen=True)
class ChartDimensions:
    compact_height: int = 300
    default_height: int = 380
    tall_height: int = 460
    row_height: int = 40
    compact_row_height: int = 34
    max_table_height: int = 480


DIMENSIONS = ChartDimensions()


SEMANTIC_COLORS = {
    "positive": APP_THEMES[DEFAULT_THEME_MODE].tokens()["profit"],
    "profit": APP_THEMES[DEFAULT_THEME_MODE].tokens()["profit"],
    "negative": APP_THEMES[DEFAULT_THEME_MODE].tokens()["loss"],
    "loss": APP_THEMES[DEFAULT_THEME_MODE].tokens()["loss"],
    "neutral": APP_THEMES[DEFAULT_THEME_MODE].tokens()["neutral_value"],
    "primary": APP_THEMES[DEFAULT_THEME_MODE].tokens()["primary"],
    "secondary": APP_THEMES[DEFAULT_THEME_MODE].tokens()["accent"],
    "accent": APP_THEMES[DEFAULT_THEME_MODE].tokens()["accent"],
    "success": APP_THEMES[DEFAULT_THEME_MODE].tokens()["success"],
    "warning": APP_THEMES[DEFAULT_THEME_MODE].tokens()["warning"],
    "danger": APP_THEMES[DEFAULT_THEME_MODE].tokens()["danger"],
    "cash": APP_THEMES[DEFAULT_THEME_MODE].tokens()["cash"],
    "missing": APP_THEMES[DEFAULT_THEME_MODE].tokens()["text_subtle"],
    "surface": APP_THEMES[DEFAULT_THEME_MODE].tokens()["surface"],
    "ink": APP_THEMES[DEFAULT_THEME_MODE].tokens()["text"],
}

CATEGORY_COLORS = get_chart_palette(APP_THEMES[DEFAULT_THEME_MODE].tokens(), "allocation")

CURRENCY_COLORS = {
    "KRW": APP_THEMES[DEFAULT_THEME_MODE].tokens()["krw"],
    "USD": APP_THEMES[DEFAULT_THEME_MODE].tokens()["usd"],
    "CASH": APP_THEMES[DEFAULT_THEME_MODE].tokens()["cash"],
}

STATUS_COLORS = {
    "updated": APP_THEMES[DEFAULT_THEME_MODE].tokens()["success"],
    "cached": APP_THEMES[DEFAULT_THEME_MODE].tokens()["info"],
    "stale": APP_THEMES[DEFAULT_THEME_MODE].tokens()["warning"],
    "failed": APP_THEMES[DEFAULT_THEME_MODE].tokens()["danger"],
    "missing": APP_THEMES[DEFAULT_THEME_MODE].tokens()["text_subtle"],
    "missing_api_key": APP_THEMES[DEFAULT_THEME_MODE].tokens()["text_subtle"],
    "manual": APP_THEMES[DEFAULT_THEME_MODE].tokens()["neutral_value"],
}


def deterministic_color(key: object, palette: Iterable[str] = CATEGORY_COLORS) -> str:
    colors = list(palette)
    if not colors:
        raise ValueError("palette must contain at least one color")
    digest = hashlib.sha256(str(key).upper().encode("utf-8")).hexdigest()
    return colors[int(digest[:8], 16) % len(colors)]


def signed_color(value: float | None) -> str:
    return get_pnl_color(value, get_active_theme().tokens())


def status_color(status: object) -> str:
    return get_status_color(str(status or ""), get_active_theme().tokens())["color"]


def chart_config() -> dict[str, object]:
    return {
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    }
