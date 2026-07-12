from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date, datetime
from html import escape
from typing import Any

import streamlit as st

from portfolio.holdings import PortfolioMetrics
from portfolio.market_indices import DEFAULT_MARKET_WARNING_SPECS, MarketIndexQuote, MarketWarningSignal
from portfolio.transactions import normalize_transaction_rows

from .components import render_empty_state
from .formatters import KST, format_kst, format_number, format_price, instrument_label, percentage, signed_krw, signed_percentage
from .theme import SEMANTIC_COLORS, get_active_theme


_SECTOR_BY_TICKER = {
    "000660": "반도체·전자",
    "005930": "반도체·전자",
    "005935": "반도체·전자",
    "009540": "조선·산업재",
    "071050": "금융",
    "239890": "디스플레이 소재",
    "AYA": "귀금속·광업",
    "AVR": "바이오·헬스케어",
    "CCCC": "바이오·헬스케어",
    "CGEM": "바이오·헬스케어",
    "CMPS": "바이오·헬스케어",
    "CTMX": "바이오·헬스케어",
    "EXK": "귀금속·광업",
    "GHRS": "바이오·헬스케어",
    "MAKO": "귀금속·광업",
    "PSNL": "바이오·헬스케어",
    "QURE": "바이오·헬스케어",
    "VOR": "바이오·헬스케어",
}

_SECTOR_BY_NAME = {
    "HD한국조선해양": "조선·산업재",
    "SK하이닉스": "반도체·전자",
    "삼성전자": "반도체·전자",
    "삼성전자우": "반도체·전자",
    "삼성전자우선주": "반도체·전자",
    "피엔에이치테크": "디스플레이 소재",
    "한국금융지주": "금융",
}


