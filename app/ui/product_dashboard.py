from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import date
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from portfolio.allocation_view import ALLOCATION_PERSPECTIVES, AllocationViewModel, build_allocation_view_model
from portfolio.dashboard_view import ProfitSummaryView, build_dashboard_view_model, build_profit_summary_view
from portfolio.holdings import PortfolioMetrics
from portfolio.journal import build_journal_events, filter_journal_events, normalize_journal_notes

from .charts import apply_chart_layout
from .components import (
    render_action_nav,
    render_asset_row,
    render_cash_row,
    render_empty_state,
    render_page_header,
    render_plotly_chart,
    render_profit_summary_card,
    render_section_card,
    render_segmented_control,
    render_timeline_event,
    render_total_asset_hero,
)
from .formatters import compact_krw, format_number, full_krw, percentage, signed_krw, signed_percentage
from .stability import request_app_rerun
from .theme import DIMENSIONS, SEMANTIC_COLORS, deterministic_color


PROFIT_PERIODS = ["오늘", "총", "이번주", "이번달", "이번분기", "올해"]
JOURNAL_FILTERS = ["전체", "매수/매도", "입금/출금", "환전", "배당/이자", "메모"]


def _last_refresh_text(value: object | None) -> str:
    return str(value or "미조회")


def _status_text(model) -> str:
    return f"정상 {model.priced_count}/{model.holdings_count} · 실패 {model.failed_quote_count} · 미조회 {model.missing_quote_count}"


