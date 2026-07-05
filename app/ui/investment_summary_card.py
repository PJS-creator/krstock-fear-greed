from __future__ import annotations

import math
from datetime import date, datetime
from html import escape
from typing import Any

import streamlit as st

from portfolio.holdings import PortfolioMetrics
from portfolio.transactions import normalize_transaction_rows

from .components import render_empty_state
from .formatters import KST, format_kst, format_number, format_price, instrument_label, percentage, signed_krw, signed_percentage
from .theme import get_active_theme


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


def _currency_badge(value: object) -> str:
    label = _currency_label(value)
    if label == "-":
        return ""
    return f"<span class='summary-currency-badge summary-currency-{label.lower()}'>{escape(label)}</span>"


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
    intensity = min(abs(change_pct) / 0.045, 1.0)
    if change_pct > 0:
        return _mix_hex(tokens["profit_text"], tokens["profit"], intensity)
    return _mix_hex(tokens["loss_text"], tokens["loss"], intensity)


def _font_size_for_weight(weight: float) -> float:
    return max(0.66, min(1.85, 0.62 + math.sqrt(max(weight, 0.0)) * 2.0))


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


def _allocation_rows(metrics: PortfolioMetrics, *, max_items: int = 8) -> list[dict[str, Any]]:
    tokens = get_active_theme().tokens()
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
            }
        )
    rows = sorted(rows, key=_sort_key, reverse=True)
    if len(rows) <= max_items:
        return rows
    kept = rows[: max_items - 1]
    other = rows[max_items - 1 :]
    other_value = sum(float(row["value_krw"]) for row in other)
    other_day_change_krw = sum(float(row.get("day_change_krw") or 0.0) for row in other)
    other_previous_value = other_value - other_day_change_krw
    other_day_change_pct = other_day_change_krw / other_previous_value if other_previous_value else None
    kept.append(
        {
            "label": "기타",
            "detail": f"{len(other)}개 항목 합산",
            "value_krw": other_value,
            "weight": other_value / total if total else 0.0,
            "color": _movement_dot_color(other_day_change_pct),
            "heat_color": _heatmap_tone(other_day_change_pct),
            "day_change_pct": other_day_change_pct,
            "day_change_krw": other_day_change_krw,
            "kind": "other",
            "currency": "-",
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


def _heatmap_tiles(rows: list[dict[str, Any]]) -> str:
    tiles = []
    for row in _treemap_layout(rows):
        weight = float(row.get("weight") or 0.0)
        change_pct = row.get("day_change_pct")
        change_text = signed_percentage(change_pct) if change_pct is not None else "-"
        font_size = _font_size_for_weight(weight)
        tile_width = float(row.get("width") or 0.0)
        tile_height = float(row.get("height") or 0.0)
        show_text = weight >= 0.006 and tile_width >= 5 and tile_height >= 5
        label_html = f"<div class='summary-heatmap-name'>{escape(str(row['label']))}</div>" if show_text else ""
        change_html = f"<div class='summary-heatmap-change'>{escape(change_text)}</div>" if show_text else ""
        tiles.append(
            "<div class='summary-heatmap-tile' "
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
            "<td colspan='11'>"
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
        purchase_amount = "-"
        if holding.get("avg_price") is not None:
            purchase_amount = format_price(float(holding.get("avg_price") or 0.0) * float(holding.get("quantity") or 0.0), holding.get("currency"))
        current_price = format_price(holding.get("current_price"), holding.get("currency"))
        day_change = _price_change_text(holding)
        pnl_pct = signed_percentage(item.total_pnl_pct) if item.total_pnl_pct is not None else "-"
        day_change_class = _signed_class(_holding_day_change_price(holding))
        day_change_value = _holding_day_change_price(holding)
        irr = _holding_irr(holding, normalized_transactions, as_of_date=irr_date)
        irr_text = signed_percentage(irr) if irr is not None else "-"
        rows.append(
            "<tr>"
            f"<td class='summary-name'><span class='summary-name-dot' style='background:{color}'></span><span class='summary-name-text'>{label}</span>{_currency_badge(currency)}</td>"
            f"<td>{escape(quantity)}</td>"
            f"<td>{escape(avg_price)}</td>"
            f"<td>{escape(purchase_amount)}</td>"
            f"<td>{escape(current_price)}</td>"
            f"<td class='summary-sparkline-cell'>{_sparkline_html(holding)}</td>"
            f"<td class='{day_change_class}'>{_badge_html(day_change_value, day_change)}</td>"
            f"<td>{_badge_html(item.total_pnl_pct, pnl_pct)}</td>"
            f"<td>{_badge_html(irr, irr_text)}</td>"
            f"<td>{escape(_krw(item.market_value_krw))}</td>"
            f"<td>{escape(percentage(item.weight, digits=2))}</td>"
            "</tr>"
        )
    if metrics.cash_total_krw > 0:
        rows.append(
            "<tr class='summary-section-row summary-section-cash'>"
            "<td colspan='11'>"
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
                f"<td class='summary-name'><span class='summary-name-dot' style='background:{cash_row['color']}'></span><span class='summary-name-text'>{escape(str(cash_row['label']))}</span>{_currency_badge(currency)}</td>"
                f"<td>{escape(quantity)}</td>"
                "<td>-</td><td>-</td>"
                f"<td>{escape(current_price)}</td>"
                "<td>-</td><td>-</td><td>-</td><td>-</td>"
                f"<td>{escape(_krw(float(cash_row['value_krw'])))}</td>"
                f"<td>{escape(percentage(float(cash_row['weight']), digits=2))}</td>"
                "</tr>"
            )
    portfolio_irr = _portfolio_irr(metrics, normalized_transactions, as_of_date=irr_date)
    total_day_text = f"{_signed_text(metrics.day_change_krw, signed_krw)} ({_signed_text(metrics.day_change_pct, signed_percentage)})"
    rows.append(
        "<tr class='summary-total-row'>"
        "<td>합계 (주식 평가금액 + 현금)</td><td>-</td><td>-</td>"
        f"<td>{escape(_krw(metrics.total_cost_krw) if metrics.total_cost_krw else '-')}</td>"
        "<td>-</td>"
        "<td>-</td>"
        f"<td>{_badge_html(metrics.day_change_krw, total_day_text)}</td>"
        f"<td>{_badge_html(metrics.total_pnl_pct, _signed_text(metrics.total_pnl_pct, signed_percentage))}</td>"
        f"<td>{_badge_html(portfolio_irr, signed_percentage(portfolio_irr) if portfolio_irr is not None else '-')}</td>"
        f"<td>{escape(_krw(metrics.total_value_krw))}</td><td>100.00%</td>"
        "</tr>"
    )
    return rows


def _mobile_holding_summary_table(metrics: PortfolioMetrics) -> str:
    rows = []
    for item in sorted(metrics.rows, key=lambda row: row.market_value_krw or 0.0, reverse=True):
        holding = item.holding
        label = instrument_label(holding)
        color = _movement_dot_color(_holding_day_change_price(holding))
        currency = _currency_label(holding.get("currency"))
        quantity = f"{format_number(float(holding.get('quantity') or 0), digits=4, trim=True)}주"
        avg_price = format_price(holding.get("avg_price"), holding.get("currency"))
        current_price = format_price(holding.get("current_price"), holding.get("currency"))
        rows.append(
            "<tr>"
            "<td>"
            f"<div class='summary-mobile-summary-name'><span class='summary-name-dot' style='background:{color}'></span><strong>{escape(label)}</strong>{_currency_badge(currency)}</div>"
            "</td>"
            f"<td>{escape(quantity)}</td>"
            f"<td>{escape(avg_price)}</td>"
            f"<td>{escape(current_price)}</td>"
            f"<td class='summary-mobile-summary-weight'>{escape(percentage(item.weight, digits=2))}</td>"
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
            min-height: 430px;
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
        .summary-heatmap-legend .down:before { background: var(--app-loss); }
        .summary-heatmap-area {
            position: relative;
            flex: 1;
            min-height: 360px;
            width: 100%;
            background: var(--summary-heatmap-bg);
            border: 1px solid var(--summary-heatmap-border);
            border-radius: 7px;
            overflow: hidden;
            box-shadow: var(--app-shadow);
        }
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
            box-shadow: inset 0 -24px 58px var(--token-overlay);
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
        .summary-heatmap-change { font-size: 0.82em; margin-top: 6px; font-weight: 760; font-variant-numeric: tabular-nums; }
        .summary-heatmap-empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--app-muted); }
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
        .summary-col-name { width: 13.5%; }
        .summary-col-qty { width: 7%; }
        .summary-col-avg { width: 8.3%; }
        .summary-col-cost { width: 8.7%; }
        .summary-col-price { width: 8.2%; }
        .summary-col-spark { width: 8.2%; }
        .summary-col-day { width: 11.2%; }
        .summary-col-pnl { width: 8%; }
        .summary-col-irr { width: 7.5%; }
        .summary-col-value { width: 11%; }
        .summary-col-weight { width: 8.4%; }
        .summary-name {
            min-width: 0;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .summary-name-text {
            min-width: 0;
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
        .summary-split-label {
            color: var(--app-muted);
            font-size: 0.92rem;
            font-weight: 760;
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
            border: 1px solid var(--app-border);
            font-size: 0.92em;
        }
        .summary-badge.summary-up { color: var(--summary-up-text); background: var(--summary-up-bg); border-color: var(--summary-up-border); }
        .summary-badge.summary-down { color: var(--summary-down-text); background: var(--summary-down-bg); border-color: var(--summary-down-border); }
        .summary-badge.summary-neutral { color: var(--app-text); background: var(--summary-neutral-badge-bg); }
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
            .summary-heatmap-card { min-height: 360px; }
            .summary-heatmap-area { min-height: 300px; }
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
                min-height: 280px;
            }
            .summary-heatmap-head {
                align-items: flex-start;
                flex-direction: column;
            }
            .summary-heatmap-area {
                min-height: 240px;
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
                padding: 8px 4px;
                text-align: right;
                vertical-align: middle;
                overflow-wrap: anywhere;
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
                overflow-wrap: anywhere;
            }
            .summary-mobile-summary-weight {
                color: var(--app-positive);
                font-weight: 850;
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
            .summary-table td:nth-child(3):before { content: "평균단가"; }
            .summary-table td:nth-child(4):before { content: "매입금액"; }
            .summary-table td:nth-child(5):before { content: "현재가"; }
            .summary-table td:nth-child(6):before { content: "당일 흐름"; }
            .summary-table td:nth-child(7):before { content: "전일 대비"; }
            .summary-table td:nth-child(8):before { content: "평가 수익률"; }
            .summary-table td:nth-child(9):before { content: "IRR"; }
            .summary-table td:nth-child(10):before { content: "평가액"; }
            .summary-table td:nth-child(11):before { content: "자산 비중"; }
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
) -> None:
    _render_styles()
    if metrics.holdings_count == 0 and metrics.cash_total_krw <= 0:
        render_empty_state(
            "아직 포트폴리오 데이터가 없습니다.",
            "먼저 입금 또는 보유종목을 입력하면 총괄현황, 자산 비중, 보유 종목 요약이 표시됩니다.",
        )
        return
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
        f"<span class='summary-legend-title'>{escape(str(row['label']))}{_currency_badge(row.get('currency'))}</span>"
        f"<small>{escape(_krw(float(row['value_krw'])))} · {escape(str(row.get('currency') or '-'))}</small>"
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
            f"<span class='summary-legend-title'>{escape(str(row['label']))}{_currency_badge(row.get('currency'))}</span>"
            f"<small>{escape(str(row['detail']))}</small>"
            "</span>"
            f"<span class='summary-legend-pct'>{escape(percentage(float(row['weight']), digits=2))}</span>"
            "</div>"
            for row in cash_rows
        )
    else:
        cash_legend_rows = "<div class='summary-empty-line'>현금 없음</div>"
    heatmap_tiles = _heatmap_tiles(allocation_rows)
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
                    <div class="summary-heatmap-legend"><span class="up">상승</span><span class="down">하락</span></div>
                </div>
                <div class="summary-heatmap-area">{heatmap_tiles}</div>
            </div>
        </div>
        <div class="summary-split-grid">
            <div class="summary-split-card">
                <div class="summary-split-label">투자자산</div>
                <div class="summary-split-value">{escape(_krw(metrics.total_position_value_krw))}</div>
                <div class="summary-split-sub">주식 평가금액 · 총자산 대비 {escape(percentage(stock_pct, digits=2))}</div>
            </div>
            <div class="summary-split-card">
                <div class="summary-split-label">현금</div>
                <div class="summary-split-value">{escape(_krw(metrics.cash_total_krw))}</div>
                <div class="summary-split-sub">{escape(cash_detail)} · 총자산 대비 {escape(percentage(cash_pct, digits=2))}</div>
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
                        <col class="summary-col-avg" />
                        <col class="summary-col-cost" />
                        <col class="summary-col-price" />
                        <col class="summary-col-spark" />
                        <col class="summary-col-day" />
                        <col class="summary-col-pnl" />
                        <col class="summary-col-irr" />
                        <col class="summary-col-value" />
                        <col class="summary-col-weight" />
                    </colgroup>
                    <thead>
                        <tr>
                            <th>종목명</th>
                            <th>보유 수량</th>
                            <th>평균단가</th>
                            <th>매입금액</th>
                            <th>현재가</th>
                            <th class="summary-sparkline-th">당일 흐름</th>
                            <th>전일대비</th>
                            <th>수익률</th>
                            <th>IRR</th>
                            <th>평가금액</th>
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
