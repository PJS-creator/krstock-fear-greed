from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

import streamlit as st

from portfolio.holdings import PortfolioMetrics

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


def _sort_key(row: dict[str, Any]) -> float:
    return float(row.get("value_krw") or 0)


def _allocation_rows(metrics: PortfolioMetrics, *, max_items: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = metrics.total_value_krw
    for index, item in enumerate(metrics.rows):
        value = item.market_value_krw
        if value is None or value <= 0:
            continue
        rows.append(
            {
                "label": instrument_label(item.holding),
                "detail": instrument_label(item.holding, include_ticker=True),
                "value_krw": value,
                "weight": value / total if total else 0.0,
                "color": deterministic_color(item.holding.get("ticker") or index),
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
                "kind": "cash",
            }
        )
    rows = sorted(rows, key=_sort_key, reverse=True)
    if len(rows) <= max_items:
        return rows
    kept = rows[: max_items - 1]
    other = rows[max_items - 1 :]
    other_value = sum(float(row["value_krw"]) for row in other)
    kept.append(
        {
            "label": "기타",
            "detail": f"{len(other)}개 항목 합산",
            "value_krw": other_value,
            "weight": other_value / total if total else 0.0,
            "color": "#64748B",
            "kind": "other",
        }
    )
    return kept


def _donut_gradient(rows: list[dict[str, Any]]) -> str:
    cursor = 0.0
    stops = []
    for row in rows:
        start = cursor
        cursor += max(float(row["weight"]) * 100, 0)
        stops.append(f"{row['color']} {start:.4f}% {cursor:.4f}%")
    return ", ".join(stops) or f"{SEMANTIC_COLORS['missing']} 0% 100%"


def _coverage_label(metrics: PortfolioMetrics) -> str:
    if metrics.total_position_value_krw <= 0:
        return "보유 종목 없음"
    covered_count = sum(1 for row in metrics.rows if row.cost_basis_krw is not None)
    return f"평단가 입력 {covered_count:,}/{metrics.holdings_count:,}종목"


def _holding_table_rows(metrics: PortfolioMetrics) -> list[str]:
    rows = []
    for item in sorted(metrics.rows, key=lambda row: row.market_value_krw or 0.0, reverse=True):
        holding = item.holding
        label = escape(instrument_label(holding))
        color = deterministic_color(holding.get("ticker") or label)
        quantity = f"{format_number(float(holding.get('quantity') or 0), digits=4, trim=True)}주"
        avg_price = format_price(holding.get("avg_price"), holding.get("currency"))
        pnl_pct = signed_percentage(item.total_pnl_pct) if item.total_pnl_pct is not None else "-"
        pnl_class = _signed_class(item.total_pnl_pct)
        rows.append(
            "<tr>"
            f"<td class='summary-name'><span style='background:{color}'></span>{label}</td>"
            f"<td>{escape(quantity)}</td>"
            f"<td>{escape(avg_price)}</td>"
            f"<td class='{pnl_class}'>{escape(pnl_pct)}</td>"
            f"<td>{escape(_krw(item.market_value_krw))}</td>"
            f"<td>{escape(percentage(item.weight, digits=2))}</td>"
            "</tr>"
        )
    if metrics.cash_total_krw > 0:
        rows.append(
            "<tr>"
            "<td class='summary-name'><span style='background:#8C99A8'></span>현금</td>"
            "<td>-</td><td>-</td><td>-</td>"
            f"<td>{escape(_krw(metrics.cash_total_krw))}</td>"
            f"<td>{escape(percentage(metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else 0, digits=2))}</td>"
            "</tr>"
        )
    rows.append(
        "<tr class='summary-total-row'>"
        "<td>합계 (주식 평가금액 + 현금)</td><td>-</td><td>-</td><td>-</td>"
        f"<td>{escape(_krw(metrics.total_value_krw))}</td><td>100.00%</td>"
        "</tr>"
    )
    return rows


def _kpi_card(title: str, value: str, subtext: str, color: str = "default") -> str:
    return (
        f"<div class='summary-kpi summary-kpi-{color}'>"
        f"<div class='summary-kpi-title'>{escape(title)}</div>"
        f"<div class='summary-kpi-value'>{escape(value)}</div>"
        f"<div class='summary-kpi-sub'>{escape(subtext)}</div>"
        "</div>"
    )


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        .summary-card {
            background: linear-gradient(135deg, #03101E 0%, #071A2A 48%, #020817 100%);
            border: 1px solid rgba(148, 163, 184, 0.34);
            border-radius: 8px;
            color: #E5E7EB;
            padding: 20px;
            box-shadow: 0 18px 54px rgba(2, 8, 23, 0.30);
        }
        .summary-card * { box-sizing: border-box; letter-spacing: 0; }
        .summary-top {
            display: grid;
            grid-template-columns: minmax(260px, 1fr) 300px 220px;
            gap: 12px;
            align-items: stretch;
        }
        .summary-title h2 { margin: 0; font-size: 2.25rem; line-height: 1.08; color: #F8FAFC; }
        .summary-title p { margin: 12px 0 0; color: #CBD5E1; font-size: 1.08rem; }
        .summary-top-box, .summary-panel, .summary-table-wrap, .summary-kpi {
            background: rgba(2, 12, 24, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.28);
            border-radius: 8px;
        }
        .summary-top-box { padding: 14px 18px; }
        .summary-top-label { color: #CBD5E1; font-size: 0.92rem; }
        .summary-date { color: #11E6D5; font-size: 1.55rem; margin-top: 4px; }
        .summary-delta { font-size: 1.45rem; margin-top: 8px; }
        .summary-sub { color: #CBD5E1; font-size: 0.92rem; margin-top: 4px; }
        .summary-main {
            display: grid;
            grid-template-columns: 360px minmax(360px, 1fr);
            gap: 18px;
            margin-top: 16px;
            align-items: center;
        }
        .summary-panel { padding: 18px; }
        .summary-panel h3, .summary-table-wrap h3 { margin: 0 0 16px; color: #F8FAFC; font-size: 1.18rem; }
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
        .summary-legend-total { border-top: 1px solid rgba(148, 163, 184, 0.24); margin-top: 12px; padding-top: 14px; color: #11E6D5; text-align: center; font-size: 1.15rem; }
        .summary-donut-area { display: flex; justify-content: center; align-items: center; min-height: 480px; }
        .summary-donut {
            --donut: #334155 0% 100%;
            width: min(500px, 92vw);
            aspect-ratio: 1;
            border-radius: 50%;
            position: relative;
            background: conic-gradient(var(--donut));
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.42), 0 28px 70px rgba(0, 0, 0, 0.34);
        }
        .summary-donut:after {
            content: "";
            position: absolute;
            inset: 31%;
            border-radius: 50%;
            background: #06111D;
            border: 1px solid rgba(148, 163, 184, 0.26);
        }
        .summary-donut-center {
            position: absolute;
            z-index: 1;
            inset: 35%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
        }
        .summary-donut-center .label { color: #E5E7EB; font-size: 1.2rem; }
        .summary-donut-center .value { color: #11E6D5; font-size: 1.55rem; margin: 8px 0; font-variant-numeric: tabular-nums; }
        .summary-donut-center .split { color: #CBD5E1; border-top: 1px solid rgba(148, 163, 184, 0.30); padding-top: 10px; width: 100%; }
        .summary-table-wrap { margin-top: 16px; overflow: hidden; }
        .summary-table-wrap h3 { padding: 14px 18px; margin: 0; border-bottom: 1px solid rgba(148, 163, 184, 0.26); }
        .summary-table { width: 100%; border-collapse: collapse; font-size: 0.96rem; }
        .summary-table th, .summary-table td { border-bottom: 1px solid rgba(148, 163, 184, 0.18); padding: 10px 12px; text-align: right; font-variant-numeric: tabular-nums; }
        .summary-table th { color: #CBD5E1; font-weight: 650; background: rgba(15, 23, 42, 0.58); }
        .summary-table th:first-child, .summary-table td:first-child { text-align: left; }
        .summary-name { min-width: 220px; }
        .summary-name span { width: 13px; height: 13px; display: inline-block; border-radius: 50%; margin-right: 9px; vertical-align: -1px; }
        .summary-total-row td { color: #F8FAFC; font-weight: 760; background: rgba(15, 23, 42, 0.54); }
        .summary-kpi-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
        .summary-kpi { padding: 16px 18px; min-height: 104px; }
        .summary-kpi-title { color: #CBD5E1; font-size: 0.96rem; }
        .summary-kpi-value { color: #F8FAFC; font-size: 1.35rem; margin-top: 6px; font-variant-numeric: tabular-nums; }
        .summary-kpi-sub { color: #94A3B8; font-size: 0.9rem; margin-top: 4px; }
        .summary-kpi-cyan .summary-kpi-value { color: #11E6D5; }
        .summary-kpi-red .summary-kpi-value, .summary-up { color: #FF4D4F; }
        .summary-kpi-blue .summary-kpi-value, .summary-down { color: #3B82F6; }
        .summary-neutral { color: #CBD5E1; }
        .summary-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; color: #94A3B8; font-size: 0.9rem; }
        @media (max-width: 980px) {
            .summary-top, .summary-main, .summary-kpi-grid { grid-template-columns: 1fr; }
            .summary-donut-area { min-height: 360px; }
            .summary-table-wrap { overflow-x: auto; }
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
) -> None:
    _render_styles()
    allocation_rows = _allocation_rows(metrics)
    stock_pct = metrics.total_position_value_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0
    cash_pct = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0
    day_class = _signed_class(metrics.day_change_krw)
    pnl_class = _signed_class(metrics.total_pnl_krw)
    seed = metrics.total_cost_krw if metrics.total_cost_krw > 0 else None
    seed_label = _krw(seed) if seed is not None else "평단가 필요"
    kpi_cards = [
        _kpi_card("총 자산", _krw(metrics.total_value_krw), f"주식 {percentage(stock_pct, digits=2)} · 현금 {percentage(cash_pct, digits=2)}", "cyan"),
        _kpi_card("주식 평가금액", _krw(metrics.total_position_value_krw), f"{metrics.priced_count:,}/{metrics.holdings_count:,}종목 평가", "default"),
        _kpi_card("현금", _krw(metrics.cash_total_krw), f"{percentage(cash_pct, digits=2)}", "default"),
        _kpi_card("주식 평가이익", _signed_text(metrics.total_pnl_krw, signed_krw), "주식 평가금액 - 총 시드", _kpi_tone(metrics.total_pnl_krw)),
        _kpi_card("주식 수익률", _signed_text(metrics.total_pnl_pct, signed_percentage), _coverage_label(metrics), _kpi_tone(metrics.total_pnl_pct)),
        _kpi_card("금일 손익", _signed_text(metrics.day_change_krw, signed_krw), "최근 제공 가격과 전일 종가 기준", _kpi_tone(metrics.day_change_krw)),
        _kpi_card("전일 대비 수익률", _signed_text(metrics.day_change_pct, signed_percentage), "전일 보유 평가액 대비", _kpi_tone(metrics.day_change_pct)),
        _kpi_card("총 시드", seed_label, _coverage_label(metrics), "default"),
        _kpi_card("적용 환율", f"{format_number(metrics.usd_krw)}원 / USD", "미국 주식 및 달러 현금 환산", "default"),
    ]
    legend_rows = "".join(
        "<div class='summary-legend-row'>"
        f"<span class='summary-dot' style='background:{row['color']}'></span>"
        f"<span class='summary-legend-name'>{escape(str(row['label']))}</span>"
        f"<span class='summary-legend-pct'>{escape(percentage(float(row['weight']), digits=2))}</span>"
        "</div>"
        for row in allocation_rows
    )
    table_rows = "".join(_holding_table_rows(metrics))
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
            <div class="summary-donut-area">
                <div class="summary-donut" style="--donut: {_donut_gradient(allocation_rows)}">
                    <div class="summary-donut-center">
                        <div class="label">총 자산</div>
                        <div class="value">{escape(_krw(metrics.total_value_krw))}</div>
                        <div class="split">주식 {escape(percentage(stock_pct, digits=2))}<br>현금 {escape(percentage(cash_pct, digits=2))}</div>
                    </div>
                </div>
            </div>
        </div>
        <div class="summary-table-wrap">
            <h3>보유 종목 현황</h3>
            <table class="summary-table">
                <thead>
                    <tr>
                        <th>종목명</th>
                        <th>보유 수량</th>
                        <th>평단가 (원/달러)</th>
                        <th>평가 수익률 (%)</th>
                        <th>평가금액 (원)</th>
                        <th>자산 비중 (%)</th>
                    </tr>
                </thead>
                <tbody>{table_rows}</tbody>
            </table>
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
