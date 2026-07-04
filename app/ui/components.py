from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from html import escape
from uuid import uuid4

import pandas as pd
import streamlit as st

from portfolio.diagnostics import calculate_diagnostics
from portfolio.history import PortfolioHistoryRecord
from portfolio.holdings import PortfolioMetrics
from portfolio.sample_data import sample_portfolio

from .formatters import compact_krw, format_number, format_price, full_krw, instrument_label, percentage, signed_krw, signed_percentage
from .stability import begin_ui_action, request_app_rerun
from .status import aggregate_price_statuses, build_price_log_rows, present_diagnostic, quote_status_label, split_diagnostics
from .theme import DIMENSIONS, chart_config

PENDING_PORTFOLIO_STATE_KEY = "pending_portfolio_state"
LOGGER = logging.getLogger(__name__)


def render_plotly_chart(fig, *, key: str) -> None:
    st.plotly_chart(fig, use_container_width=True, theme=None, config=chart_config(), key=key)


def render_badge(label: str, *, tone: str = "neutral") -> None:
    tone = tone if tone in {"success", "warning", "danger", "info", "neutral"} else "neutral"
    st.markdown(f"<span class='app-badge app-badge-{tone}'>{escape(label)}</span>", unsafe_allow_html=True)


def render_metric_card(
    title: str,
    value: object,
    *,
    delta: object | None = None,
    status: str = "neutral",
    help_text: str | None = None,
) -> None:
    status = status if status in {"success", "warning", "danger", "info", "neutral"} else "neutral"
    delta_html = f"<div class='app-metric-delta'>{escape(str(delta))}</div>" if delta not in (None, "") else ""
    help_html = f"<div class='app-metric-help'>{escape(help_text)}</div>" if help_text else ""
    st.markdown(
        (
            f"<div class='app-metric-card app-metric-{status}'>"
            f"<div class='app-metric-title'>{escape(title)}</div>"
            f"<div class='app-metric-value'>{escape(str(value))}</div>"
            f"{delta_html}"
            f"{help_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_app_header(
    *,
    title: str,
    status_text: str,
    save_status_text: str,
    render_theme_selector: Callable[[], None] | None = None,
    status_tone: str = "neutral",
    refresh_disabled: bool = False,
    retry_disabled: bool = False,
    save_disabled: bool = True,
    show_retry: bool = False,
    show_save: bool = False,
) -> dict[str, bool]:
    if render_theme_selector is not None:
        render_theme_selector()
    tone = status_tone if status_tone in {"success", "warning", "danger", "info", "neutral"} else "neutral"
    left, middle, right = st.columns([2.0, 2.5, 1.35], vertical_alignment="center")
    with left:
        st.title(title)
    with middle:
        st.markdown(
            (
                "<div class='app-header-status'>"
                f"<span class='app-badge app-badge-{tone}'>{escape(status_text)}</span>"
                f"<span class='app-header-save'>{escape(save_status_text)}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with right:
        refresh_clicked = st.button("가격·환율 갱신", type="primary", width="stretch", icon=":material/refresh:", key="app_header_refresh", disabled=refresh_disabled)
        retry_clicked = False
        if show_retry:
            retry_clicked = st.button("실패 재시도", width="stretch", icon=":material/replay:", key="app_header_retry", disabled=retry_disabled)
        save_clicked = False
        if show_save:
            save_clicked = st.button("포트폴리오 저장", disabled=save_disabled, width="stretch", icon=":material/save:", key="app_header_save")
    return {"refresh": refresh_clicked, "retry": retry_clicked, "save": save_clicked}


def render_empty_state(
    title: str,
    message: str,
    *,
    primary_label: str | None = None,
    primary_key: str | None = None,
    secondary_label: str | None = None,
    secondary_key: str | None = None,
) -> tuple[bool, bool]:
    st.markdown(
        (
            "<div class='app-empty-state'>"
            f"<div class='app-empty-title'>{escape(title)}</div>"
            f"<div class='app-empty-message'>{escape(message)}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    primary_clicked = False
    secondary_clicked = False
    if primary_label or secondary_label:
        cols = st.columns(2 if primary_label and secondary_label else 1)
        if primary_label:
            primary_clicked = cols[0].button(primary_label, type="primary", key=primary_key, use_container_width=True)
        if secondary_label:
            target = cols[1] if primary_label else cols[0]
            secondary_clicked = target.button(secondary_label, key=secondary_key, use_container_width=True)
    return primary_clicked, secondary_clicked


def render_page_header(
    title: str,
    description: str,
    *,
    status_text: str = "",
    save_status_text: str = "",
) -> None:
    status_html = f"<span class='app-badge app-badge-info'>{escape(status_text)}</span>" if status_text else ""
    save_html = f"<span class='muted-text'>{escape(save_status_text)}</span>" if save_status_text else ""
    st.markdown(
        (
            "<div class='app-page-header'>"
            "<div>"
            f"<h2>{escape(title)}</h2>"
            f"<p>{escape(description)}</p>"
            "</div>"
            f"<div class='app-page-header-status'>{status_html}{save_html}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _tone_class(value: float | None) -> str:
    if value is None or value == 0:
        return "value-neutral"
    return "value-positive" if value > 0 else "value-negative"


def render_total_asset_hero(
    *,
    total_asset_krw: float,
    day_change_krw: float | None,
    day_change_pct: float | None,
    status_text: str,
    last_refresh_text: str,
    sample_mode: bool = False,
) -> None:
    badge = "<span class='app-badge app-badge-warning'>샘플</span>" if sample_mode else ""
    change_text = f"{signed_krw(day_change_krw)} · {signed_percentage(day_change_pct)}" if day_change_krw is not None else "일간 변동 데이터 부족"
    st.markdown(
        (
            "<section class='hero-card'>"
            "<div class='hero-main'>"
            "<div class='muted-text'>총자산</div>"
            f"<div class='hero-total'>{escape(full_krw(total_asset_krw))}</div>"
            f"<div class='hero-change {_tone_class(day_change_krw)}'>{escape(change_text)}</div>"
            "</div>"
            "<div class='hero-side'>"
            f"{badge}"
            f"<div><span class='muted-text'>가격·환율</span><strong>{escape(status_text)}</strong></div>"
            f"<div><span class='muted-text'>마지막 갱신</span><strong>{escape(last_refresh_text)}</strong></div>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_action_nav(
    items: list[tuple[str, str, str]],
    *,
    active_key: str | None = None,
    state_key: str | None = None,
) -> str | None:
    selected = None
    columns = st.columns(len(items))
    for column, (key, label, caption) in zip(columns, items):
        button_type = "primary" if key == active_key else "secondary"
        with column:
            if st.button(label, key=f"quick_nav_{key}", type=button_type, use_container_width=True, help=caption):
                selected = key
                if state_key:
                    st.session_state[state_key] = key
    return selected


def render_segmented_control(
    label: str,
    options: list[str],
    *,
    key: str,
    default: str | None = None,
) -> str:
    if hasattr(st, "segmented_control"):
        value = st.segmented_control(label, options=options, default=default or options[0], key=key)
        return str(value or default or options[0])
    index = options.index(default) if default in options else 0
    return str(st.radio(label, options=options, index=index, horizontal=True, key=key))


def render_section_card(title: str, *, help_text: str | None = None, action_label: str | None = None) -> None:
    help_html = f"<p>{escape(help_text)}</p>" if help_text else ""
    action_html = f"<span class='app-badge'>{escape(action_label)}</span>" if action_label else ""
    st.markdown(
        (
            "<div class='section-card-heading'>"
            "<div>"
            f"<h3>{escape(title)}</h3>"
            f"{help_html}"
            "</div>"
            f"{action_html}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _initials(value: str) -> str:
    text = "".join(part[0] for part in value.replace("-", " ").split() if part)
    return (text or value[:2] or "?").upper()[:2]


def render_asset_row(row: Mapping[str, object]) -> None:
    name = str(row.get("name") or row.get("display_name") or row.get("ticker") or "-")
    ticker = str(row.get("ticker") or "")
    market = str(row.get("market") or "")
    currency = str(row.get("currency") or "")
    quantity = format_number(float(row.get("quantity") or 0.0), digits=4, trim=True)
    value_krw = full_krw(float(row.get("value_krw") or 0.0))
    pnl = row.get("total_pnl_krw")
    pnl_text = signed_krw(pnl) if pnl is not None else "손익 데이터 부족"
    pnl_pct = row.get("total_pnl_pct")
    pct_text = signed_percentage(pnl_pct) if pnl_pct is not None else "-"
    status = str(row.get("status") or "")
    st.markdown(
        (
            "<div class='asset-row'>"
            f"<div class='asset-icon'>{escape(_initials(ticker or name))}</div>"
            "<div class='asset-main'>"
            f"<strong>{escape(name)}</strong>"
            f"<span>{escape(market)} · {escape(ticker)} · {escape(quantity)}주 · {escape(currency)}</span>"
            "</div>"
            "<div class='asset-values'>"
            f"<strong>{escape(value_krw)}</strong>"
            f"<span class='{_tone_class(float(pnl) if pnl is not None else None)}'>{escape(pnl_text)} · {escape(pct_text)}</span>"
            f"<small>{escape(status)}</small>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_cash_row(row: Mapping[str, object]) -> None:
    currency = str(row.get("currency") or "")
    amount = float(row.get("amount") or 0.0)
    value_krw = float(row.get("value_krw") or 0.0)
    weight = row.get("weight")
    amount_text = f"{format_number(amount)} {currency}" if currency == "USD" else f"{format_number(amount)}원"
    st.markdown(
        (
            "<div class='asset-row cash-row'>"
            f"<div class='asset-icon cash-icon'>{escape(currency[:1] or 'C')}</div>"
            "<div class='asset-main'>"
            f"<strong>{'달러 현금' if currency == 'USD' else '원화 현금'}</strong>"
            f"<span>{escape(amount_text)}</span>"
            "</div>"
            "<div class='asset-values'>"
            f"<strong>{escape(full_krw(value_krw))}</strong>"
            f"<span>총자산 {escape(percentage(weight))}</span>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_profit_summary_card(summary: Mapping[str, object], *, detail: bool = False) -> None:
    items = [
        ("평가수익", summary.get("evaluation_profit_krw"), summary.get("evaluation_profit_pct")),
        ("실현수익", summary.get("realized_profit_krw"), None),
        ("배당/이자", summary.get("dividend_interest_krw"), None),
        ("수수료/세금", summary.get("fees_taxes_krw"), None),
        ("합계", summary.get("total_profit_krw"), summary.get("simple_return")),
    ]
    cards = []
    for label, value, pct_value in items:
        if value is None:
            value_text = "데이터 부족"
            tone = "value-neutral"
        elif label == "수수료/세금":
            value_text = full_krw(float(value))
            tone = "value-neutral"
        else:
            value_text = signed_krw(float(value))
            tone = _tone_class(float(value))
        pct_text = signed_percentage(pct_value) if pct_value is not None else ""
        cards.append(
            "<div class='profit-card'>"
            f"<span>{escape(label)}</span>"
            f"<strong class='{tone}'>{escape(value_text)}</strong>"
            f"<small>{escape(pct_text)}</small>"
            "</div>"
        )
    st.markdown("<div class='profit-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
    if detail:
        reasons = summary.get("insufficient_reasons") or []
        for reason in reasons:
            st.caption(str(reason))


def render_timeline_event(event: Mapping[str, object]) -> None:
    tags = event.get("tags") or []
    tag_html = "".join(f"<span class='app-badge'>{escape(str(tag))}</span>" for tag in tags)
    amount = event.get("amount")
    amount_text = ""
    if amount is not None:
        amount_text = format_price(amount, event.get("currency"))
    cash_impact = event.get("cash_impact")
    cash_text = signed_krw(cash_impact) if isinstance(cash_impact, (int, float)) else ""
    st.markdown(
        (
            "<div class='timeline-event'>"
            "<div class='timeline-dot'></div>"
            "<div class='timeline-body'>"
            f"<div class='timeline-date'>{escape(str(event.get('event_date') or ''))}</div>"
            f"<strong>{escape(str(event.get('title') or ''))}</strong>"
            f"<p>{escape(str(event.get('subtitle') or ''))}</p>"
            f"<div class='timeline-meta'><span>{escape(str(event.get('event_type') or ''))}</span><span>{escape(amount_text)}</span><span>{escape(cash_text)}</span>{tag_html}</div>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_info_box(title: str, message: str) -> None:
    st.markdown(
        f"<div class='app-box app-box-info'><strong>{escape(title)}</strong><span>{escape(message)}</span></div>",
        unsafe_allow_html=True,
    )


def render_warning_box(title: str, message: str) -> None:
    st.markdown(
        f"<div class='app-box app-box-warning'><strong>{escape(title)}</strong><span>{escape(message)}</span></div>",
        unsafe_allow_html=True,
    )


def render_error_box(title: str, message: str) -> None:
    st.markdown(
        f"<div class='app-box app-box-danger'><strong>{escape(title)}</strong><span>{escape(message)}</span></div>",
        unsafe_allow_html=True,
    )


def safe_render_section(name: str, render_fn: Callable[[], None], *, show_debug: bool | None = None) -> bool:
    try:
        render_fn()
        return True
    except Exception as exc:
        error_id = uuid4().hex[:10]
        LOGGER.exception("ui_section_error id=%s section=%s type=%s message=%s", error_id, name, type(exc).__name__, exc)
        render_error_box(
            "이 영역을 불러오는 중 문제가 발생했습니다.",
            f"{name} 화면을 다시 열거나 새로고침해 주세요. 오류 ID: {error_id}",
        )
        debug_enabled = show_debug if show_debug is not None else os.environ.get("DEBUG_UI", "").strip().lower() in {"1", "true", "yes"}
        if debug_enabled:
            st.exception(exc)
        return False


def render_empty_portfolio() -> None:
    st.info(
        "보유 종목이 아직 없습니다. 1) 사용자 입력 탭에서 매입/매도 거래를 입력하고 2) 거래 미리보기 후 반영한 뒤 3) 가격 갱신, 현금·환율 입력, 저장 순서로 진행하세요."
    )
    st.caption("샘플은 기능 확인용 가상 데이터이며 실제 보유 내역이 아닙니다.")
    if st.button("샘플 불러오기", key="load_sample_portfolio"):
        if not begin_ui_action("load_legacy_sample_portfolio"):
            return
        positions, quotes, usd_krw, cash_krw = sample_portfolio()
        rows = []
        for position in positions:
            quote = quotes.get((position.market, position.symbol))
            rows.append(
                {
                    "market": position.market,
                    "ticker": position.symbol,
                    "display_name": position.name,
                    "currency": position.currency,
                    "quantity": position.quantity,
                    "avg_price": position.avg_price,
                    "target_weight": position.target_weight,
                    "strategy_tag": position.strategy_tag,
                    "account_name": position.account_name,
                    "current_price": quote.price if quote else None,
                    "previous_close": quote.previous_close if quote else None,
                    "quote_status": "manual" if quote else "missing",
                    "fetched_at": quote.fetched_at.isoformat() if quote else None,
                    "provider": "sample",
                }
            )
        st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
            "holdings_rows": rows,
            "portfolio_transactions": [],
            "cash_krw": cash_krw,
            "cash_usd": 0.0,
            "usd_krw": usd_krw,
            "fx_status_message": "샘플 USD/KRW 환율",
            "fx_fetched_at": None,
            "mark_clean": False,
        }
        request_app_rerun()


def _history_chart_data(records: list[PortfolioHistoryRecord] | None) -> list[float] | None:
    if not records or len(records) < 2:
        return None
    return [record.total_value_krw for record in records[-24:]]


def render_kpi_cards(metrics: PortfolioMetrics, *, history_records: list[PortfolioHistoryRecord] | None = None) -> None:
    total_kwargs = {}
    chart_data = _history_chart_data(history_records)
    if chart_data:
        total_kwargs = {"chart_data": chart_data, "chart_type": "line"}
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "총자산",
        compact_krw(metrics.total_value_krw),
        help=f"KRW 환산 총자산입니다. 전체 금액: {full_krw(metrics.total_value_krw)}",
        border=True,
        **total_kwargs,
    )
    col2.metric(
        "오늘 변동",
        signed_krw(metrics.day_change_krw),
        delta=signed_percentage(metrics.day_change_pct) if metrics.day_change_pct is not None else None,
        help=f"최근 제공 가격과 전일 종가 차이로 계산합니다. 전체 금액: {full_krw(metrics.day_change_krw)}",
        border=True,
    )
    cash_weight = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else None
    col3.metric(
        "총현금",
        compact_krw(metrics.cash_total_krw),
        delta=f"총자산 대비 {percentage(cash_weight)}" if cash_weight is not None else None,
        delta_color="off",
        help=f"KRW 현금과 USD 현금을 USD/KRW로 환산한 금액입니다. 전체 금액: {full_krw(metrics.cash_total_krw)}",
        border=True,
    )
    col4.metric(
        "USD 노출도",
        percentage(metrics.usd_exposure_pct),
        delta=full_krw(metrics.usd_exposure_krw),
        delta_color="off",
        help="USD 현금과 USD 표시 자산의 KRW 환산 비중입니다.",
        border=True,
    )


def render_cost_basis_note(metrics: PortfolioMetrics) -> None:
    if metrics.total_pnl_krw is None or metrics.cost_basis_coverage <= 0:
        st.caption("평균 매수가가 없어 총손익과 총수익률은 표시하지 않습니다.")
        return
    st.caption(
        f"원가 정보 범위 {percentage(metrics.cost_basis_coverage)} · "
        f"원가 정보가 있는 종목 기준 총손익 {full_krw(metrics.total_pnl_krw)}, 총수익률 {signed_percentage(metrics.total_pnl_pct)}"
    )


def render_price_update_log(statuses: list[object], holdings_rows: list[dict[str, object]]) -> None:
    if not statuses:
        return
    summary = aggregate_price_statuses(statuses)
    if summary.has_issues:
        st.warning(f"가격 갱신 완료 · {summary.detail_text}")
    else:
        st.success(f"가격 갱신 완료 · {summary.short_text}")
    rows = build_price_log_rows(statuses, holdings_rows)
    with st.expander(f"데이터 업데이트 상세 · 성공 {summary.success} / 캐시 {summary.cached} / 실패 {summary.failed}", expanded=False):
        issue_only = st.checkbox("실패·이전저장값·미조회만 보기", value=summary.has_issues, key="price_log_issue_only")
        visible_rows = [row for row in rows if row["raw_status"] in {"stale", "failed", "missing", "missing_api_key"}] if issue_only else rows
        if not visible_rows:
            st.caption("확인할 실패 항목이 없습니다.")
            return
        frame = pd.DataFrame(visible_rows).drop(columns=["raw_status"])
        st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=min(DIMENSIONS.max_table_height, 90 + len(frame) * DIMENSIONS.row_height),
        )


def render_diagnostics(metrics: PortfolioMetrics) -> None:
    presentations = [
        present_diagnostic(item, priced_count=metrics.priced_count, holdings_count=metrics.holdings_count)
        for item in calculate_diagnostics(metrics)
    ]
    primary, details = split_diagnostics(presentations)
    cols = st.columns(3)
    for index, item in enumerate(primary):
        with cols[index % 3]:
            st.metric(
                item.label,
                item.value,
                delta=item.severity_label,
                delta_color="off",
                help=item.help_text,
                border=True,
            )
    if details:
        with st.expander("세부 진단", expanded=False):
            for item in details:
                st.metric(item.label, item.value, delta=item.severity_label, delta_color="off", help=item.help_text, border=True)


def render_single_currency_exposure(metrics: PortfolioMetrics) -> None:
    if metrics.total_value_krw <= 0:
        st.info("통화 노출도는 평가 가능한 자산이 있을 때 표시됩니다.")
        return
    usd_pct = metrics.usd_exposure_pct
    krw_pct = 1 - usd_pct
    dominant = "USD" if usd_pct >= krw_pct else "KRW"
    value = usd_pct if dominant == "USD" else krw_pct
    st.metric(
        "통화 노출",
        f"{dominant} {percentage(value)}",
        delta=full_krw(metrics.usd_exposure_krw if dominant == "USD" else metrics.total_value_krw - metrics.usd_exposure_krw),
        delta_color="off",
        help="통화가 하나뿐이거나 한쪽 노출만 있을 때는 차트 대신 요약으로 표시합니다.",
        border=True,
    )


def render_contribution_summary(metrics: PortfolioMetrics) -> None:
    rows = [row for row in metrics.rows if row.day_change_krw is not None and row.day_change_krw != 0]
    if not rows:
        return
    best = max(rows, key=lambda row: row.day_change_krw or 0.0)
    worst = min(rows, key=lambda row: row.day_change_krw or 0.0)
    col1, col2 = st.columns(2)
    col1.metric(
        "최대 상승 기여",
        instrument_label(best.holding),
        delta=signed_krw(best.day_change_krw),
        help=instrument_label(best.holding, include_ticker=True),
        border=True,
    )
    col2.metric(
        "최대 하락 기여",
        instrument_label(worst.holding),
        delta=signed_krw(worst.day_change_krw),
        help=instrument_label(worst.holding, include_ticker=True),
        border=True,
    )


def status_label(status: object) -> str:
    return quote_status_label(status)
