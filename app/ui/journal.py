from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import date
from html import escape

import pandas as pd
import streamlit as st

from portfolio.journal import JournalEvent, build_journal_events, filter_journal_events, normalize_journal_notes

from .components import render_empty_state
from .formatters import format_number, format_price
from .stability import request_app_rerun

JOURNAL_FILTERS = ["전체", "매수/매도", "입금/출금", "환전", "배당/이자", "메모"]


def _event_label(event_type: str) -> str:
    return {
        "buy": "매수",
        "sell": "매도",
        "deposit": "입금",
        "withdrawal": "출금",
        "opening_balance": "시작 잔고",
        "manual_adjustment": "수동 조정",
        "fx_conversion": "환전",
        "fx_conversion_in": "환전 입금",
        "fx_conversion_out": "환전 출금",
        "dividend": "배당",
        "interest": "이자",
        "note": "메모",
        "fee": "수수료",
        "tax": "세금",
    }.get(event_type, event_type)


def _amount_text(amount: float | None, currency: str | None) -> str:
    if amount is None:
        return "-"
    if currency == "KRW":
        return compact_krw(amount)
    if currency == "USD":
        return f"${format_number(amount)}"
    return format_price(amount, currency)


def _month_summary(events: list[JournalEvent]) -> dict[str, object]:
    current_month = date.today().isoformat()[:7]
    month_events = [event for event in events if event.event_date.startswith(current_month)]
    last_date = events[0].event_date if events else None
    counts = Counter(event.event_type for event in events)
    month_counts = Counter(event.event_type for event in month_events)
    return {
        "count": len(events),
        "month_buy_count": month_counts.get("buy", 0),
        "month_sell_count": month_counts.get("sell", 0),
        "month_cash_count": sum(month_counts.get(event_type, 0) for event_type in ("deposit", "withdrawal", "opening_balance", "manual_adjustment")),
        "last_date": last_date,
        "note_count": counts.get("note", 0),
    }


def _render_event(event: JournalEvent) -> None:
    label = _event_label(event.event_type)
    amount = _amount_text(event.amount, event.currency)
    cash_impact = _amount_text(event.cash_impact, event.currency) if event.cash_impact is not None else "-"
    tags = " ".join(f"`{tag}`" for tag in event.tags)
    st.markdown(
        (
            "<div class='journal-event'>"
            f"<div class='journal-event-head'><span>{escape(event.event_date)}</span><strong>{escape(label)}</strong></div>"
            f"<div class='journal-event-title'>{escape(event.title)}</div>"
            f"<div class='journal-event-subtitle'>{escape(event.subtitle or '')}</div>"
            "<div class='journal-event-meta'>"
            f"<span>금액 {escape(amount)}</span>"
            f"<span>현금 영향 {escape(cash_impact)}</span>"
            f"<span>{escape(event.symbol or event.market or '')}</span>"
            "</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if tags:
        st.caption(tags)
    with st.expander("원본 상세", expanded=False):
        st.json(asdict(event))


def render_journal_tab(
    *,
    transactions: list[Mapping[str, object]],
    cash_ledger: list[Mapping[str, object]],
    journal_notes: list[Mapping[str, object]],
    on_save_notes: Callable[[list[dict[str, object]]], None],
) -> None:
    st.subheader("매매일지")
    st.caption("거래 입력, 현금 원장, 환전, 배당/이자, 수동 메모를 날짜순으로 모아 봅니다. 자동 생성 이벤트는 원본 거래/현금 원장을 삭제하지 않습니다.")

    events = build_journal_events(transactions=transactions, cash_ledger=cash_ledger, journal_notes=journal_notes)
    summary = _month_summary(events)
    cols = st.columns(5)
    cols[0].metric("전체 기록", f"{summary['count']:,}건")
    cols[1].metric("이번달 매수", f"{summary['month_buy_count']:,}건")
    cols[2].metric("이번달 매도", f"{summary['month_sell_count']:,}건")
    cols[3].metric("이번달 입출금", f"{summary['month_cash_count']:,}건")
    cols[4].metric("마지막 기록", summary["last_date"] or "-")

    with st.expander("수동 메모 작성", expanded=False):
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

    filter_cols = st.columns([1.4, 1])
    event_group = filter_cols[0].radio("필터", JOURNAL_FILTERS, horizontal=True, key="journal_filter")
    symbol_filter = filter_cols[1].text_input("종목 필터", placeholder="예: 삼성전자, QURE", key="journal_symbol_filter")
    filtered = filter_journal_events(events, event_group=event_group, symbol=symbol_filter)

    if not filtered:
        render_empty_state("아직 매매일지가 없습니다.", "거래 입력, 현금 원장 또는 수동 메모를 추가하면 이곳에 날짜순으로 표시됩니다.")
        return

    for event in filtered[:100]:
        _render_event(event)

    with st.expander("수동 메모 수정/삭제", expanded=False):
        if not journal_notes:
            st.caption("수정할 수동 메모가 없습니다.")
        else:
            edited = st.data_editor(pd.DataFrame(journal_notes), num_rows="dynamic", width="stretch", key="journal_notes_editor")
            if st.button("수동 메모 수정 적용"):
                try:
                    on_save_notes(normalize_journal_notes(edited.to_dict("records")))
                    request_app_rerun()
                except ValueError as exc:
                    st.error(f"메모를 수정할 수 없습니다: {exc}")