def _krw(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{format_number(value)}원"


def _display_date(value: object) -> str:
    text = format_kst(value)
    if text == "미조회":
        return datetime.now(KST).strftime("%Y.%m.%d")
    try:
        parsed = datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
        return parsed.strftime("%Y.%m.%d")
    except ValueError:
        return text[:10].replace("-", ".")


def _signed_class(value: float | None) -> str:
    if value is None or value == 0:
        return "summary-neutral"
    return "summary-up" if value > 0 else "summary-down"


def _movement_dot_color(change: float | None) -> str:
    tokens = get_active_theme().tokens()
    if change is None or abs(change) < 1e-12:
        return tokens["neutral_value"]
    return tokens["profit"] if change > 0 else tokens["loss"]


def _signed_text(value: float | None, formatter) -> str:
    if value is None:
        return "-"
    return formatter(value)


def _kpi_tone(value: float | None) -> str:
    if value is None or value == 0:
        return "default"
    return "red" if value > 0 else "blue"


def _mix_hex(start: str, end: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(f"{round(a + (b - a) * ratio):02X}" for a, b in zip(start_rgb, end_rgb))


def _sort_key(row: dict[str, Any]) -> float:
    return float(row.get("value_krw") or 0)


def _holding_day_change_pct(item) -> float | None:
    holding = item.holding
    current_price = holding.get("current_price")
    previous_close = holding.get("previous_close")
    if current_price is None or previous_close is None:
        return None
    previous_value = float(previous_close)
    if previous_value <= 0:
        return None
    return (float(current_price) - previous_value) / previous_value


def _holding_day_change_price(holding: dict[str, Any]) -> float | None:
    current_price = holding.get("current_price")
    previous_close = holding.get("previous_close")
    if current_price is None or previous_close is None:
        return None
    return float(current_price) - float(previous_close)


def _signed_price(value: float, currency: object) -> str:
    if value == 0:
        return format_price(0.0, currency)
    sign = "+" if value > 0 else "-"
    return f"{sign}{format_price(abs(value), currency)}"


def _currency_label(value: object) -> str:
    currency = str(value or "").upper()
    return currency if currency in {"KRW", "USD"} else "-"


def _market_code(holding: Mapping[str, Any]) -> str:
    market = str(holding.get("market") or "").strip().upper()
    if market in {"KR", "KOSPI", "KOSDAQ"}:
        return "KR"
    if market in {"US", "NASDAQ", "NYSE", "AMEX"}:
        return "US"
    currency = _currency_label(holding.get("currency"))
    if currency == "KRW":
        return "KR"
    if currency == "USD":
        return "US"
    return market[:2] or "-"


def _holding_sector(holding: Mapping[str, Any]) -> str:
    explicit_sector = str(holding.get("sector") or holding.get("sector_name") or "").strip()
    if explicit_sector:
        return explicit_sector
    ticker = str(holding.get("ticker") or holding.get("symbol") or "").strip().upper()
    if ticker in _SECTOR_BY_TICKER:
        return _SECTOR_BY_TICKER[ticker]
    display_name = str(holding.get("display_name") or holding.get("name") or "").strip()
    return _SECTOR_BY_NAME.get(display_name, "기타")


def _currency_badge(value: object) -> str:
    label = _currency_label(value)
    if label == "-":
        return ""
    return f"<span class='summary-currency-badge summary-currency-{label.lower()}'>{escape(label)}</span>"


def _holding_native_value(holding: dict[str, Any]) -> float | None:
    current_price = holding.get("current_price")
    if current_price is None:
        return None
    return float(current_price) * float(holding.get("quantity") or 0.0)


def _holding_allocation_detail(holding: dict[str, Any], value_krw: float) -> str:
    currency = _currency_label(holding.get("currency"))
    native_value = _holding_native_value(holding)
    if currency == "USD" and native_value is not None:
        return f"달러 {format_number(native_value, digits=1, trim=True)}$ • 환산 {_krw(value_krw)}"
    if currency == "KRW":
        return f"평가액 {_krw(value_krw)}"
    return f"환산 {_krw(value_krw)}"


def _mobile_price(value: object, currency: object) -> str:
    if value is None:
        return "-"
    currency_label = _currency_label(currency)
    if currency_label == "KRW":
        return f"₩{format_number(float(value), digits=0)}"
    if currency_label == "USD":
        return f"${format_number(float(value), digits=1, trim=True)}"
    return format_number(float(value), digits=1, trim=True)


def _price_change_text(holding: dict[str, Any]) -> str:
    change = _holding_day_change_price(holding)
    pct = None
    previous_close = holding.get("previous_close")
    if change is not None and previous_close is not None and float(previous_close) > 0:
        pct = change / float(previous_close)
    if change is None:
        return "-"
    return f"{_signed_price(change, holding.get('currency'))} ({signed_percentage(pct) if pct is not None else '-'})"


def _badge_html(value: float | None, text: str) -> str:
    return f"<span class='summary-badge {_signed_class(value)}'>{escape(text)}</span>"


def _plain_metric_html(value: float | None, text: str) -> str:
    return f"<span class='summary-plain-metric {_signed_class(value)}'>{escape(text)}</span>"


def _signed_krw_delta_html(value: float | None) -> str:
    if value is None:
        return "<span class='summary-pnl-delta summary-neutral'>-</span>"
    if value == 0:
        return f"<span class='summary-pnl-delta summary-neutral'>{escape(_krw(0.0))}</span>"
    icon = "▲" if value > 0 else "▼"
    return f"<span class='summary-pnl-delta {_signed_class(value)}'>{icon} {escape(_krw(abs(value)))}</span>"


def _price_amount_group_html(
    *,
    avg_price: str,
    purchase_amount_krw: str,
    current_price: str,
    market_value_krw: str,
    current_tone: str,
) -> str:
    return (
        "<div class='summary-price-group'>"
        "<div class='summary-price-stack'>"
        f"<span class='summary-price-main'>{escape(avg_price)}</span>"
        f"<span class='summary-price-sub'>{escape(purchase_amount_krw)}</span>"
        "</div>"
        "<div class='summary-price-stack'>"
        f"<span class='summary-price-main summary-current-price {current_tone}'>{escape(current_price)}</span>"
        f"<span class='summary-price-sub summary-market-value'>{escape(market_value_krw)}</span>"
        "</div>"
        "</div>"
    )


def _pnl_stack_html(total_pnl_pct: float | None, total_pnl_krw: float | None) -> str:
    pct_text = signed_percentage(total_pnl_pct) if total_pnl_pct is not None else "-"
    tone = _signed_class(total_pnl_pct if total_pnl_pct is not None else total_pnl_krw)
    return (
        f"<div class='summary-pnl-stack {tone}'>"
        f"<span class='summary-pnl-rate'>{escape(pct_text)}</span>"
        f"{_signed_krw_delta_html(total_pnl_krw)}"
        "</div>"
    )


def _intraday_price_values(holding: dict[str, Any]) -> list[float]:
    raw_values = holding.get("intraday_prices") or []
    if not isinstance(raw_values, (list, tuple)):
        return []
    values = []
    for value in raw_values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number >= 0:
            values.append(number)
    return values


def _sparkline_points(values: list[float], *, width: int = 86, height: int = 26, padding: int = 3) -> str:
    if len(values) < 2:
        return ""
    min_value = min(values)
    max_value = max(values)
    spread = max_value - min_value
    x_step = (width - padding * 2) / (len(values) - 1)
    points = []
    for index, value in enumerate(values):
        x = padding + index * x_step
        y = height / 2 if spread == 0 else padding + (max_value - value) / spread * (height - padding * 2)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _sparkline_html(holding: dict[str, Any]) -> str:
    values = _intraday_price_values(holding)
    if len(values) < 2:
        return "<div class='summary-sparkline summary-sparkline-empty' title='당일 분봉 데이터 없음'></div>"
    first = values[0]
    last = values[-1]
    tone = "up" if last > first else "down" if last < first else "neutral"
    volatility = (max(values) - min(values)) / first if first else 0.0
    title = f"당일 분봉 {len(values)}개 · 변동폭 {percentage(volatility, digits=2)}"
    points = _sparkline_points(values)
    end_x, end_y = points.split()[-1].split(",")
    return (
        f"<div class='summary-sparkline summary-sparkline-{tone}' title='{escape(title)}'>"
        "<svg viewBox='0 0 86 26' aria-hidden='true' focusable='false'>"
        "<line x1='3' y1='13' x2='83' y2='13' class='summary-sparkline-baseline'></line>"
        f"<polyline points='{points}'></polyline>"
        f"<circle cx='{end_x}' cy='{end_y}' r='2.2'></circle>"
        "</svg>"
        "</div>"
    )


def _heatmap_tone(change_pct: float | None) -> str:
    tokens = get_active_theme().tokens()
    if change_pct is None or abs(change_pct) < 1e-12:
        return tokens["neutral_value"]
    intensity = 0.42 + min(abs(change_pct) / 0.035, 1.0) * 0.58
    base = tokens["surface_raised"]
    if change_pct > 0:
        return _mix_hex(base, tokens["profit"], intensity)
    return _mix_hex(base, tokens["loss"], intensity)


def _font_size_for_weight(weight: float) -> float:
    return max(0.58, min(1.85, 0.58 + math.sqrt(max(weight, 0.0)) * 2.0))


def _safe_date(value: object | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _as_of_date(last_refresh: object = None) -> date:
    return _safe_date(last_refresh) or datetime.now(KST).date()


def _xnpv(rate: float, cashflows: list[tuple[date, float]]) -> float:
    base_date = min(day for day, _ in cashflows)
    return sum(amount / ((1.0 + rate) ** ((day - base_date).days / 365.25)) for day, amount in cashflows)


def _xirr(cashflows: list[tuple[date, float]]) -> float | None:
    if len(cashflows) < 2:
        return None
    amounts = [amount for _, amount in cashflows]
    if not any(amount < 0 for amount in amounts) or not any(amount > 0 for amount in amounts):
        return None
    if len({day for day, _ in cashflows}) < 2:
        return None

    low = -0.9999
    high = 10.0
    low_value = _xnpv(low, cashflows)
    high_value = _xnpv(high, cashflows)
    while low_value * high_value > 0 and high < 1_000:
        high *= 2
        high_value = _xnpv(high, cashflows)
    if low_value * high_value > 0:
        return None

    for _ in range(90):
        mid = (low + high) / 2
        mid_value = _xnpv(mid, cashflows)
        if abs(mid_value) < 1e-7:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2


def _normalized_transactions(transactions: list[dict[str, Any]] | None) -> list[dict[str, object]]:
    if not transactions:
        return []
    try:
        return normalize_transaction_rows(transactions)
    except ValueError:
        return []


def _holding_irr(
    holding: dict[str, Any],
    transactions: list[dict[str, object]],
    *,
    as_of_date: date,
) -> float | None:
    ticker = str(holding.get("ticker") or holding.get("symbol") or "")
    market = str(holding.get("market") or "")
    current_price = holding.get("current_price")
    quantity = float(holding.get("quantity") or 0.0)
    if not ticker or not market or current_price is None or quantity <= 0:
        return None

    cashflows: list[tuple[date, float]] = []
    for transaction in transactions:
        if str(transaction.get("ticker")) != ticker or str(transaction.get("market")) != market:
            continue
        occurred_at = _safe_date(transaction.get("occurred_at"))
        if occurred_at is None:
            continue
        amount = float(transaction.get("unit_price") or 0.0) * float(transaction.get("quantity") or 0.0)
        if amount <= 0:
            continue
        cashflows.append((occurred_at, -amount if transaction.get("transaction_type") == "buy" else amount))
    cashflows.append((as_of_date, float(current_price) * quantity))
    return _xirr(cashflows)


def _portfolio_irr(metrics: PortfolioMetrics, transactions: list[dict[str, object]], *, as_of_date: date) -> float | None:
    if not transactions or metrics.total_position_value_krw <= 0:
        return None
    cashflows: list[tuple[date, float]] = []
    for transaction in transactions:
        occurred_at = _safe_date(transaction.get("occurred_at"))
        if occurred_at is None:
            continue
        fx_rate = 1.0 if transaction.get("currency") == "KRW" else metrics.usd_krw
        amount = float(transaction.get("unit_price") or 0.0) * float(transaction.get("quantity") or 0.0) * fx_rate
        if amount <= 0:
            continue
        cashflows.append((occurred_at, -amount if transaction.get("transaction_type") == "buy" else amount))
    cashflows.append((as_of_date, metrics.total_position_value_krw))
    return _xirr(cashflows)


def _holding_allocation_rows(metrics: PortfolioMetrics) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = metrics.total_value_krw
    for item in metrics.rows:
        value = item.market_value_krw
        if value is None or value <= 0:
            continue
        day_change_pct = _holding_day_change_pct(item)
        rows.append(
            {
                "label": instrument_label(item.holding),
                "detail": instrument_label(item.holding, include_ticker=True),
                "value_krw": value,
                "weight": value / total if total else 0.0,
                "color": _movement_dot_color(day_change_pct),
                "heat_color": _heatmap_tone(day_change_pct),
                "day_change_pct": day_change_pct,
                "day_change_krw": item.day_change_krw,
                "kind": "holding",
                "currency": _currency_label(item.holding.get("currency")),
                "market_code": _market_code(item.holding),
                "compact_label": str(item.holding.get("ticker") or item.holding.get("symbol") or instrument_label(item.holding)),
                "sector": _holding_sector(item.holding),
                "allocation_detail": _holding_allocation_detail(item.holding, float(value)),
            }
        )
    return sorted(rows, key=_sort_key, reverse=True)


def _allocation_rows(metrics: PortfolioMetrics, *, max_items: int = 3) -> list[dict[str, Any]]:
    rows = _holding_allocation_rows(metrics)
    total = metrics.total_value_krw
    if len(rows) <= max_items:
        return rows
    kept = rows[:max_items]
    other = rows[max_items:]
    other_value = sum(float(row["value_krw"]) for row in other)
    other_day_change_krw = sum(float(row.get("day_change_krw") or 0.0) for row in other)
    other_previous_value = other_value - other_day_change_krw
    other_day_change_pct = other_day_change_krw / other_previous_value if other_previous_value else None
    kept.append(
        {
            "label": f"그 외 {len(other)}종목",
            "detail": f"{len(other)}개 종목 합산",
            "value_krw": other_value,
            "weight": other_value / total if total else 0.0,
            "color": _movement_dot_color(other_day_change_pct),
            "heat_color": _heatmap_tone(other_day_change_pct),
            "day_change_pct": other_day_change_pct,
            "day_change_krw": other_day_change_krw,
            "kind": "other",
            "currency": "-",
            "allocation_detail": f"{len(other)}개 종목 합산 • 환산 {_krw(other_value)}",
        }
    )
    return kept


def _cash_allocation_rows(metrics: PortfolioMetrics) -> list[dict[str, Any]]:
    if metrics.cash_total_krw <= 0:
        return []
    tokens = get_active_theme().tokens()
    total = metrics.total_value_krw
    rows: list[dict[str, Any]] = []
    if metrics.cash.cash_krw > 0:
        rows.append(
            {
                "label": "원화 현금",
                "detail": _krw(metrics.cash.cash_krw),
                "value_krw": metrics.cash.cash_krw,
                "weight": metrics.cash.cash_krw / total if total else 0.0,
                "color": tokens["krw"],
                "kind": "cash",
                "currency": "KRW",
            }
        )
    if metrics.cash.cash_usd > 0:
        cash_usd_krw = metrics.cash.cash_usd * metrics.usd_krw
        rows.append(
            {
                "label": "달러 현금",
                "detail": f"{format_price(metrics.cash.cash_usd, 'USD')} · 환산 {_krw(cash_usd_krw)}",
                "value_krw": cash_usd_krw,
                "weight": cash_usd_krw / total if total else 0.0,
                "color": tokens["usd"],
                "kind": "cash",
                "currency": "USD",
            }
        )
    return rows


def _cash_allocation_row(metrics: PortfolioMetrics) -> dict[str, Any] | None:
    rows = _cash_allocation_rows(metrics)
    if not rows:
        return None
    tokens = get_active_theme().tokens()
    total = metrics.total_value_krw
    return {
        "label": "현금",
        "detail": "KRW/USD 현금",
        "value_krw": metrics.cash_total_krw,
        "weight": metrics.cash_total_krw / total if total else 0.0,
        "color": tokens["cash"],
        "kind": "cash",
        "currency": "-",
    }


def _currency_totals(metrics: PortfolioMetrics) -> dict[str, dict[str, float]]:
    totals = {
        "investment": {"KRW": 0.0, "USD": 0.0},
        "cash": {"KRW": metrics.cash.cash_krw, "USD": metrics.cash.cash_usd * metrics.usd_krw},
    }
    for item in metrics.rows:
        currency = _currency_label(item.holding.get("currency"))
        if currency in {"KRW", "USD"} and item.market_value_krw:
            totals["investment"][currency] += float(item.market_value_krw)
    return totals


def _currency_split_text(values: dict[str, float], total: float) -> str:
    parts = []
    for currency in ("KRW", "USD"):
        value = float(values.get(currency) or 0.0)
        if value <= 0:
            continue
        parts.append(f"{currency} {percentage(value / total if total else 0.0, digits=1)}")
    return " · ".join(parts) if parts else "KRW/USD 없음"


def _split_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total = sum(float(row["value_krw"]) for row in rows)
    cursor = 0.0
    split_index = 1
    for index, row in enumerate(rows[:-1], start=1):
        cursor += float(row["value_krw"])
        if cursor >= total / 2:
            split_index = index
            break
    return rows[:split_index], rows[split_index:]


def _treemap_layout(
    rows: list[dict[str, Any]],
    *,
    x: float = 0.0,
    y: float = 0.0,
    width: float = 100.0,
    height: float = 100.0,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if len(rows) == 1:
        row = dict(rows[0])
        row.update({"x": x, "y": y, "width": width, "height": height})
        return [row]

    first, second = _split_rows(rows)
    first_value = sum(float(row["value_krw"]) for row in first)
    total_value = first_value + sum(float(row["value_krw"]) for row in second)
    first_ratio = first_value / total_value if total_value else 0.5
    if width >= height:
        first_width = width * first_ratio
        return _treemap_layout(first, x=x, y=y, width=first_width, height=height) + _treemap_layout(
            second,
            x=x + first_width,
            y=y,
            width=width - first_width,
            height=height,
        )
    first_height = height * first_ratio
    return _treemap_layout(first, x=x, y=y, width=width, height=first_height) + _treemap_layout(
        second,
        x=x,
        y=y + first_height,
        width=width,
        height=height - first_height,
    )


def _heatmap_tiles(
    rows: list[dict[str, Any]],
    *,
    aspect_ratio: float = 1.0,
    balanced: bool = False,
) -> str:
    tiles = []
    safe_aspect_ratio = max(float(aspect_ratio), 0.1)
    canvas_height = 100.0 / safe_aspect_ratio
    layout_function = _balanced_treemap_layout if balanced else _treemap_layout
    positioned_rows = layout_function(rows, width=100.0, height=canvas_height)
    for positioned in positioned_rows:
        row = {
            **positioned,
            "y": float(positioned["y"]) / canvas_height * 100.0,
            "height": float(positioned["height"]) / canvas_height * 100.0,
        }
        weight = float(row.get("weight") or 0.0)
        change_pct = row.get("day_change_pct")
        change_text = signed_percentage(change_pct) if change_pct is not None else "-"
        font_size = _font_size_for_weight(weight)
        tile_width = float(row.get("width") or 0.0)
        tile_height = float(row.get("height") or 0.0)
        is_small = weight < 0.035 or tile_width < 14 or tile_height < 14
        tile_classes = "summary-heatmap-tile summary-heatmap-small" if is_small else "summary-heatmap-tile"
        market_code = str(row.get("market_code") or "-")
        market_suffix = f" ({market_code})" if market_code != "-" else ""
        title = f"{row['label']}{market_suffix} · {change_text} · 비중 {percentage(weight, digits=2)}"
        if row.get("heatmap_detail"):
            title = f"{title} · {row['heatmap_detail']}"
        market_html = (
            f" <span class='summary-heatmap-market'>({escape(market_code)})</span>" if market_code != "-" else ""
        )
        label_html = f"<div class='summary-heatmap-name'>{escape(str(row['label']))}{market_html}</div>"
        change_html = f"<div class='summary-heatmap-change'>{escape(change_text)}</div>"
        tiles.append(
            f"<div class='{tile_classes}' "
            f"title='{escape(title)}' aria-label='{escape(title)}' "
            f"style='left:{row['x']:.4f}%;top:{row['y']:.4f}%;width:{row['width']:.4f}%;height:{row['height']:.4f}%;"
            f"background:{row['heat_color']};font-size:{font_size:.2f}rem;'>"
            f"{label_html}"
            f"{change_html}"
            "</div>"
        )
    return "".join(tiles) or (
        "<div class='summary-heatmap-empty' "
        f"style='background:{SEMANTIC_COLORS['missing']}'>보유자산 없음</div>"
    )


def _mobile_heatmap_partition(
    rows: list[dict[str, Any]],
    *,
    other_weight_threshold: float = 0.035,
    minimum_individual_items: int = 4,
    maximum_visible_tiles: int = 8,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(rows, key=_sort_key, reverse=True)
    if len(ordered) <= minimum_individual_items:
        return ordered, []
    threshold_count = sum(
        1 for row in ordered if float(row.get("weight") or 0.0) >= other_weight_threshold
    )
    maximum_individual_items = max(minimum_individual_items, maximum_visible_tiles - 1)
    individual_count = min(
        len(ordered),
        maximum_individual_items,
        max(minimum_individual_items, threshold_count),
    )
    grouped_count = len(ordered) - individual_count
    if grouped_count == 1:
        if len(ordered) <= maximum_visible_tiles:
            return ordered, []
        if individual_count > minimum_individual_items:
            individual_count -= 1
    return ordered[:individual_count], ordered[individual_count:]


def _aggregate_heatmap_rows(
    rows: list[dict[str, Any]],
    *,
    label_prefix: str,
    kind: str,
    sector: str,
) -> dict[str, Any] | None:
    if not rows:
        return None
    total_value = sum(float(row.get("value_krw") or 0.0) for row in rows)
    total_change = 0.0
    for row in rows:
        explicit_change = row.get("day_change_krw")
        if explicit_change is not None:
            total_change += float(explicit_change)
            continue
        value = float(row.get("value_krw") or 0.0)
        change_pct = row.get("day_change_pct")
        if change_pct is None or float(change_pct) <= -1.0:
            continue
        previous_value = value / (1.0 + float(change_pct))
        total_change += value - previous_value
    previous_total = total_value - total_change
    change_pct = total_change / previous_total if previous_total > 0 else None
    labels = [str(row.get("compact_label") or row.get("label") or "-") for row in rows]
    market_codes = {str(row.get("market_code") or "-") for row in rows}
    market_code = next(iter(market_codes)) if len(market_codes) == 1 else "-"
    return {
        "label": f"{label_prefix} {len(rows)}종목",
        "compact_label": f"{label_prefix} {len(rows)}",
        "detail": f"{len(rows)}개 소형 비중 종목 합산",
        "heatmap_detail": f"포함 종목: {', '.join(labels)}",
        "value_krw": total_value,
        "weight": sum(float(row.get("weight") or 0.0) for row in rows),
        "color": _movement_dot_color(change_pct),
        "heat_color": _heatmap_tone(change_pct),
        "day_change_pct": change_pct,
        "day_change_krw": total_change,
        "kind": kind,
        "currency": "-",
        "market_code": market_code,
        "sector": sector,
    }


def _mobile_other_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    other_row = _aggregate_heatmap_rows(
        rows,
        label_prefix="그 외",
        kind="other",
        sector="그 외",
    )
    if other_row is not None:
        other_row["compact_label"] = "그 외"
        other_row["market_code"] = "-"
    return other_row


def _desktop_sector_partition(
    rows: list[dict[str, Any]],
    *,
    other_weight_threshold: float = 0.015,
    minimum_individual_items: int = 3,
    maximum_visible_tiles: int = 7,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(rows, key=_sort_key, reverse=True)
    if len(ordered) <= minimum_individual_items:
        return ordered, []
    threshold_count = sum(
        1 for row in ordered if float(row.get("weight") or 0.0) >= other_weight_threshold
    )
    maximum_individual_items = max(minimum_individual_items, maximum_visible_tiles - 1)
    individual_count = min(
        len(ordered),
        maximum_individual_items,
        max(minimum_individual_items, threshold_count),
    )
    grouped_count = len(ordered) - individual_count
    if grouped_count == 1:
        if len(ordered) <= maximum_visible_tiles:
            return ordered, []
        if individual_count > minimum_individual_items:
            individual_count -= 1
    return ordered[:individual_count], ordered[individual_count:]


def _desktop_sector_rows(group: Mapping[str, Any]) -> list[dict[str, Any]]:
    individual_rows, grouped_rows = _desktop_sector_partition(list(group.get("rows") or []))
    other_row = _aggregate_heatmap_rows(
        grouped_rows,
        label_prefix="기타",
        kind="sector_other",
        sector=str(group.get("label") or "기타"),
    )
    return sorted(
        [*individual_rows, *([other_row] if other_row is not None else [])],
        key=_sort_key,
        reverse=True,
    )


def _mobile_heatmap(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return (
            "<div class='summary-mobile-heatmap-layout summary-mobile-heatmap-empty'>"
            "보유자산 없음</div>"
        )
    individual_rows, grouped_rows = _mobile_heatmap_partition(rows)
    other_row = _mobile_other_row(grouped_rows)
    display_rows = sorted(
        [*individual_rows, *([other_row] if other_row is not None else [])],
        key=_sort_key,
        reverse=True,
    )
    return (
        "<div class='summary-mobile-heatmap-layout'>"
        f"<div class='summary-mobile-heatmap-major'>{_heatmap_tiles(display_rows, aspect_ratio=4 / 3, balanced=True)}</div>"
        "</div>"
    )


def _sector_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("sector") or "기타"), []).append(row)
    groups = [
        {
            "label": sector,
            "rows": sorted(sector_rows, key=_sort_key, reverse=True),
            "value_krw": sum(float(row.get("value_krw") or 0.0) for row in sector_rows),
            "weight": sum(float(row.get("weight") or 0.0) for row in sector_rows),
        }
        for sector, sector_rows in grouped.items()
    ]
    return sorted(groups, key=_sort_key, reverse=True)


def _display_sector_groups(rows: list[dict[str, Any]], *, standalone_sector_limit: int = 2) -> list[dict[str, Any]]:
    groups = _sector_groups(rows)
    if len(groups) <= standalone_sector_limit:
        return groups

    standalone = groups[:standalone_sector_limit]
    minor_groups = groups[standalone_sector_limit:]
    other_rows = sorted(
        [row for group in minor_groups for row in group["rows"]],
        key=_sort_key,
        reverse=True,
    )
    other_group = {
        "label": "그 외",
        "rows": other_rows,
        "value_krw": sum(float(group.get("value_krw") or 0.0) for group in minor_groups),
        "weight": sum(float(group.get("weight") or 0.0) for group in minor_groups),
    }
    return [*standalone, other_group]


def _bounded_group_proportions(values: list[float], *, minimum: float) -> list[float]:
    if not values:
        return []
    floor = min(max(minimum, 0.0), 1.0 / len(values))
    positive = [max(float(value), 0.0) for value in values]
    total = sum(positive)
    if total <= 0:
        return [1.0 / len(values)] * len(values)

    result = [0.0] * len(values)
    remaining = set(range(len(values)))
    remaining_space = 1.0
    while remaining:
        remaining_value = sum(positive[index] for index in remaining)
        if remaining_value <= 0:
            equal_share = remaining_space / len(remaining)
            for index in remaining:
                result[index] = equal_share
            break
        below_floor = [
            index
            for index in remaining
            if remaining_space * positive[index] / remaining_value < floor
        ]
        if not below_floor:
            for index in remaining:
                result[index] = remaining_space * positive[index] / remaining_value
            break
        for index in below_floor:
            result[index] = floor
            remaining.remove(index)
            remaining_space -= floor
    return result


def _sector_group_layout(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not groups:
        return []
    minimum_area = 0.18 if len(groups) == 2 else 0.12
    layout_proportions = _bounded_group_proportions(
        [float(group.get("value_krw") or 0.0) for group in groups],
        minimum=minimum_area,
    )
    layout_rows = [
        {**group, "value_krw": proportion, "actual_value_krw": group.get("value_krw")}
        for group, proportion in zip(groups, layout_proportions, strict=True)
    ]
    positioned = _balanced_treemap_layout(layout_rows, width=100.0, height=100.0)
    restored = []
    for group in positioned:
        group["value_krw"] = group.pop("actual_value_krw")
        restored.append(group)
    return restored


def _split_rows_by_balance(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total = sum(max(float(row.get("value_krw") or 0.0), 0.0) for row in rows)
    if total <= 0:
        midpoint = max(1, len(rows) // 2)
        return rows[:midpoint], rows[midpoint:]
    cursor = 0.0
    best_index = 1
    best_distance = float("inf")
    for index, row in enumerate(rows[:-1], start=1):
        cursor += max(float(row.get("value_krw") or 0.0), 0.0)
        distance = abs(total / 2.0 - cursor)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return rows[:best_index], rows[best_index:]


def _balanced_treemap_layout(
    rows: list[dict[str, Any]],
    *,
    x: float = 0.0,
    y: float = 0.0,
    width: float = 100.0,
    height: float = 100.0,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if len(rows) == 1:
        row = dict(rows[0])
        row.update({"x": x, "y": y, "width": width, "height": height})
        return [row]

    first, second = _split_rows_by_balance(rows)
    first_value = sum(max(float(row.get("value_krw") or 0.0), 0.0) for row in first)
    second_value = sum(max(float(row.get("value_krw") or 0.0), 0.0) for row in second)
    total_value = first_value + second_value
    first_ratio = first_value / total_value if total_value > 0 else len(first) / len(rows)
    if width >= height:
        first_width = width * first_ratio
        return _balanced_treemap_layout(first, x=x, y=y, width=first_width, height=height) + _balanced_treemap_layout(
            second,
            x=x + first_width,
            y=y,
            width=width - first_width,
            height=height,
        )
    first_height = height * first_ratio
    return _balanced_treemap_layout(first, x=x, y=y, width=width, height=first_height) + _balanced_treemap_layout(
        second,
        x=x,
        y=y + first_height,
        width=width,
        height=height - first_height,
    )


def _sector_member_layout(rows: list[dict[str, Any]], *, group_width: float, group_height: float) -> list[dict[str, Any]]:
    if len(rows) == 3:
        values = [max(float(row.get("value_krw") or 0.0), 0.0) for row in rows]
        total = sum(values)
        first_ratio = values[0] / total if total > 0 else 1.0 / 3.0
        remaining_total = values[1] + values[2]
        second_ratio = values[1] / remaining_total if remaining_total > 0 else 0.5
        first_width = first_ratio * 100.0
        remaining_width = 100.0 - first_width
        second_height = second_ratio * 100.0
        return [
            {**rows[0], "x": 0.0, "y": 0.0, "width": first_width, "height": 100.0},
            {
                **rows[1],
                "x": first_width,
                "y": 0.0,
                "width": remaining_width,
                "height": second_height,
            },
            {
                **rows[2],
                "x": first_width,
                "y": second_height,
                "width": remaining_width,
                "height": 100.0 - second_height,
            },
        ]

    virtual_width = max(group_width, 1.0) * 10.0
    virtual_height = max(group_height * 2.56 - 30.0, 28.0)
    positioned = _balanced_treemap_layout(rows, width=virtual_width, height=virtual_height)
    return [
        {
            **row,
            "x": float(row["x"]) / virtual_width * 100.0,
            "y": float(row["y"]) / virtual_height * 100.0,
            "width": float(row["width"]) / virtual_width * 100.0,
            "height": float(row["height"]) / virtual_height * 100.0,
        }
        for row in positioned
    ]


def _sector_member_tile(row: dict[str, Any]) -> str:
    weight = float(row.get("weight") or 0.0)
    change_pct = row.get("day_change_pct")
    change_text = signed_percentage(change_pct) if change_pct is not None else "-"
    market_code = str(row.get("market_code") or "-")
    market_suffix = f" ({market_code})" if market_code != "-" else ""
    title = f"{row['label']}{market_suffix} · {change_text} · 비중 {percentage(weight, digits=2)}"
    if row.get("heatmap_detail"):
        title = f"{title} · {row['heatmap_detail']}"
    tile_width = float(row.get("width") or 0.0)
    tile_height = float(row.get("height") or 0.0)
    is_tiny = tile_width < 15.0 or tile_height < 18.0
    is_small = is_tiny or tile_width < 24.0 or tile_height < 29.0
    size_class = " summary-sector-tile-tiny" if is_tiny else " summary-sector-tile-small" if is_small else ""
    aggregate_class = " summary-sector-tile-aggregate" if row.get("kind") == "sector_other" else ""
    tile_class = f"summary-sector-tile{size_class}{aggregate_class}"
    display_label = row.get("compact_label") if is_small else row.get("label")
    market_html = (
        f" <span class='summary-heatmap-market'>({escape(market_code)})</span>"
        if market_code != "-" and not is_small
        else ""
    )
    return (
        f"<div class='{tile_class}' title='{escape(title)}' aria-label='{escape(title)}' "
        f"style='left:{float(row['x']):.4f}%;top:{float(row['y']):.4f}%;"
        f"width:{tile_width:.4f}%;height:{tile_height:.4f}%;background:{row['heat_color']}'>"
        f"<div class='summary-sector-tile-name'>{escape(str(display_label or '-'))}{market_html}</div>"
        f"<div class='summary-sector-tile-change'>{escape(change_text)}</div>"
        f"<div class='summary-sector-tile-weight'>비중 {escape(percentage(weight, digits=2))}</div>"
        "</div>"
    )


def _sector_group_html(group: dict[str, Any]) -> str:
    source_rows = list(group["rows"])
    rows = _desktop_sector_rows(group)
    group_title = (
        f"{group['label']} · 비중 {percentage(float(group['weight']), digits=2)} · "
        + ", ".join(str(row.get("compact_label") or row.get("label") or "-") for row in source_rows)
    )
    positioned = _sector_member_layout(
        rows,
        group_width=float(group.get("width") or 100.0),
        group_height=float(group.get("height") or 100.0),
    )
    tiles = "".join(_sector_member_tile(row) for row in positioned)
    compact_class = " summary-sector-group-compact" if float(group.get("height") or 100.0) < 30.0 else ""
    return (
        f"<section class='summary-sector-group summary-sector-group-major{compact_class}' title='{escape(group_title)}' "
        f"style='left:{float(group['x']):.4f}%;top:{float(group['y']):.4f}%;"
        f"width:{float(group['width']):.4f}%;height:{float(group['height']):.4f}%'>"
        "<div class='summary-sector-group-head'>"
        f"<div class='summary-sector-group-name'><strong>{escape(str(group['label']))}</strong>"
        f"<span>{len(source_rows)}종목</span></div>"
        f"<div class='summary-sector-group-weight'>{escape(percentage(float(group['weight']), digits=2))}</div>"
        "</div>"
        f"<div class='summary-sector-members'>{tiles}</div>"
        "</section>"
    )


def _sector_heatmap(rows: list[dict[str, Any]]) -> str:
    groups = _display_sector_groups(rows)
    if not groups:
        return (
            "<div class='summary-sector-heatmap summary-heatmap-desktop summary-sector-heatmap-empty'>"
            "보유자산 없음</div>"
        )
    parts = "".join(_sector_group_html(group) for group in _sector_group_layout(groups))
    return f"<div class='summary-sector-heatmap summary-heatmap-desktop'>{parts}</div>"


def _market_index_value(value: object) -> str:
    if value is None:
        return "미조회"
    return format_number(float(value), digits=2, trim=True)


def _market_index_attr(row: MarketIndexQuote | Mapping[str, Any], key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _market_index_cell(row: MarketIndexQuote | Mapping[str, Any]) -> str:
    label = str(_market_index_attr(row, "label") or "-")
    symbol = str(_market_index_attr(row, "symbol") or "")
    value = _market_index_attr(row, "value")
    status = str(_market_index_attr(row, "status") or "")
    change_pct = _market_index_attr(row, "change_pct")
    error_message = _market_index_attr(row, "error_message")
    if status == "updated" and value is not None:
        change_class = _signed_class(float(change_pct or 0.0))
        change_text = signed_percentage(float(change_pct or 0.0))
    else:
        change_class = "summary-neutral"
        change_text = "조회 실패"
    title_parts = [label]
    if symbol:
        title_parts.append(symbol)
    if error_message:
        title_parts.append(str(error_message))
    return (
        f"<div class='summary-index-cell' title='{escape(' · '.join(title_parts))}'>"
        f"<span class='summary-index-name'>{escape(label)}</span>"
        "<span class='summary-index-quote'>"
        f"<span class='summary-index-value'>{escape(_market_index_value(value))}</span>"
        f"<span class='summary-index-change {change_class}'>({escape(change_text)})</span>"
        "</span>"
        "</div>"
    )


def _market_warning_attr(row: MarketWarningSignal | Mapping[str, Any], key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _market_warning_placeholder_rows() -> list[dict[str, Any]]:
    return [
        {
            "label": spec.label,
            "status": "pending",
        }
        for spec in DEFAULT_MARKET_WARNING_SPECS
    ]


def _market_warning_meta(status: str) -> tuple[str, str]:
    if status == "buy_blocked":
        return "매수 금지", "summary-warning-buy"
    if status == "sell_blocked":
        return "매도 금지", "summary-warning-sell"
    if status == "clear":
        return "정상 범위", "summary-warning-clear"
    if status == "insufficient":
        return "데이터 부족", "summary-warning-neutral"
    if status == "configuration_required":
        return "설정 필요", "summary-warning-neutral"
    if status == "failed":
        return "조회 실패", "summary-warning-neutral"
    return "조회 대기", "summary-warning-neutral"


def _market_warning_card(row: MarketWarningSignal | Mapping[str, Any]) -> str:
    label = str(_market_warning_attr(row, "label") or "-")
    status = str(_market_warning_attr(row, "status") or "pending")
    badge, status_class = _market_warning_meta(status)
    return (
        f"<div class='summary-warning-card {status_class}'>"
        f"<strong class='summary-warning-label'>{escape(label)}</strong>"
        f"<div class='summary-warning-badge'>{escape(badge)}</div>"
        "</div>"
    )


def _market_warning_strip(rows: list[MarketWarningSignal | Mapping[str, Any]] | None) -> str:
    warning_rows = list(rows or []) or _market_warning_placeholder_rows()
    cards = "".join(_market_warning_card(row) for row in warning_rows)
    return (
        "<div class='summary-warning-strip' aria-label='매수 매도 경고'>"
        f"<div class='summary-warning-cards'>{cards}</div>"
        "</div>"
    )


def _market_index_strip(rows: list[MarketIndexQuote | Mapping[str, Any]] | None) -> str:
    index_rows = list(rows or [])
    if not index_rows:
        cells = "<div class='summary-index-empty'>주요 지수 데이터 미조회</div>"
    else:
        cells = "".join(_market_index_cell(row) for row in index_rows)
    return (
        "<div class='summary-index-strip' aria-label='주요 지수변동'>"
        "<div class='summary-index-title'>주요 지수변동</div>"
        f"<div class='summary-index-cells'>{cells}</div>"
        "</div>"
    )


def _coverage_label(metrics: PortfolioMetrics) -> str:
    if metrics.total_position_value_krw <= 0:
        return "보유 종목 없음"
    covered_count = sum(1 for row in metrics.rows if row.cost_basis_krw is not None)
    return f"평균단가 입력 {covered_count:,}/{metrics.holdings_count:,}종목"


def _holding_table_rows(
    metrics: PortfolioMetrics,
    *,
    transactions: list[dict[str, Any]] | None = None,
    as_of_date: date | None = None,
) -> list[str]:
    rows = []
    normalized_transactions = _normalized_transactions(transactions)
    irr_date = as_of_date or datetime.now(KST).date()
    if metrics.rows:
        rows.append(
            "<tr class='summary-section-row summary-section-investment'>"
            "<td colspan='8'>"
            "<span>투자</span>"
            "</td>"
            "</tr>"
        )
    for item in sorted(metrics.rows, key=lambda row: row.market_value_krw or 0.0, reverse=True):
        holding = item.holding
        label = escape(instrument_label(holding))
        color = _movement_dot_color(_holding_day_change_price(holding))
        currency = _currency_label(holding.get("currency"))
        quantity = f"{format_number(float(holding.get('quantity') or 0), digits=4, trim=True)}주"
        avg_price = format_price(holding.get("avg_price"), holding.get("currency"))
        purchase_amount = _krw(item.cost_basis_krw) if item.cost_basis_krw is not None else "-"
        current_price = format_price(holding.get("current_price"), holding.get("currency"))
        market_value = _krw(item.market_value_krw)
        day_change = _price_change_text(holding)
        day_change_class = _signed_class(_holding_day_change_price(holding))
        day_change_value = _holding_day_change_price(holding)
        irr = _holding_irr(holding, normalized_transactions, as_of_date=irr_date)
        irr_text = signed_percentage(irr) if irr is not None else "-"
        rows.append(
            "<tr>"
            f"<td class='summary-name'><span class='summary-name-inner'><span class='summary-name-dot' style='background:{color}'></span><span class='summary-name-text'>{label}</span>{_currency_badge(currency)}</span></td>"
            f"<td>{escape(quantity)}</td>"
            "<td class='summary-price-cell'>"
            f"{_price_amount_group_html(avg_price=avg_price, purchase_amount_krw=purchase_amount, current_price=current_price, market_value_krw=market_value, current_tone=day_change_class)}"
            "</td>"
            f"<td class='summary-sparkline-cell'>{_sparkline_html(holding)}</td>"
            f"<td class='{day_change_class}'>{_badge_html(day_change_value, day_change)}</td>"
            f"<td>{_pnl_stack_html(item.total_pnl_pct, item.total_pnl_krw)}</td>"
            f"<td>{_plain_metric_html(irr, irr_text)}</td>"
            f"<td>{escape(percentage(item.weight, digits=2))}</td>"
            "</tr>"
        )
    if metrics.cash_total_krw > 0:
        rows.append(
            "<tr class='summary-section-row summary-section-cash'>"
            "<td colspan='8'>"
            "<span>현금</span>"
            "</td>"
            "</tr>"
        )
        for cash_row in _cash_allocation_rows(metrics):
            currency = str(cash_row["currency"])
            quantity = _krw(metrics.cash.cash_krw) if currency == "KRW" else format_price(metrics.cash.cash_usd, "USD")
            current_price = "-" if currency == "KRW" else f"{format_number(metrics.usd_krw, digits=0)}원/USD"
            rows.append(
                "<tr class='summary-cash-detail-row'>"
                f"<td class='summary-name'><span class='summary-name-inner'><span class='summary-name-dot' style='background:{cash_row['color']}'></span><span class='summary-name-text'>{escape(str(cash_row['label']))}</span>{_currency_badge(currency)}</span></td>"
                f"<td>{escape(quantity)}</td>"
                "<td class='summary-price-cell'>"
                f"{_price_amount_group_html(avg_price='-', purchase_amount_krw='-', current_price=current_price, market_value_krw=_krw(float(cash_row['value_krw'])), current_tone='summary-neutral')}"
                "</td>"
                "<td>-</td><td>-</td><td>-</td><td>-</td>"
                f"<td>{escape(percentage(float(cash_row['weight']), digits=2))}</td>"
                "</tr>"
            )
    portfolio_irr = _portfolio_irr(metrics, normalized_transactions, as_of_date=irr_date)
    total_day_text = f"{_signed_text(metrics.day_change_krw, signed_krw)} ({_signed_text(metrics.day_change_pct, signed_percentage)})"
    rows.append(
        "<tr class='summary-total-row'>"
        "<td>합계 (주식 평가금액 + 현금)</td><td>-</td>"
        "<td class='summary-price-cell'>"
        f"{_price_amount_group_html(avg_price='-', purchase_amount_krw=_krw(metrics.total_cost_krw) if metrics.total_cost_krw else '-', current_price='-', market_value_krw=_krw(metrics.total_value_krw), current_tone='summary-neutral')}"
        "</td>"
        "<td>-</td>"
        f"<td>{_badge_html(metrics.day_change_krw, total_day_text)}</td>"
        f"<td>{_pnl_stack_html(metrics.total_pnl_pct, metrics.total_pnl_krw)}</td>"
        f"<td>{_plain_metric_html(portfolio_irr, signed_percentage(portfolio_irr) if portfolio_irr is not None else '-')}</td>"
        "<td>100.00%</td>"
        "</tr>"
    )
    return rows


def _mobile_holding_summary_table(metrics: PortfolioMetrics) -> str:
    rows = []
    for item in sorted(metrics.rows, key=lambda row: row.market_value_krw or 0.0, reverse=True):
        holding = item.holding
        label = instrument_label(holding)
        color = _movement_dot_color(_holding_day_change_price(holding))
        quantity = f"{format_number(float(holding.get('quantity') or 0), digits=1, trim=True)}주"
        avg_price = _mobile_price(holding.get("avg_price"), holding.get("currency"))
        current_price = _mobile_price(holding.get("current_price"), holding.get("currency"))
        rows.append(
            "<tr>"
            "<td>"
            f"<div class='summary-mobile-summary-name'><span class='summary-name-dot' style='background:{color}'></span><strong>{escape(label)}</strong></div>"
            "</td>"
            f"<td>{escape(quantity)}</td>"
            f"<td class='summary-mobile-tight'>{escape(avg_price)}</td>"
            f"<td class='summary-mobile-tight'>{escape(current_price)}</td>"
            f"<td class='summary-mobile-summary-weight'>{escape(percentage(item.weight, digits=1))}</td>"
            "</tr>"
        )
    if not rows:
        return ""
    return (
        "<div class='summary-mobile-holdings'>"
        "<h3>보유 종목 요약</h3>"
        "<div class='summary-mobile-table-scroll'>"
        "<table class='summary-mobile-holding-table'>"
        "<thead><tr>"
        "<th>종목명</th><th>수량</th><th>평균단가</th><th>현재가</th><th>자산비중</th>"
        "</tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table></div></div>"
    )


def _kpi_card(title: str, value: str, subtext: str, color: str = "default", icon: str = "") -> str:
    icon_html = f"<div class='summary-kpi-icon'>{escape(icon)}</div>" if icon else ""
    return (
        f"<div class='summary-kpi summary-kpi-{color}'>"
        f"{icon_html}"
        "<div class='summary-kpi-copy'>"
        f"<div class='summary-kpi-title'>{escape(title)}</div>"
        f"<div class='summary-kpi-value'>{escape(value)}</div>"
        f"<div class='summary-kpi-sub'>{escape(subtext)}</div>"
        "</div>"
        "</div>"
    )


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        .summary-card {
            background: var(--summary-card-bg);
            border: 1px solid var(--app-border);
            border-radius: 8px;
            color: var(--app-text);
            padding: 20px;
            box-shadow: var(--app-shadow);
        }
        .summary-card * { box-sizing: border-box; letter-spacing: 0; }
        .summary-top {
            display: grid;
            grid-template-columns: minmax(260px, 1fr) 300px 220px;
            gap: 12px;
            align-items: stretch;
        }
        .summary-title h2 { margin: 0; font-size: 2.35rem; line-height: 1.08; color: var(--app-heading); font-weight: 900; }
        .summary-title p { margin: 12px 0 0; color: var(--app-muted); font-size: 1.08rem; }
        .summary-top-box, .summary-panel, .summary-table-wrap, .summary-kpi {
            background: var(--summary-panel-bg);
            border: 1px solid var(--app-border);
            border-radius: 8px;
        }
        .summary-top-box { padding: 16px 18px; box-shadow: var(--app-shadow-sm); }
        .summary-top-label { color: var(--app-muted); font-size: 0.92rem; }
        .summary-date { color: var(--app-positive); font-size: 1.64rem; margin-top: 4px; font-weight: 850; }
        .summary-delta { font-size: 1.82rem; margin-top: 8px; font-weight: 900; }
        .summary-sub { color: var(--app-muted); font-size: 0.92rem; margin-top: 4px; }
        .summary-main {
            display: grid;
            grid-template-columns: 360px minmax(360px, 1fr);
            gap: 18px;
            margin-top: 16px;
            align-items: stretch;
        }
        .summary-panel { padding: 18px; box-shadow: var(--app-shadow-sm); }
        .summary-panel h3, .summary-table-wrap h3 { margin: 0 0 16px; color: var(--app-heading); font-size: 1.24rem; font-weight: 850; }
        .summary-legend-row {
            display: grid;
            grid-template-columns: 20px minmax(0, 1fr) 74px;
            gap: 8px;
            align-items: center;
            padding: 8px 0;
            color: var(--app-text);
            font-size: 1.02rem;
        }
        .summary-dot { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
        .summary-legend-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .summary-legend-name {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .summary-legend-title {
            min-width: 0;
            display: flex;
            align-items: center;
            gap: 6px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-legend-name small {
            color: var(--app-muted);
            font-size: 0.78rem;
            line-height: 1.2;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-legend-pct { text-align: right; font-variant-numeric: tabular-nums; }
        .summary-asset-group {
            padding: 10px 0;
            border-bottom: 1px solid var(--app-border);
        }
        .summary-asset-group:first-of-type { padding-top: 0; }
        .summary-asset-group-cash { border-bottom: 0; }
        .summary-asset-group-head {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 8px;
            color: var(--app-heading);
            font-size: 0.94rem;
            font-weight: 850;
        }
        .summary-dot-rule {
            margin: -2px 0 6px;
            color: var(--app-muted);
            font-size: 0.76rem;
            line-height: 1.25;
            display: flex;
            flex-wrap: wrap;
            gap: 6px 10px;
        }
        .summary-dot-rule span {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
        }
        .summary-dot-rule span:before {
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            display: inline-block;
        }
        .summary-dot-rule-up:before {
            background: var(--app-profit);
        }
        .summary-dot-rule-down:before {
            background: var(--app-loss);
        }
        .summary-dot-rule-flat:before {
            background: var(--token-neutral-value);
        }
        .summary-empty-line {
            color: var(--app-muted);
            font-size: 0.9rem;
            padding: 6px 0 8px;
        }
        .summary-legend-total { border-top: 1px solid var(--app-border); margin-top: 12px; padding-top: 14px; color: var(--app-positive); text-align: center; font-size: 1.18rem; font-weight: 850; }
        .summary-heatmap-card {
            padding: 18px;
            min-height: 0;
            display: flex;
            flex-direction: column;
        }
        .summary-heatmap-head {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            margin-bottom: 12px;
        }
        .summary-heatmap-head h3 { margin: 0; }
        .summary-heatmap-legend { display: flex; gap: 12px; color: var(--app-muted); font-size: 0.9rem; }
        .summary-heatmap-legend span:before {
            content: "";
            width: 9px;
            height: 9px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
        }
        .summary-heatmap-legend .up:before { background: var(--app-profit); }
        .summary-heatmap-legend .flat:before { background: var(--token-neutral-value); }
        .summary-heatmap-legend .down:before { background: var(--app-loss); }
        .summary-heatmap-area {
            position: relative;
            flex: 1;
            min-height: 300px;
            width: 100%;
            background: var(--summary-heatmap-bg);
            border: 1px solid var(--summary-heatmap-border);
            border-radius: 7px;
            overflow: hidden;
            box-shadow: var(--app-shadow);
        }
        .summary-heatmap-mobile { display: none; }
        .summary-heatmap-tile {
            position: absolute;
            border: 2px solid var(--summary-heatmap-tile-border);
            color: var(--token-chart-tooltip-text);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            line-height: 1.15;
            padding: 4px;
            overflow: hidden;
            text-shadow: none;
            box-shadow: inset 0 -12px 28px color-mix(in srgb, var(--token-overlay) 36%, transparent);
            transition: filter 150ms ease, transform 150ms ease, box-shadow 150ms ease;
            transform-origin: center;
            will-change: filter, transform;
        }
        .summary-heatmap-tile:hover {
            filter: brightness(1.15) saturate(1.08);
            transform: translateZ(0) scale(1.1);
            z-index: 5;
            overflow: visible;
            box-shadow: inset 0 -8px 18px color-mix(in srgb, var(--token-overlay) 22%, transparent);
        }
        .summary-heatmap-small {
            padding: 2px;
            line-height: 1.02;
        }
        .summary-heatmap-small .summary-heatmap-name {
            -webkit-line-clamp: 1;
            font-size: 0.82em;
        }
        .summary-heatmap-small .summary-heatmap-change {
            margin-top: 2px;
            font-size: 0.68em;
        }
        .summary-heatmap-small:hover {
            font-size: max(0.78rem, 1em) !important;
            transform: translateZ(0) scale(1.18);
        }
        .summary-heatmap-small:hover .summary-heatmap-name {
            -webkit-line-clamp: 2;
        }
        .summary-heatmap-name {
            font-weight: 900;
            max-width: 100%;
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
            overflow: hidden;
            text-overflow: clip;
            white-space: normal;
            word-break: keep-all;
            overflow-wrap: anywhere;
        }
        .summary-heatmap-market {
            color: var(--token-chart-tooltip-text);
            font-size: 0.72em;
            font-weight: 750;
            opacity: 0.78;
            white-space: nowrap;
        }
        .summary-heatmap-change { font-size: 0.82em; margin-top: 6px; font-weight: 760; font-variant-numeric: tabular-nums; }
        .summary-heatmap-empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--app-muted); }
        .summary-sector-heatmap {
            flex: 0 0 auto;
            position: relative;
            height: clamp(276px, 22vw, 310px);
            min-height: 0;
            overflow: hidden;
            border-radius: 8px;
            background: var(--summary-heatmap-bg);
        }
        .summary-sector-group {
            position: absolute;
            box-sizing: border-box;
            min-width: 0;
            min-height: 0;
            display: flex;
            flex-direction: column;
            padding: 5px;
            border: 2px solid var(--summary-heatmap-bg);
            border-radius: 7px;
            background: var(--summary-heatmap-bg);
            box-shadow: inset 0 0 0 1px var(--summary-heatmap-border);
            overflow: hidden;
        }
        .summary-sector-group-head {
            flex: 0 0 auto;
            min-height: 25px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
            padding: 0 2px 5px;
        }
        .summary-sector-group-name {
            min-width: 0;
            display: flex;
            align-items: baseline;
            gap: 7px;
        }
        .summary-sector-group-name strong {
            min-width: 0;
            color: var(--app-heading);
            font-size: clamp(0.72rem, 0.82vw, 0.88rem);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-sector-group-name span {
            color: var(--app-muted);
            font-size: 0.68rem;
            white-space: nowrap;
        }
        .summary-sector-group-weight {
            color: var(--app-primary);
            font-size: clamp(0.68rem, 0.76vw, 0.8rem);
            font-weight: 850;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }
        .summary-sector-members {
            position: relative;
            flex: 1;
            min-height: 0;
            overflow: hidden;
            border-radius: 5px;
        }
        .summary-sector-tile {
            position: absolute;
            box-sizing: border-box;
            min-width: 0;
            min-height: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            padding: 4px;
            border: 2px solid var(--summary-heatmap-bg);
            border-radius: 5px;
            color: var(--token-chart-tooltip-text);
            text-align: center;
            overflow: hidden;
            transition: filter 150ms ease, transform 150ms ease, box-shadow 150ms ease;
        }
        .summary-sector-tile:hover {
            z-index: 4;
            filter: brightness(1.18) saturate(1.06);
            transform: translateZ(0) scale(1.035);
            box-shadow: var(--app-shadow-sm);
        }
        .summary-sector-tile-aggregate {
            box-shadow: inset 0 0 0 1px var(--summary-heatmap-tile-border);
        }
        .summary-sector-group-compact .summary-sector-tile {
            flex-direction: row;
            justify-content: space-between;
            gap: 4px;
            padding: 2px 6px;
        }
        .summary-sector-group-compact .summary-sector-tile-name {
            min-width: 0;
            font-size: 0.64rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .summary-sector-group-compact .summary-sector-tile-change {
            flex: 0 0 auto;
            font-size: 0.64rem;
        }
        .summary-sector-group-compact .summary-sector-tile-weight,
        .summary-sector-group-compact .summary-heatmap-market {
            display: none;
        }
        .summary-sector-tile-name {
            max-width: 100%;
            font-size: clamp(0.62rem, 0.78vw, 0.88rem);
            font-weight: 850;
            line-height: 1.15;
            overflow-wrap: anywhere;
        }
        .summary-sector-tile-change {
            font-size: clamp(0.68rem, 0.88vw, 0.96rem);
            font-weight: 900;
            font-variant-numeric: tabular-nums;
        }
        .summary-sector-tile-weight {
            color: var(--token-chart-tooltip-text);
            font-size: 0.62rem;
            font-weight: 700;
            opacity: 0.78;
            white-space: nowrap;
        }
        .summary-sector-tile-small {
            gap: 1px;
            padding: 2px;
        }
        .summary-sector-tile-small .summary-sector-tile-name {
            font-size: clamp(0.56rem, 0.68vw, 0.7rem);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .summary-sector-tile-small .summary-sector-tile-change { font-size: 0.64rem; }
        .summary-sector-tile-small .summary-sector-tile-weight { display: none; }
        .summary-sector-tile-tiny .summary-sector-tile-change { display: none; }
        .summary-sector-heatmap-empty {
            place-items: center;
            color: var(--app-muted);
            border: 1px solid var(--summary-heatmap-border);
            border-radius: 7px;
            background: var(--summary-heatmap-bg);
        }
        .summary-mobile-heatmap-layout {
            display: block;
        }
        .summary-mobile-heatmap-major {
            position: relative;
            min-height: 0;
            aspect-ratio: 4 / 3;
            overflow: hidden;
            border: 1px solid var(--summary-heatmap-border);
            border-radius: 7px;
            background: var(--summary-heatmap-bg);
            box-shadow: var(--app-shadow);
        }
        .summary-mobile-heatmap-empty {
            min-height: 232px;
            place-items: center;
            color: var(--app-muted);
            border: 1px solid var(--summary-heatmap-border);
            border-radius: 7px;
            background: var(--summary-heatmap-bg);
        }
        .summary-index-strip {
            margin-top: 12px;
            padding: 10px 12px;
            border: 1px solid var(--app-border);
            border-radius: 7px;
            background: var(--summary-panel-bg);
        }
        .summary-index-title {
            margin-bottom: 7px;
            color: var(--app-muted);
            font-size: 0.82rem;
            font-weight: 850;
        }
        .summary-index-cells {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 8px;
            align-items: stretch;
        }
        .summary-index-cell {
            min-width: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            padding: 7px 7px;
            border: 1px solid var(--app-border);
            border-radius: 6px;
            background: var(--app-surface);
            color: var(--app-text);
            font-size: 0.74rem;
            line-height: 1.2;
            text-align: center;
            font-variant-numeric: tabular-nums;
        }
        .summary-index-name {
            max-width: 100%;
            color: var(--app-muted);
            font-weight: 820;
            line-height: 1.14;
            white-space: normal;
            word-break: keep-all;
        }
        .summary-index-quote {
            display: inline-flex;
            align-items: baseline;
            justify-content: center;
            gap: 1px;
            min-width: 0;
            max-width: 100%;
            white-space: nowrap;
        }
        .summary-index-value {
            color: var(--app-heading);
            font-weight: 850;
        }
        .summary-index-change {
            font-size: 0.72rem;
            font-weight: 820;
        }
        .summary-index-empty {
            color: var(--app-muted);
            font-size: 0.82rem;
        }
        .summary-warning-strip {
            margin-top: 10px;
        }
        .summary-warning-cards {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }
        .summary-warning-card {
            min-width: 0;
            min-height: 41px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding: 7px;
            border: 1px solid var(--app-border);
            border-radius: 6px;
            background: var(--app-surface);
            color: var(--app-text);
            box-sizing: border-box;
        }
        .summary-warning-label {
            min-width: 0;
            color: var(--app-heading);
            font-size: 0.86rem;
            font-weight: 900;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-warning-badge {
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 25px;
            padding: 4px 9px;
            border-radius: 999px;
            border: 1px solid var(--app-border);
            color: var(--app-muted);
            background: var(--token-neutral-value-soft);
            font-size: 0.75rem;
            font-weight: 900;
            line-height: 1;
            white-space: nowrap;
        }
        .summary-warning-buy .summary-warning-badge {
            border-color: var(--token-profit);
            color: var(--token-profit);
            background: var(--token-profit-soft);
        }
        .summary-warning-sell .summary-warning-badge {
            border-color: var(--token-loss);
            color: var(--token-loss);
            background: var(--token-loss-soft);
        }
        .summary-warning-clear .summary-warning-badge {
            border-color: var(--token-success);
            color: var(--token-success);
            background: var(--token-success-soft);
        }
        .summary-mobile-holdings { display: none; }
        .summary-table-wrap { margin-top: 16px; overflow: hidden; }
        .summary-table-wrap h3 { padding: 16px 20px; margin: 0; border-bottom: 1px solid var(--app-border); }
        .summary-table-scroll { overflow-x: auto; }
        .summary-table {
            width: 100%;
            min-width: 0;
            table-layout: fixed;
            border-collapse: collapse;
            font-size: clamp(0.68rem, 0.63vw, 0.79rem);
            line-height: 1.22;
        }
        .summary-table th, .summary-table td {
            border-bottom: 1px solid var(--app-border);
            padding: 8px 5px;
            text-align: right;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            vertical-align: middle;
        }
        .summary-table th { color: var(--app-muted); font-weight: 760; background: var(--app-table-header); }
        .summary-table tbody tr:not(.summary-total-row):hover td { background: var(--app-table-hover); }
        .summary-table th:first-child, .summary-table td:first-child { text-align: left; }
        .summary-col-name { width: 16%; }
        .summary-col-qty { width: 7.5%; }
        .summary-col-price-group { width: 29%; }
        .summary-col-spark { width: 8.5%; }
        .summary-col-day { width: 10.5%; }
        .summary-col-pnl { width: 12.5%; }
        .summary-col-irr { width: 7.5%; }
        .summary-col-weight { width: 8.5%; }
        .summary-price-heading {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            align-items: center;
            text-align: center;
            line-height: 1.2;
        }
        .summary-price-heading strong {
            display: block;
            color: var(--app-muted);
            font-size: 1em;
        }
        .summary-price-heading span {
            display: block;
            margin-top: 4px;
            color: var(--app-muted);
            font-size: 0.86em;
            font-weight: 650;
        }
        .summary-pnl-heading {
            display: grid;
            gap: 4px;
            justify-items: center;
            line-height: 1.2;
        }
        .summary-pnl-heading strong {
            color: var(--app-muted);
            font-weight: 760;
        }
        .summary-pnl-heading span {
            color: var(--app-muted);
            font-size: 0.86em;
            font-weight: 650;
        }
        .summary-price-cell {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        .summary-price-group {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            align-items: center;
            text-align: center;
            min-width: 0;
        }
        .summary-price-stack {
            min-width: 0;
            display: grid;
            gap: 4px;
            align-content: center;
        }
        .summary-price-main {
            color: var(--app-heading);
            font-size: 1.08em;
            font-weight: 860;
            line-height: 1.15;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-current-price.summary-up { color: var(--summary-up-text); }
        .summary-current-price.summary-down { color: var(--summary-down-text); }
        .summary-current-price.summary-neutral { color: var(--app-heading); }
        .summary-price-sub {
            color: var(--app-muted);
            font-size: 0.92em;
            font-weight: 650;
            line-height: 1.18;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-market-value {
            color: var(--app-text);
            font-weight: 760;
        }
        .summary-name {
            min-width: 0;
        }
        .summary-name-inner {
            min-width: 0;
            width: 100%;
            max-width: 100%;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            line-height: inherit;
            vertical-align: middle;
        }
        .summary-name-text {
            flex: 1 1 auto;
            min-width: 0;
            display: inline-block;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .summary-name-dot { width: 10px; height: 10px; flex: 0 0 auto; display: inline-block; border-radius: 50%; }
        .summary-currency-badge {
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 34px;
            padding: 2px 5px;
            border-radius: 999px;
            border: 1px solid var(--app-border);
            color: var(--app-muted);
            background: var(--app-surface-alt);
            font-size: 0.68rem;
            font-weight: 820;
            line-height: 1;
        }
        .summary-currency-usd {
            color: var(--token-usd);
            border-color: var(--token-usd);
            background: var(--token-usd-soft);
        }
        .summary-currency-krw {
            color: var(--token-krw);
            border-color: var(--token-border-strong);
            background: var(--token-krw-soft);
        }
        .summary-section-row td {
            padding: 9px 12px !important;
            text-align: left !important;
            background: var(--app-panel-strong) !important;
            color: var(--app-heading);
            font-weight: 850;
            display: table-cell !important;
        }
        .summary-cash-detail-row td {
            color: var(--app-muted);
        }
        .summary-sparkline-th, .summary-sparkline-cell { text-align: center !important; }
        .summary-sparkline {
            width: 70px;
            height: 26px;
            display: inline-grid;
            place-items: center;
            border-radius: 7px;
            background: var(--app-surface-alt);
            border: 1px solid var(--app-border);
        }
        .summary-sparkline svg { width: 64px; height: 20px; display: block; overflow: visible; }
        .summary-sparkline polyline {
            fill: none;
            stroke: currentColor;
            stroke-width: 2.2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }
        .summary-sparkline circle { fill: currentColor; }
        .summary-sparkline-baseline { stroke: var(--app-border-strong); stroke-width: 1; stroke-dasharray: 3 4; }
        .summary-sparkline-up { color: var(--app-profit); background: var(--token-profit-soft); }
        .summary-sparkline-down { color: var(--app-loss); background: var(--token-loss-soft); }
        .summary-sparkline-neutral { color: var(--app-muted); }
        .summary-sparkline-empty:before {
            content: "";
            width: 54px;
            border-top: 1px dashed var(--app-border-strong);
        }
        .summary-split-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-top: 16px;
        }
        .summary-split-card {
            border: 1px solid var(--app-border);
            border-radius: 8px;
            background: var(--summary-panel-bg);
            padding: 16px 18px;
            box-shadow: var(--app-shadow-sm);
        }
        .summary-split-heading {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            max-width: 100%;
        }
        .summary-split-label {
            color: var(--app-muted);
            font-size: 0.92rem;
            font-weight: 760;
        }
        .summary-split-pct {
            display: inline-flex;
            align-items: center;
            min-height: 20px;
            padding: 0 7px;
            border-radius: 999px;
            color: var(--app-heading);
            background: var(--app-surface-alt);
            border: 1px solid var(--app-border);
            font-size: 0.78rem;
            font-weight: 850;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }
        .summary-split-value {
            color: var(--app-heading);
            font-size: 1.58rem;
            font-weight: 900;
            margin-top: 6px;
            font-variant-numeric: tabular-nums;
            overflow-wrap: anywhere;
        }
        .summary-split-sub {
            color: var(--app-muted);
            font-size: 0.9rem;
            margin-top: 4px;
        }
        .summary-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 0;
            max-width: 100%;
            padding: 3px 6px;
            border-radius: 999px;
            font-weight: 820;
            line-height: 1.12;
            white-space: nowrap;
            border: 0;
            font-size: 0.92em;
        }
        .summary-badge.summary-up { color: var(--summary-up-text); background: var(--summary-up-bg); }
        .summary-badge.summary-down { color: var(--summary-down-text); background: var(--summary-down-bg); }
        .summary-badge.summary-neutral { color: var(--app-text); background: var(--summary-neutral-badge-bg); }
        .summary-plain-metric {
            display: inline-block;
            color: var(--app-muted);
            font-weight: 850;
            line-height: 1.2;
            white-space: nowrap;
        }
        .summary-plain-metric.summary-up { color: var(--summary-up-text); }
        .summary-plain-metric.summary-down { color: var(--summary-down-text); }
        .summary-pnl-stack {
            display: inline-grid;
            gap: 4px;
            justify-items: center;
            align-content: center;
            line-height: 1.18;
            white-space: nowrap;
        }
        .summary-pnl-stack.summary-up { color: var(--summary-up-text); }
        .summary-pnl-stack.summary-down { color: var(--summary-down-text); }
        .summary-pnl-stack.summary-neutral { color: var(--app-muted); }
        .summary-pnl-rate {
            font-size: 1.06em;
            font-weight: 900;
        }
        .summary-pnl-delta {
            font-size: 0.9em;
            font-weight: 780;
        }
        .summary-total-row td { color: var(--app-heading); font-weight: 800; background: var(--app-panel-strong); }
        .summary-kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
        .summary-kpi { padding: 17px 18px; min-height: 112px; display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 12px; align-items: start; }
        .summary-kpi-icon {
            width: 34px;
            height: 34px;
            border-radius: 9px;
            display: grid;
            place-items: center;
            color: var(--token-info-text);
            background: var(--token-info-soft);
            border: 1px solid var(--app-border);
            font-weight: 900;
            font-size: 0.84rem;
        }
        .summary-kpi-title { color: var(--app-muted); font-size: 0.96rem; }
        .summary-kpi-value { color: var(--app-heading); font-size: 1.58rem; font-weight: 900; margin-top: 6px; font-variant-numeric: tabular-nums; }
        .summary-kpi-sub { color: var(--app-muted); font-size: 0.9rem; margin-top: 4px; }
        .summary-kpi-cyan .summary-kpi-value { color: var(--app-accent); }
        .summary-kpi-cyan .summary-kpi-icon { color: var(--app-accent); background: var(--app-accent-soft); border-color: var(--app-accent); }
        .summary-kpi-red .summary-kpi-value, .summary-up { color: var(--summary-up-text); }
        .summary-kpi-red .summary-kpi-icon { color: var(--summary-up-text); background: var(--summary-up-bg); border-color: var(--summary-up-border); }
        .summary-kpi-blue .summary-kpi-value, .summary-down { color: var(--summary-down-text); }
        .summary-kpi-blue .summary-kpi-icon { color: var(--summary-down-text); background: var(--summary-down-bg); border-color: var(--summary-down-border); }
        .summary-neutral { color: var(--app-muted); }
        .summary-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; color: var(--app-muted); font-size: 0.9rem; }
        @media (max-width: 980px) {
            .summary-top, .summary-main, .summary-split-grid, .summary-kpi-grid { grid-template-columns: 1fr; }
            .summary-heatmap-card { min-height: 0; }
            .summary-sector-heatmap {
                height: clamp(270px, 32vw, 300px);
                min-height: 0;
            }
            .summary-heatmap-area { min-height: 260px; }
        }
        @media (max-width: 720px) {
            .summary-card {
                padding: 12px;
                box-shadow: var(--app-shadow-sm);
            }
            .summary-title h2 {
                font-size: 1.72rem;
                line-height: 1.14;
            }
            .summary-title p {
                margin-top: 8px;
                font-size: 0.94rem;
            }
            .summary-top {
                grid-template-columns: 1fr;
                gap: 10px;
            }
            .summary-top-box,
            .summary-panel,
            .summary-table-wrap,
            .summary-kpi {
                border-radius: 8px;
            }
            .summary-top-box,
            .summary-panel {
                padding: 12px;
            }
            .summary-date,
            .summary-delta {
                font-size: 1.32rem;
            }
            .summary-main {
                grid-template-columns: 1fr;
                gap: 12px;
                margin-top: 12px;
            }
            .summary-legend-row {
                grid-template-columns: 18px minmax(0, 1fr) 68px;
                font-size: 0.93rem;
                padding: 7px 0;
            }
            .summary-heatmap-card {
                min-height: 0;
            }
            .summary-sector-heatmap { display: none; }
            .summary-heatmap-mobile { display: block; }
            .summary-heatmap-head {
                align-items: flex-start;
                flex-direction: column;
            }
            .summary-heatmap-tile {
                padding: 4px;
                font-size: clamp(0.68rem, 3.15vw, 0.98rem) !important;
                line-height: 1.08;
            }
            .summary-heatmap-name {
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
                white-space: normal;
                text-overflow: clip;
                word-break: keep-all;
                overflow: hidden;
            }
            .summary-heatmap-change {
                font-size: 0.76em;
                margin-top: 4px;
            }
            .summary-index-strip {
                margin-top: 9px;
                padding: 8px;
            }
            .summary-index-title {
                margin-bottom: 6px;
                font-size: 0.76rem;
            }
            .summary-index-cells {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 6px;
                overflow-x: hidden;
            }
            .summary-index-cell {
                min-width: 0;
                padding: 7px 6px;
                font-size: clamp(0.62rem, 2.55vw, 0.7rem);
            }
            .summary-index-name {
                min-height: 1.56em;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .summary-index-quote {
                gap: 0;
                font-size: clamp(0.58rem, 2.35vw, 0.66rem);
            }
            .summary-index-change {
                font-size: 1em;
            }
            .summary-warning-cards {
                gap: 6px;
            }
            .summary-warning-card {
                min-height: 36px;
                gap: 4px;
                padding: 6px;
            }
            .summary-warning-label {
                font-size: clamp(0.68rem, 2.7vw, 0.74rem);
            }
            .summary-warning-badge {
                min-height: 22px;
                padding: 3px 6px;
                font-size: clamp(0.62rem, 2.55vw, 0.68rem);
            }
            .summary-mobile-holdings {
                display: block;
                margin-top: 12px;
                padding: 13px 12px;
                border: 1px solid var(--app-border);
                border-radius: 8px;
                background: var(--summary-panel-bg);
            }
            .summary-mobile-holdings h3 {
                margin: 0 0 10px;
                color: var(--app-heading);
                font-size: 1.06rem;
            }
            .summary-mobile-table-scroll {
                width: 100%;
                overflow-x: hidden;
            }
            .summary-mobile-holding-table {
                width: 100%;
                table-layout: fixed;
                border-collapse: separate;
                border-spacing: 0;
                font-size: 0.72rem;
                line-height: 1.22;
                font-variant-numeric: tabular-nums;
            }
            .summary-mobile-holding-table th,
            .summary-mobile-holding-table td {
                border-bottom: 1px solid var(--app-border);
                padding: 8px 3px;
                text-align: right;
                vertical-align: middle;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                overflow-wrap: normal;
            }
            .summary-mobile-holding-table th {
                color: var(--app-muted);
                font-size: 0.68rem;
                font-weight: 800;
                background: var(--app-table-header);
            }
            .summary-mobile-holding-table th:first-child,
            .summary-mobile-holding-table td:first-child {
                width: 29%;
                padding-left: 0;
                text-align: left;
            }
            .summary-mobile-holding-table th:nth-child(2),
            .summary-mobile-holding-table td:nth-child(2) {
                width: 14%;
            }
            .summary-mobile-holding-table th:nth-child(3),
            .summary-mobile-holding-table td:nth-child(3),
            .summary-mobile-holding-table th:nth-child(4),
            .summary-mobile-holding-table td:nth-child(4) {
                width: 20%;
            }
            .summary-mobile-holding-table th:nth-child(5),
            .summary-mobile-holding-table td:nth-child(5) {
                width: 17%;
                padding-right: 0;
            }
            .summary-mobile-holding-table tbody tr:last-child td {
                border-bottom: 0;
            }
            .summary-mobile-summary-name {
                min-width: 0;
                display: flex;
                align-items: center;
                gap: 5px;
                color: var(--app-heading);
                font-weight: 850;
            }
            .summary-mobile-summary-name .summary-name-dot {
                width: 9px;
                height: 9px;
                flex: 0 0 auto;
                border-radius: 50%;
            }
            .summary-mobile-summary-name strong {
                min-width: 0;
                font-size: 0.76rem;
                line-height: 1.18;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .summary-mobile-tight {
                font-size: clamp(0.58rem, 2.35vw, 0.7rem);
                letter-spacing: -0.01em;
            }
            .summary-mobile-summary-weight {
                color: var(--app-positive);
                font-weight: 850;
                font-size: clamp(0.58rem, 2.35vw, 0.7rem);
            }
            .summary-table-wrap {
                margin-top: 12px;
                overflow: visible;
            }
            .summary-table-wrap h3 {
                padding: 13px 14px;
                font-size: 1.06rem;
            }
            .summary-table-scroll {
                overflow: visible;
            }
            .summary-table {
                display: block;
                min-width: 0;
                width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                font-size: 0.9rem;
            }
            .summary-table thead {
                display: none;
            }
            .summary-table tbody {
                display: grid;
                gap: 10px;
                padding: 10px;
            }
            .summary-table tr {
                display: grid;
                grid-template-columns: 1fr;
                border: 1px solid var(--app-border);
                border-radius: 8px;
                overflow: hidden;
                background: var(--summary-panel-bg);
            }
            .summary-table th,
            .summary-table td {
                border-bottom: 1px solid var(--app-border);
                padding: 8px 10px;
                min-height: 34px;
                text-align: right;
                white-space: normal;
            }
            .summary-table td {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
            }
            .summary-table td:before {
                color: var(--app-muted);
                content: "";
                flex: 0 0 auto;
                font-size: 0.78rem;
                font-weight: 760;
            }
            .summary-table td:last-child {
                border-bottom: 0;
            }
            .summary-table td:nth-child(1) {
                justify-content: flex-start;
                min-width: 0;
                font-size: 1rem;
                font-weight: 850;
                text-align: left;
            }
            .summary-table td:nth-child(1):before { display: none; }
            .summary-table td:nth-child(2):before { content: "수량"; }
            .summary-table td:nth-child(3):before { content: "단가·금액"; }
            .summary-table td:nth-child(4):before { content: "당일 흐름"; }
            .summary-table td:nth-child(5):before { content: "전일 대비"; }
            .summary-table td:nth-child(6):before { content: "누적수익률"; }
            .summary-table td:nth-child(7):before { content: "IRR"; }
            .summary-table td:nth-child(8):before { content: "자산 비중"; }
            .summary-table td.summary-price-cell {
                display: grid;
                gap: 8px;
            }
            .summary-table td.summary-price-cell:before {
                justify-self: start;
            }
            .summary-table td.summary-price-cell .summary-price-group {
                width: 100%;
            }
            .summary-name {
                min-width: 0;
            }
            .summary-sparkline-th,
            .summary-sparkline-cell {
                width: auto;
                text-align: right !important;
            }
            .summary-sparkline {
                width: 86px;
                height: 30px;
            }
            .summary-sparkline svg {
                width: 80px;
                height: 24px;
            }
            .summary-badge {
                min-width: 0;
                max-width: 100%;
                white-space: normal;
            }
            .summary-total-row td {
                background: var(--app-panel-strong);
            }
            .summary-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
                margin-top: 12px;
            }
            .summary-kpi {
                min-height: 96px;
                padding: 14px;
            }
            .summary-kpi-value {
                font-size: 1.32rem;
                overflow-wrap: anywhere;
            }
            .summary-foot {
                flex-direction: column;
                font-size: 0.82rem;
            }
        }
        @media (max-width: 420px) {
            .summary-kpi-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_investment_summary_card(
    metrics: PortfolioMetrics,
    *,
    portfolio_name: str,
    last_refresh: object = None,
    transactions: list[dict[str, Any]] | None = None,
    market_indices: list[MarketIndexQuote | Mapping[str, Any]] | None = None,
    market_warnings: list[MarketWarningSignal | Mapping[str, Any]] | None = None,
) -> None:
    _render_styles()
    if metrics.holdings_count == 0 and metrics.cash_total_krw <= 0:
        render_empty_state(
            "아직 포트폴리오 데이터가 없습니다.",
            "먼저 입금 또는 보유종목을 입력하면 총괄현황, 자산 비중, 보유 종목 요약이 표시됩니다.",
        )
        return
    holding_allocation_rows = _holding_allocation_rows(metrics)
    allocation_rows = _allocation_rows(metrics)
    as_of_date = _as_of_date(last_refresh)
    stock_pct = metrics.total_position_value_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0
    cash_pct = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0
    day_class = _signed_class(metrics.day_change_krw)
    pnl_class = _signed_class(metrics.total_pnl_krw)
    seed = metrics.total_cost_krw if metrics.total_cost_krw > 0 else None
    seed_label = _krw(seed) if seed is not None else "평균단가 필요"
    kpi_cards = [
        _kpi_card("총자산", _krw(metrics.total_value_krw), f"주식 {percentage(stock_pct, digits=2)} · 현금 {percentage(cash_pct, digits=2)}", "cyan", "₩"),
        _kpi_card("주식 평가금액", _krw(metrics.total_position_value_krw), f"{metrics.priced_count:,}/{metrics.holdings_count:,}종목 평가", "default", "주"),
        _kpi_card("현금", _krw(metrics.cash_total_krw), f"{percentage(cash_pct, digits=2)}", "default", "$"),
        _kpi_card("평가이익", _signed_text(metrics.total_pnl_krw, signed_krw), "주식 평가금액 - 투자원금", _kpi_tone(metrics.total_pnl_krw), "P/L"),
        _kpi_card("주식 수익률", _signed_text(metrics.total_pnl_pct, signed_percentage), _coverage_label(metrics), _kpi_tone(metrics.total_pnl_pct), "%"),
        _kpi_card("오늘 손익", _signed_text(metrics.day_change_krw, signed_krw), "최근 가격과 전일 종가 기준", _kpi_tone(metrics.day_change_krw), "D"),
        _kpi_card("전일대비", _signed_text(metrics.day_change_pct, signed_percentage), "전일 보유 평가액 대비", _kpi_tone(metrics.day_change_pct), "Δ"),
        _kpi_card("투자원금", seed_label, _coverage_label(metrics), "default", "Σ"),
        _kpi_card("환율", f"{format_number(metrics.usd_krw)}원 / USD", "미국 주식 및 달러 현금 환산", "default", "FX"),
    ]
    investment_legend_rows = "".join(
        "<div class='summary-legend-row'>"
        f"<span class='summary-dot' style='background:{row['color']}'></span>"
        "<span class='summary-legend-name'>"
        f"<span class='summary-legend-title'>{escape(str(row['label']))}</span>"
        f"<small>{escape(str(row.get('allocation_detail') or _krw(float(row['value_krw']))))}</small>"
        "</span>"
        f"<span class='summary-legend-pct'>{escape(percentage(float(row['weight']), digits=2))}</span>"
        "</div>"
        for row in allocation_rows
    )
    if not investment_legend_rows:
        investment_legend_rows = "<div class='summary-empty-line'>보유 종목 없음</div>"
    cash_legend_rows = ""
    cash_rows = _cash_allocation_rows(metrics)
    if cash_rows:
        cash_legend_rows = "".join(
            "<div class='summary-legend-row summary-cash-row'>"
            f"<span class='summary-dot' style='background:{row['color']}'></span>"
            "<span class='summary-legend-name'>"
            f"<span class='summary-legend-title'>{escape(str(row['label']))}</span>"
            f"<small>{escape(str(row['detail']))}</small>"
            "</span>"
            f"<span class='summary-legend-pct'>{escape(percentage(float(row['weight']), digits=2))}</span>"
            "</div>"
            for row in cash_rows
        )
    else:
        cash_legend_rows = "<div class='summary-empty-line'>현금 없음</div>"
    desktop_heatmap = _sector_heatmap(holding_allocation_rows)
    mobile_heatmap = _mobile_heatmap(holding_allocation_rows)
    market_index_strip = _market_index_strip(market_indices)
    market_warning_strip = _market_warning_strip(market_warnings)
    mobile_holding_summary = _mobile_holding_summary_table(metrics)
    table_rows = "".join(_holding_table_rows(metrics, transactions=transactions, as_of_date=as_of_date))
    cash_detail = f"KRW {_krw(metrics.cash.cash_krw)} · USD ${format_number(metrics.cash.cash_usd)}"
    html = f"""
    <div class="summary-card">
        <div class="summary-top">
            <div class="summary-title">
                <h2>총괄현황</h2>
            </div>
            <div class="summary-top-box">
                <div class="summary-top-label">기준일</div>
                <div class="summary-date">{escape(_display_date(last_refresh))}</div>
                <div class="summary-sub">최근 가격</div>
            </div>
            <div class="summary-top-box">
                <div class="summary-top-label">전일 대비</div>
                <div class="summary-delta {day_class}">{escape(_signed_text(metrics.day_change_krw, signed_krw))}</div>
                <div class="summary-sub {day_class}">{escape(_signed_text(metrics.day_change_pct, signed_percentage))}</div>
            </div>
        </div>
        <div class="summary-main">
            <div class="summary-panel">
                <h3>자산 비중</h3>
                <div class="summary-asset-group">
                    <div class="summary-asset-group-head"><span>투자</span><strong>{escape(percentage(stock_pct, digits=2))}</strong></div>
                    <div class="summary-dot-rule" aria-label="종목 점 색상 기준">
                        <span class="summary-dot-rule-up">상승</span>
                        <span class="summary-dot-rule-down">하락</span>
                        <span class="summary-dot-rule-flat">보합·미산정</span>
                    </div>
                    {investment_legend_rows}
                </div>
                <div class="summary-asset-group summary-asset-group-cash">
                    <div class="summary-asset-group-head"><span>현금</span><strong>{escape(percentage(cash_pct, digits=2))}</strong></div>
                    {cash_legend_rows}
                </div>
                <div class="summary-legend-total">투자 + 현금 100%</div>
            </div>
            <div class="summary-panel summary-heatmap-card">
                <div class="summary-heatmap-head">
                    <h3>구성·성과</h3>
                    <div class="summary-heatmap-legend"><span class="up">상승</span><span class="flat">보합</span><span class="down">하락</span></div>
                </div>
                {desktop_heatmap}
                <div class="summary-heatmap-mobile">{mobile_heatmap}</div>
                {market_index_strip}
                {market_warning_strip}
            </div>
        </div>
        <div class="summary-split-grid">
            <div class="summary-split-card">
                <div class="summary-split-heading"><div class="summary-split-label">투자자산</div><span class="summary-split-pct">{escape(percentage(stock_pct, digits=1))}</span></div>
                <div class="summary-split-value">{escape(_krw(metrics.total_position_value_krw))}</div>
                <div class="summary-split-sub">주식 평가금액</div>
            </div>
            <div class="summary-split-card">
                <div class="summary-split-heading"><div class="summary-split-label">현금</div><span class="summary-split-pct">{escape(percentage(cash_pct, digits=1))}</span></div>
                <div class="summary-split-value">{escape(_krw(metrics.cash_total_krw))}</div>
                <div class="summary-split-sub">{escape(cash_detail)}</div>
            </div>
        </div>
        {mobile_holding_summary}
        <div class="summary-table-wrap">
            <h3>보유 종목</h3>
            <div class="summary-table-scroll">
                <table class="summary-table">
                    <colgroup>
                        <col class="summary-col-name" />
                        <col class="summary-col-qty" />
                        <col class="summary-col-price-group" />
                        <col class="summary-col-spark" />
                        <col class="summary-col-day" />
                        <col class="summary-col-pnl" />
                        <col class="summary-col-irr" />
                        <col class="summary-col-weight" />
                    </colgroup>
                    <thead>
                        <tr>
                            <th>종목명</th>
                            <th>보유 수량</th>
                            <th>
                                <div class="summary-price-heading">
                                    <div><strong>평균단가</strong><span>(매입금액)</span></div>
                                    <div><strong>현재가</strong><span>(평가금액)</span></div>
                                </div>
                            </th>
                            <th class="summary-sparkline-th">당일 흐름</th>
                            <th>전일대비</th>
                            <th>
                                <div class="summary-pnl-heading">
                                    <strong>누적수익률</strong>
                                    <span>(평가손익)</span>
                                </div>
                            </th>
                            <th>IRR</th>
                            <th>비중</th>
                        </tr>
                    </thead>
                    <tbody>{table_rows}</tbody>
                </table>
            </div>
        </div>
        <div class="summary-kpi-grid">
            {''.join(kpi_cards)}
        </div>
        <div class="summary-foot">
            <span>평가 수익률은 입력한 평균 매입단가 기준입니다.</span>
            <span>수수료 및 세금 비반영</span>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