def _allocation_chart(view: AllocationViewModel) -> go.Figure | None:
    if not view.has_data:
        return None
    labels = [row.label for row in view.rows]
    values = [row.value_krw for row in view.rows]
    colors = [SEMANTIC_COLORS["cash"] if row.kind == "cash" else deterministic_color(row.key) for row in view.rows]
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.58,
            sort=False,
            marker=dict(colors=colors),
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>평가액 ₩%{value:,.0f}<br>비중 %{percent}<extra></extra>",
        )
    )
    fig.update_layout(
        annotations=[
            dict(
                text=f"{view.perspective}<br><b>{compact_krw(view.total_value_krw)}</b>",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
        ],
        margin=dict(l=8, r=8, t=8, b=8),
        showlegend=False,
    )
    return apply_chart_layout(fig, height=DIMENSIONS.compact_height, showlegend=False)


def _render_allocation_rows(view: AllocationViewModel) -> None:
    for row in view.rows:
        st.markdown(
            (
                "<div class='asset-row'>"
                f"<div class='asset-icon'>{row.label[:2]}</div>"
                "<div class='asset-main'>"
                f"<strong>{row.label}</strong>"
                f"<span>{row.detail}</span>"
                "</div>"
                "<div class='asset-values'>"
                f"<strong>{full_krw(row.value_krw)}</strong>"
                f"<span>{percentage(row.weight)}</span>"
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def _profit_summary_mapping(summary: ProfitSummaryView) -> dict[str, object]:
    return {
        "evaluation_profit_krw": summary.evaluation_profit_krw,
        "evaluation_profit_pct": summary.evaluation_profit_pct,
        "realized_profit_krw": summary.realized_profit_krw,
        "dividend_interest_krw": summary.dividend_interest_krw,
        "fees_taxes_krw": summary.fees_taxes_krw,
        "total_profit_krw": summary.total_profit_krw,
        "simple_return": summary.simple_return,
        "insufficient_reasons": summary.insufficient_reasons,
    }


def render_home_dashboard(
    *,
    metrics: PortfolioMetrics,
    transactions: list[dict[str, object]],
    cash_ledger: list[dict[str, object]],
    last_refresh_text: str,
    save_status_text: str,
    sample_mode: bool = False,
) -> str | None:
    model = build_dashboard_view_model(metrics, transactions=transactions, cash_ledger=cash_ledger, period="총")
    render_page_header("홈 대시보드", "총자산, 투자, 현금, 수익, 비중을 매일 보기 쉬운 형태로 정리했습니다.", status_text=_status_text(model), save_status_text=save_status_text)

    if model.is_empty:
        primary, secondary = render_empty_state(
            "아직 포트폴리오가 없습니다.",
            "먼저 입금 또는 거래를 입력하면 총자산 홈과 분석 화면이 채워집니다.",
            primary_label="입금 기록하기",
            primary_key="home_empty_go_cash",
            secondary_label="거래 입력하기",
            secondary_key="home_empty_go_trade",
        )
        if primary:
            return "cash"
        if secondary:
            return "trade"
        return None

    render_total_asset_hero(
        total_asset_krw=model.total_asset_krw,
        day_change_krw=model.day_change_krw,
        day_change_pct=model.day_change_pct,
        status_text=_status_text(model),
        last_refresh_text=last_refresh_text,
        sample_mode=sample_mode,
    )

    selected_nav = render_action_nav(
        [
            ("profit", "수익", "평가·실현·배당·비용 요약"),
            ("tax", "세금", "입력 세금과 수수료 합계"),
            ("dividend", "배당", "배당과 이자 내역"),
            ("trend", "추이", "저장된 총자산 흐름"),
            ("allocation", "비중", "종목·유형·통화 비중"),
            ("journal", "매매일지", "거래와 현금 흐름 타임라인"),
        ],
        active_key=None,
    )

    render_section_card("투자", help_text="평가액이 큰 종목부터 표시합니다. 상세 표는 아래에서 펼쳐 볼 수 있습니다.")
    if not model.asset_rows:
        render_empty_state("보유 종목이 없습니다.", "거래 입력 또는 현재 보유종목 빠른 입력으로 투자자산을 추가하세요.")
    else:
        show_all = st.toggle("전체 투자 종목 보기", value=False, key="home_show_all_assets") if len(model.asset_rows) > 5 else True
        for row in (model.asset_rows if show_all else model.asset_rows[:5]):
            render_asset_row(asdict(row))

    render_section_card("현금", help_text="현금은 총자산에 포함하지만 투자 종목과 분리해서 보여줍니다.", action_label=f"현금 비중 {percentage(model.cash_weight)}")
    if not model.cash_rows:
        render_empty_state("현금 기록이 없습니다.", "입금 또는 환전 기록을 추가하면 KRW/USD 현금이 별도로 표시됩니다.")
    else:
        for row in model.cash_rows:
            render_cash_row(asdict(row))
        st.caption(f"총현금 {full_krw(model.cash_value_krw)} · USD/KRW {format_number(model.usd_krw)}")

    render_section_card("수익 현황", help_text="투자 조언이 아니라 입력된 거래와 현금 원장 기반 집계입니다.")
    render_profit_summary_card(_profit_summary_mapping(model.profit_summary))
    if model.profit_summary.top_contributors or model.profit_summary.loss_contributors:
        cols = st.columns(2)
        with cols[0]:
            st.caption("상위 수익 기여")
            for item in model.profit_summary.top_contributors:
                st.write(f"{item.label}: {signed_krw(item.value_krw)}")
        with cols[1]:
            st.caption("하위 손실 기여")
            for item in model.profit_summary.loss_contributors:
                st.write(f"{item.label}: {signed_krw(item.value_krw)}")

    render_section_card("비중 미리보기", help_text="현금을 포함한 총자산 기준입니다.")
    allocation = build_allocation_view_model(metrics, perspective="종목별", max_rows=6)
    chart = _allocation_chart(allocation)
    if chart is None:
        render_empty_state("비중을 계산할 자산이 없습니다.", allocation.empty_message or "평가액이 생기면 비중이 표시됩니다.")
    else:
        left, right = st.columns([1, 1.2])
        with left:
            render_plotly_chart(chart, key="home_allocation_preview")
        with right:
            _render_allocation_rows(allocation)

    if model.alerts:
        render_section_card("확인 필요", help_text="데이터 상태가 계산 결과에 영향을 줄 수 있습니다.")
        for alert in model.alerts:
            st.warning(alert)
    return selected_nav


def render_profit_analysis_screen(
    *,
    metrics: PortfolioMetrics,
    transactions: list[dict[str, object]],
    cash_ledger: list[dict[str, object]],
) -> None:
    render_page_header("수익", "평가수익, 실현수익, 배당/이자, 수수료/세금을 분리해 확인합니다.")
    period = render_segmented_control("기간", PROFIT_PERIODS, key="profit_period", default="총")
    summary = build_profit_summary_view(metrics=metrics, transactions=transactions, cash_ledger=cash_ledger, period=period)
    render_profit_summary_card(_profit_summary_mapping(summary), detail=True)
    if not summary.has_data:
        render_empty_state("수익 데이터가 아직 충분하지 않습니다.", "거래, 현금 원장, 현재가가 쌓이면 수익 현황이 표시됩니다.")
    rows = []
    for item in list(summary.top_contributors) + list(summary.loss_contributors):
        rows.append({"종목": item.label, "손익": signed_krw(item.value_krw), "수익률": signed_percentage(item.pct)})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")


def _ledger_sums(cash_ledger: list[dict[str, object]], *, event_types: set[str]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in cash_ledger:
        if str(row.get("event_type")) in event_types:
            totals[str(row.get("currency") or "KRW")] += float(row.get("amount") or 0.0)
    return dict(totals)


def render_tax_summary_screen(*, transactions: list[dict[str, object]], cash_ledger: list[dict[str, object]]) -> None:
    render_page_header("세금·비용", "사용자가 입력한 세금과 수수료의 단순 집계입니다.")
    fee_total = sum(float(row.get("fee") or 0.0) for row in transactions)
    tax_total = sum(float(row.get("tax") or 0.0) for row in transactions)
    ledger_tax_fee = _ledger_sums(cash_ledger, event_types={"fee", "tax"})
    cols = st.columns(3)
    cols[0].metric("거래 수수료 입력합계", format_number(fee_total))
    cols[1].metric("거래 세금 입력합계", format_number(tax_total))
    cols[2].metric("원장 비용 항목", ", ".join(f"{currency} {format_number(abs(value))}" for currency, value in ledger_tax_fee.items()) or "없음")
    st.caption("세무 자문이나 신고용 계산이 아니라, 사용자가 입력한 값의 참고용 합계입니다.")
    if not transactions and not ledger_tax_fee:
        render_empty_state("세금·수수료 데이터가 없습니다.", "거래 입력이나 현금 원장에 수수료/세금을 입력하면 여기에 요약됩니다.")


def render_dividend_summary_screen(*, cash_ledger: list[dict[str, object]]) -> None:
    render_page_header("배당·이자", "현금 원장에 입력된 배당과 이자 수익을 통화별로 요약합니다.")
    totals = _ledger_sums(cash_ledger, event_types={"dividend", "interest"})
    if not totals:
        render_empty_state("배당/이자 기록이 없습니다.", "현금·입출금·환율 화면에서 배당 또는 이자를 입력하면 요약됩니다.")
        return
    cols = st.columns(max(1, len(totals)))
    for column, (currency, value) in zip(cols, totals.items()):
        column.metric(f"{currency} 배당·이자", format_number(value))


def render_allocation_analysis_screen(metrics: PortfolioMetrics) -> None:
    render_page_header("비중", "종목별, 유형별, 통화별, 계좌별 관점으로 총자산 구성을 확인합니다.")
    perspective = render_segmented_control("분석 관점", list(ALLOCATION_PERSPECTIVES), key="allocation_perspective", default="종목별")
    view = build_allocation_view_model(metrics, perspective=perspective)
    if not view.has_data:
        render_empty_state("비중을 계산할 자산이 없습니다.", view.empty_message or "입금 또는 거래를 먼저 입력하세요.")
        return
    chart = _allocation_chart(view)
    left, right = st.columns([1, 1.2])
    with left:
        if chart is not None:
            render_plotly_chart(chart, key=f"allocation_chart_{perspective}")
    with right:
        _render_allocation_rows(view)
    with st.expander("진단 보기", expanded=False):
        d = view.diagnostics
        cols = st.columns(4)
        cols[0].metric("HHI", format_number(d.hhi, digits=3, trim=True))
        cols[1].metric("상위 3개 비중", percentage(d.top3_weight))
        cols[2].metric("최대 단일 비중", percentage(d.max_single_weight))
        cols[3].metric("USD 노출도", percentage(d.usd_exposure_pct))


def _journal_summary(events) -> dict[str, object]:
    this_month = date.today().strftime("%Y-%m")
    by_type = Counter(event.event_type for event in events)
    month_events = [event for event in events if event.event_date.startswith(this_month)]
    return {
        "count": len(events),
        "month_buy": sum(float(event.amount or 0.0) for event in month_events if event.event_type == "buy"),
        "month_sell": sum(float(event.amount or 0.0) for event in month_events if event.event_type == "sell"),
        "month_cash": sum(float(event.cash_impact or 0.0) for event in month_events if event.event_type in {"deposit", "withdrawal"}),
        "month_income": sum(float(event.cash_impact or 0.0) for event in month_events if event.event_type in {"dividend", "interest"}),
        "last_date": events[0].event_date if events else None,
        "by_type": by_type,
    }


def render_journal_screen(
    *,
    transactions: list[dict[str, object]],
    cash_ledger: list[dict[str, object]],
    journal_notes: list[dict[str, object]],
    on_save_notes: Callable[[list[dict[str, object]]], None],
) -> None:
    render_page_header("매매일지", "매수/매도, 입출금, 환전, 배당, 메모를 날짜순으로 복기합니다.")
    events = build_journal_events(transactions=transactions, cash_ledger=cash_ledger, journal_notes=journal_notes)
    summary = _journal_summary(events)
    cols = st.columns(5)
    cols[0].metric("전체 이벤트", f"{summary['count']:,}건")
    cols[1].metric("이번달 매수", compact_krw(float(summary["month_buy"])))
    cols[2].metric("이번달 매도", compact_krw(float(summary["month_sell"])))
    cols[3].metric("이번달 입출금", signed_krw(float(summary["month_cash"])))
    cols[4].metric("마지막 기록", summary["last_date"] or "-")

    with st.expander("매매일지 작성하기", expanded=False):
        with st.form("journal_note_form", clear_on_submit=True):
            note_cols = st.columns([1, 1, 1])
            note_date = note_cols[0].date_input("날짜", value=date.today())
            symbol = note_cols[1].text_input("종목 연결", placeholder="선택 입력")
            tags = note_cols[2].multiselect("태그", ["전략", "복기", "실수", "뉴스", "기타"], default=["복기"])
            title = st.text_input("제목", placeholder="예: 매수 판단 기록")
            body = st.text_area("내용", placeholder="투자 판단, 복기, 뉴스 링크 등을 남깁니다.", height=100)
            submitted = st.form_submit_button("메모 저장", type="primary")
        if submitted:
            try:
                next_notes = normalize_journal_notes(
                    list(journal_notes)
                    + [{"note_date": note_date.isoformat(), "title": title, "body": body, "symbol": symbol, "tags": tags}]
                )
                on_save_notes(next_notes)
                request_app_rerun()
            except ValueError as exc:
                st.error(f"메모를 저장할 수 없습니다: {exc}")

    event_group = render_segmented_control("필터", JOURNAL_FILTERS, key="journal_filter", default="전체")
    symbol_filter = st.text_input("종목 필터", placeholder="예: 삼성전자, QURE", key="journal_symbol_filter")
    filtered = filter_journal_events(events, event_group=event_group, symbol=symbol_filter)
    if not filtered:
        render_empty_state("아직 매매일지가 없습니다.", "거래, 현금 원장 또는 수동 메모를 추가하면 타임라인이 표시됩니다.")
        return
    st.markdown("<div class='timeline'>", unsafe_allow_html=True)
    for event in filtered[:100]:
        render_timeline_event(asdict(event))
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("수동 메모 수정/삭제", expanded=False):
        if not journal_notes:
            st.caption("수정할 수동 메모가 없습니다.")
        else:
            edited = st.data_editor(journal_notes, num_rows="dynamic", width="stretch", key="journal_notes_editor")
            if st.button("수동 메모 수정 적용"):
                try:
                    on_save_notes(normalize_journal_notes(edited))
                    request_app_rerun()
                except ValueError as exc:
                    st.error(f"메모를 수정할 수 없습니다: {exc}")
