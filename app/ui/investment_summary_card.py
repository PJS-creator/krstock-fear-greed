from __future__ import annotations

import math
from datetime import date, datetime
from html import escape
from typing import Any

import streamlit as st

from portfolio.holdings import PortfolioMetrics
from portfolio.transactions import normalize_transaction_rows

from .formatters import KST, format_kst, format_number, format_price, instrument_label, percentage, signed_krw, signed_percentage
from .theme import SEMANTIC_COLORS, deterministic_color


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


def _heatmap_tone(change_pct: float | None) -> str:
    if change_pct is None or abs(change_pct) < 1e-12:
        return "#4B5563"
    intensity = min(abs(change_pct) / 0.045, 1.0)
    if change_pct > 0:
        return _mix_hex("#7F2535", "#DC5A5E", intensity)
    return _mix_hex("#1F3D63", "#3B82F6", intensity)


def _font_size_for_weight(weight: float) -> float:
    return max(0.78, min(1.85, 0.72 + math.sqrt(max(weight, 0.0)) * 2.15))


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
    rows: list[dict[str, Any]] = []
    total = metrics.total_value_krw
    for index, item in enumerate(metrics.rows):
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
                "color": deterministic_color(item.holding.get("ticker") or index),
                "heat_color": _heatmap_tone(day_change_pct),
                "day_change_pct": day_change_pct,
                "day_change_krw": item.day_change_krw,
                "kind": "holding",
            }
        )
    if metrics.cash_total_krw > 0:
        rows.append(
            {
                "label": "현금",
                "detail": "원화/달러 현금",
                "value_krw": metrics.cash_total_krw,
                "weight": metrics.cash_total_krw / total if total else 0.0,
                "color": "#8C99A8",
                "heat_color": "#374151",
                "day_change_pct": 0.0,
                "day_change_krw": 0.0,
                "kind": "cash",
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
            "color": "#64748B",
            "heat_color": _heatmap_tone(other_day_change_pct),
            "day_change_pct": other_day_change_pct,
            "day_change_krw": other_day_change_krw,
            "kind": "other",
        }
    )
    return kept


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
        tiles.append(
            "<div class='summary-heatmap-tile' "
            f"style='left:{row['x']:.4f}%;top:{row['y']:.4f}%;width:{row['width']:.4f}%;height:{row['height']:.4f}%;"
            f"background:{row['heat_color']};font-size:{font_size:.2f}rem;'>"
            f"<div class='summary-heatmap-name'>{escape(str(row['label']))}</div>"
            f"<div class='summary-heatmap-change'>{escape(change_text)}</div>"
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
    return f"평단가 입력 {covered_count:,}/{metrics.holdings_count:,}종목"


def _holding_table_rows(
    metrics: PortfolioMetrics,
    *,
    transactions: list[dict[str, Any]] | None = None,
    as_of_date: date | None = None,
) -> list[str]:
    rows = []
    normalized_transactions = _normalized_transactions(transactions)
    irr_date = as_of_date or datetime.now(KST).date()
    for item in sorted(metrics.rows, key=lambda row: row.market_value_krw or 0.0, reverse=True):
        holding = item.holding
        label = escape(instrument_label(holding))
        color = deterministic_color(holding.get("ticker") or label)
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
            f"<td class='summary-name'><span style='background:{color}'></span>{label}</td>"
            f"<td>{escape(quantity)}</td>"
            f"<td>{escape(avg_price)}</td>"
            f"<td>{escape(purchase_amount)}</td>"
            f"<td>{escape(current_price)}</td>"
            f"<td class='{day_change_class}'>{_badge_html(day_change_value, day_change)}</td>"
            f"<td>{_badge_html(item.total_pnl_pct, pnl_pct)}</td>"
            f"<td>{_badge_html(irr, irr_text)}</td>"
            f"<td>{escape(_krw(item.market_value_krw))}</td>"
            f"<td>{escape(percentage(item.weight, digits=2))}</td>"
            "</tr>"
        )
    if metrics.cash_total_krw > 0:
        rows.append(
            "<tr>"
            "<td class='summary-name'><span style='background:#8C99A8'></span>현금</td>"
            "<td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>"
            f"<td>{escape(_krw(metrics.cash_total_krw))}</td>"
            f"<td>{escape(percentage(metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else 0, digits=2))}</td>"
            "</tr>"
        )
    portfolio_irr = _portfolio_irr(metrics, normalized_transactions, as_of_date=irr_date)
    total_day_text = f"{_signed_text(metrics.day_change_krw, signed_krw)} ({_signed_text(metrics.day_change_pct, signed_percentage)})"
    rows.append(
        "<tr class='summary-total-row'>"
        "<td>합계 (주식 평가금액 + 현금)</td><td>-</td><td>-</td>"
        f"<td>{escape(_krw(metrics.total_cost_krw) if metrics.total_cost_krw else '-')}</td>"
        "<td>-</td>"
        f"<td>{_badge_html(metrics.day_change_krw, total_day_text)}</td>"
        f"<td>{_badge_html(metrics.total_pnl_pct, _signed_text(metrics.total_pnl_pct, signed_percentage))}</td>"
        f"<td>{_badge_html(portfolio_irr, signed_percentage(portfolio_irr) if portfolio_irr is not None else '-')}</td>"
        f"<td>{escape(_krw(metrics.total_value_krw))}</td><td>100.00%</td>"
        "</tr>"
    )
    return rows


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
            background: radial-gradient(circle at 18% 0%, rgba(22, 55, 92, 0.34), transparent 38%),
                        linear-gradient(135deg, #050B16 0%, #091321 52%, #030713 100%);
            border: 1px solid rgba(148, 163, 184, 0.26);
            border-radius: 8px;
            color: #E5E7EB;
            padding: 20px;
            box-shadow: 0 20px 60px rgba(2, 8, 23, 0.42);
        }
        .summary-card * { box-sizing: border-box; letter-spacing: 0; }
        .summary-top {
            display: grid;
            grid-template-columns: minmax(260px, 1fr) 300px 220px;
            gap: 12px;
            align-items: stretch;
        }
        .summary-title h2 { margin: 0; font-size: 2.35rem; line-height: 1.08; color: #F8FAFC; font-weight: 900; }
        .summary-title p { margin: 12px 0 0; color: #CBD5E1; font-size: 1.08rem; }
        .summary-top-box, .summary-panel, .summary-table-wrap, .summary-kpi {
            background: linear-gradient(180deg, rgba(20, 31, 51, 0.92), rgba(9, 17, 31, 0.92));
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 8px;
        }
        .summary-top-box { padding: 16px 18px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.04); }
        .summary-top-label { color: #CBD5E1; font-size: 0.92rem; }
        .summary-date { color: #34D399; font-size: 1.64rem; margin-top: 4px; font-weight: 850; }
        .summary-delta { font-size: 1.82rem; margin-top: 8px; font-weight: 900; }
        .summary-sub { color: #CBD5E1; font-size: 0.92rem; margin-top: 4px; }
        .summary-main {
            display: grid;
            grid-template-columns: 360px minmax(360px, 1fr);
            gap: 18px;
            margin-top: 16px;
            align-items: stretch;
        }
        .summary-panel { padding: 18px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.04); }
        .summary-panel h3, .summary-table-wrap h3 { margin: 0 0 16px; color: #F8FAFC; font-size: 1.24rem; font-weight: 850; }
        .summary-legend-row {
            display: grid;
            grid-template-columns: 20px minmax(0, 1fr) 74px;
            gap: 8px;
            align-items: center;
            padding: 8px 0;
            color: #E5E7EB;
            font-size: 1.02rem;
        }
        .summary-dot { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
        .summary-legend-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .summary-legend-pct { text-align: right; font-variant-numeric: tabular-nums; }
        .summary-legend-total { border-top: 1px solid rgba(148, 163, 184, 0.24); margin-top: 12px; padding-top: 14px; color: #34D399; text-align: center; font-size: 1.18rem; font-weight: 850; }
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
        .summary-heatmap-legend { display: flex; gap: 12px; color: #CBD5E1; font-size: 0.9rem; }
        .summary-heatmap-legend span:before {
            content: "";
            width: 9px;
            height: 9px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
        }
        .summary-heatmap-legend .up:before { background: #D94B4B; }
        .summary-heatmap-legend .down:before { background: #2F80ED; }
        .summary-heatmap-area {
            position: relative;
            flex: 1;
            min-height: 360px;
            width: 100%;
            background: #050A13;
            border: 1px solid #000;
            border-radius: 7px;
            overflow: hidden;
            box-shadow: 0 24px 58px rgba(0, 0, 0, 0.26);
        }
        .summary-heatmap-tile {
            position: absolute;
            border: 1px solid #000;
            color: #F8FAFC;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            line-height: 1.15;
            padding: 6px;
            overflow: hidden;
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.56);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -24px 58px rgba(0,0,0,0.16);
        }
        .summary-heatmap-name {
            font-weight: 900;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .summary-heatmap-change { font-size: 0.82em; margin-top: 6px; font-weight: 760; font-variant-numeric: tabular-nums; }
        .summary-heatmap-empty { position: absolute; inset: 0; display: grid; place-items: center; color: #CBD5E1; }
        .summary-table-wrap { margin-top: 16px; overflow: hidden; }
        .summary-table-wrap h3 { padding: 16px 20px; margin: 0; border-bottom: 1px solid rgba(148, 163, 184, 0.24); }
        .summary-table-scroll { overflow-x: auto; }
        .summary-table { width: 100%; min-width: 1120px; border-collapse: collapse; font-size: 0.93rem; }
        .summary-table th, .summary-table td { border-bottom: 1px solid rgba(148, 163, 184, 0.20); padding: 11px 12px; text-align: right; font-variant-numeric: tabular-nums; }
        .summary-table th { color: #CBD5E1; font-weight: 760; background: rgba(15, 23, 42, 0.72); }
        .summary-table tbody tr:not(.summary-total-row):hover td { background: rgba(59, 130, 246, 0.10); }
        .summary-table th:first-child, .summary-table td:first-child { text-align: left; }
        .summary-name { min-width: 220px; }
        .summary-name span { width: 13px; height: 13px; display: inline-block; border-radius: 50%; margin-right: 9px; vertical-align: -1px; }
        .summary-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 68px;
            padding: 4px 8px;
            border-radius: 999px;
            font-weight: 820;
            line-height: 1.15;
            white-space: nowrap;
            border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .summary-badge.summary-up { color: #FEE2E2; background: rgba(220, 90, 94, 0.36); border-color: rgba(248, 113, 113, 0.38); }
        .summary-badge.summary-down { color: #DBEAFE; background: rgba(59, 130, 246, 0.28); border-color: rgba(96, 165, 250, 0.34); }
        .summary-badge.summary-neutral { color: #E5E7EB; background: rgba(75, 85, 99, 0.35); }
        .summary-total-row td { color: #F8FAFC; font-weight: 800; background: rgba(30, 41, 59, 0.70); }
        .summary-kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
        .summary-kpi { padding: 17px 18px; min-height: 112px; display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 12px; align-items: start; }
        .summary-kpi-icon {
            width: 34px;
            height: 34px;
            border-radius: 9px;
            display: grid;
            place-items: center;
            color: #C7D2FE;
            background: rgba(59, 130, 246, 0.16);
            border: 1px solid rgba(147, 197, 253, 0.18);
            font-weight: 900;
            font-size: 0.84rem;
        }
        .summary-kpi-title { color: #CBD5E1; font-size: 0.96rem; }
        .summary-kpi-value { color: #F8FAFC; font-size: 1.58rem; font-weight: 900; margin-top: 6px; font-variant-numeric: tabular-nums; }
        .summary-kpi-sub { color: #94A3B8; font-size: 0.9rem; margin-top: 4px; }
        .summary-kpi-cyan .summary-kpi-value { color: #34D399; }
        .summary-kpi-cyan .summary-kpi-icon { color: #A7F3D0; background: rgba(16, 185, 129, 0.16); border-color: rgba(52, 211, 153, 0.26); }
        .summary-kpi-red .summary-kpi-value, .summary-up { color: #F87171; }
        .summary-kpi-red .summary-kpi-icon { color: #FECACA; background: rgba(220, 90, 94, 0.18); border-color: rgba(248, 113, 113, 0.28); }
        .summary-kpi-blue .summary-kpi-value, .summary-down { color: #60A5FA; }
        .summary-kpi-blue .summary-kpi-icon { color: #BFDBFE; background: rgba(59, 130, 246, 0.18); border-color: rgba(96, 165, 250, 0.28); }
        .summary-neutral { color: #CBD5E1; }
        .summary-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; color: #94A3B8; font-size: 0.9rem; }
        @media (max-width: 980px) {
            .summary-top, .summary-main, .summary-kpi-grid { grid-template-columns: 1fr; }
            .summary-heatmap-card { min-height: 360px; }
            .summary-heatmap-area { min-height: 300px; }
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
    allocation_rows = _allocation_rows(metrics)
    as_of_date = _as_of_date(last_refresh)
    stock_pct = metrics.total_position_value_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0
    cash_pct = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0
    day_class = _signed_class(metrics.day_change_krw)
    pnl_class = _signed_class(metrics.total_pnl_krw)
    seed = metrics.total_cost_krw if metrics.total_cost_krw > 0 else None
    seed_label = _krw(seed) if seed is not None else "평단가 필요"
    kpi_cards = [
        _kpi_card("총 자산", _krw(metrics.total_value_krw), f"주식 {percentage(stock_pct, digits=2)} · 현금 {percentage(cash_pct, digits=2)}", "cyan", "₩"),
        _kpi_card("주식 평가금액", _krw(metrics.total_position_value_krw), f"{metrics.priced_count:,}/{metrics.holdings_count:,}종목 평가", "default", "주"),
        _kpi_card("현금", _krw(metrics.cash_total_krw), f"{percentage(cash_pct, digits=2)}", "default", "$"),
        _kpi_card("주식 평가이익", _signed_text(metrics.total_pnl_krw, signed_krw), "주식 평가금액 - 총 시드", _kpi_tone(metrics.total_pnl_krw), "P/L"),
        _kpi_card("주식 수익률", _signed_text(metrics.total_pnl_pct, signed_percentage), _coverage_label(metrics), _kpi_tone(metrics.total_pnl_pct), "%"),
        _kpi_card("금일 손익", _signed_text(metrics.day_change_krw, signed_krw), "최근 제공 가격과 전일 종가 기준", _kpi_tone(metrics.day_change_krw), "D"),
        _kpi_card("전일 대비 수익률", _signed_text(metrics.day_change_pct, signed_percentage), "전일 보유 평가액 대비", _kpi_tone(metrics.day_change_pct), "Δ"),
        _kpi_card("총 시드", seed_label, _coverage_label(metrics), "default", "Σ"),
        _kpi_card("적용 환율", f"{format_number(metrics.usd_krw)}원 / USD", "미국 주식 및 달러 현금 환산", "default", "FX"),
    ]
    legend_rows = "".join(
        "<div class='summary-legend-row'>"
        f"<span class='summary-dot' style='background:{row['color']}'></span>"
        f"<span class='summary-legend-name'>{escape(str(row['label']))}</span>"
        f"<span class='summary-legend-pct'>{escape(percentage(float(row['weight']), digits=2))}</span>"
        "</div>"
        for row in allocation_rows
    )
    heatmap_tiles = _heatmap_tiles(allocation_rows)
    table_rows = "".join(_holding_table_rows(metrics, transactions=transactions, as_of_date=as_of_date))
    html = f"""
    <div class="summary-card">
        <div class="summary-top">
            <div class="summary-title">
                <h2>포트폴리오 현황</h2>
                <p>{escape(portfolio_name)} · 총 자산 기준 (주식 평가금액 + 현금)</p>
            </div>
            <div class="summary-top-box">
                <div class="summary-top-label">포트폴리오 업데이트 기준일</div>
                <div class="summary-date">{escape(_display_date(last_refresh))}</div>
                <div class="summary-sub">최근 제공 가격 기준</div>
            </div>
            <div class="summary-top-box">
                <div class="summary-top-label">전일 대비</div>
                <div class="summary-delta {day_class}">{escape(_signed_text(metrics.day_change_krw, signed_krw))}</div>
                <div class="summary-sub {day_class}">{escape(_signed_text(metrics.day_change_pct, signed_percentage))}</div>
            </div>
        </div>
        <div class="summary-main">
            <div class="summary-panel">
                <h3>자산 구성 비중 <span class="summary-sub">(총 자산 기준)</span></h3>
                {legend_rows}
                <div class="summary-legend-total">총 100%</div>
            </div>
            <div class="summary-panel summary-heatmap-card">
                <div class="summary-heatmap-head">
                    <h3>자산 구성 및 성과 <span class="summary-sub">(전일 대비 기준)</span></h3>
                    <div class="summary-heatmap-legend"><span class="up">상승</span><span class="down">하락</span></div>
                </div>
                <div class="summary-heatmap-area">{heatmap_tiles}</div>
            </div>
        </div>
        <div class="summary-table-wrap">
            <h3>보유 종목 현황</h3>
            <div class="summary-table-scroll">
                <table class="summary-table">
                    <thead>
                        <tr>
                            <th>종목명</th>
                            <th>보유 수량</th>
                            <th>평단가 (원/달러)</th>
                            <th>매입금액</th>
                            <th>현재 주가</th>
                            <th>전일 대비 증감</th>
                            <th>평가 수익률 (%)</th>
                            <th>연환산수익률 (IRR)</th>
                            <th>평가금액 (원)</th>
                            <th>자산 비중 (%)</th>
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
            <span>평가 수익률은 입력한 매입 평단가 기준입니다.</span>
            <span>수수료 및 세금 비반영</span>
        </div>
    </div>
    """
    if metrics.holdings_count == 0 and metrics.cash_total_krw <= 0:
        st.info("보유자산과 현금을 입력하면 투자 총괄 카드가 표시됩니다.")
        return
    st.markdown(html, unsafe_allow_html=True)
