from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from portfolio.holdings import HOLDING_COLUMNS, PortfolioMetrics, merge_quick_rows_with_existing, normalize_holding_rows
from portfolio.symbols import (
    SIMPLE_PORTFOLIO_COLUMNS,
    build_input_preview,
    csv_to_rows,
    load_korea_listing_records,
    parse_symbol_quantity_lines,
    preview_rows_to_holdings,
    rows_to_csv,
)

from .formatters import format_kst, format_number, format_price, full_krw, instrument_label, percentage, signed_krw, signed_percentage
from .status import ISSUE_STATUSES, quote_status_label
from .theme import DIMENSIONS

QUICK_EDITOR_COLUMNS = ["ticker_or_name", "quantity", "avg_price"]
QUICK_PREVIEW_STATE_KEY = "quick_holdings_preview_rows"
MARKET_LABELS = {"전체": None, "미국": "US", "국내": "KR"}
STATUS_FILTERS = {
    "전체": None,
    "문제만": "__issues__",
    "최신": "updated",
    "캐시": "cached",
    "이전저장값": "stale",
    "실패": "failed",
    "미조회": "missing",
    "수동": "manual",
}
ADVANCED_TEXT_COLUMNS = [
    "ticker",
    "market",
    "currency",
    "display_name",
    "account_name",
    "strategy_tag",
    "note",
    "quote_status",
    "fetched_at",
    "provider",
    "price_date",
    "as_of_timestamp",
    "source",
    "error_message",
]


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def _cached_korea_listing_records() -> list[dict[str, str]]:
    try:
        import FinanceDataReader as fdr
    except ImportError:
        return []
    try:
        return load_korea_listing_records(fdr.StockListing)
    except Exception:
        return []


def _quick_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=QUICK_EDITOR_COLUMNS)
    return pd.DataFrame(
        [
            {
                "ticker_or_name": row.get("display_name") or row.get("ticker") or row.get("symbol"),
                "quantity": row.get("quantity"),
                "avg_price": row.get("avg_price"),
            }
            for row in rows
        ],
        columns=QUICK_EDITOR_COLUMNS,
    )


def _advanced_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=HOLDING_COLUMNS)
    for column in ADVANCED_TEXT_COLUMNS:
        if column in frame.columns:
            frame[column] = frame[column].fillna("").astype(str)
    return frame


def _preview_frame(records: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(records, columns=["row_number", "raw_input", "ticker", "display_name", "market", "currency", "quantity", "avg_price", "status", "message"])
    return frame.rename(
        columns={
            "row_number": "행",
            "raw_input": "입력값",
            "ticker": "티커",
            "display_name": "표시명",
            "market": "시장",
            "currency": "통화",
            "quantity": "수량",
            "avg_price": "평균단가",
            "status": "상태",
            "message": "메시지",
        }
    )


def _apply_quick_records(records: list[dict[str, object]], existing_rows: list[dict[str, object]], *, duplicate_policy: str) -> None:
    st.session_state.holdings_rows = merge_quick_rows_with_existing(records, existing_rows, duplicate_policy=duplicate_policy)
    st.session_state.pop(QUICK_PREVIEW_STATE_KEY, None)
    st.session_state.holdings_message = "입력값을 적용했습니다. 가격 새로고침 버튼을 눌러 최근 제공 가격을 갱신하세요."
    st.rerun()


def _build_preview(rows: list[dict[str, object]]) -> None:
    listing_records = _cached_korea_listing_records()
    preview = build_input_preview(rows, korea_listing_records=listing_records)
    st.session_state[QUICK_PREVIEW_STATE_KEY] = preview.rows
    if preview.errors:
        st.session_state.holdings_message = "\n".join(preview.errors)


def _candidate_resolved_rows(preview_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    for row in preview_rows:
        next_row = dict(row)
        candidates = list(next_row.get("candidates") or [])
        if next_row.get("status") == "candidate_required" and candidates:
            labels = [f"{candidate['ticker']} · {candidate['display_name']}" for candidate in candidates]
            selected_label = st.selectbox(f"{next_row.get('row_number')}행 후보 선택", labels, key=f"quick_candidate_{next_row.get('row_number')}")
            selected = candidates[labels.index(selected_label)]
            next_row.update(
                {
                    "ticker": selected["ticker"],
                    "display_name": selected["display_name"],
                    "market": selected["market"],
                    "currency": selected["currency"],
                    "status": "ok",
                    "message": "선택한 후보를 적용합니다.",
                }
            )
        resolved.append(next_row)
    return resolved


def _render_quality_summary(preview_rows: list[dict[str, object]]) -> None:
    total = len(preview_rows)
    ok = sum(1 for row in preview_rows if row.get("status") == "ok")
    candidate = sum(1 for row in preview_rows if row.get("status") == "candidate_required")
    error = sum(1 for row in preview_rows if row.get("status") == "error")
    duplicate = len(preview_rows) - len({(row.get("market"), row.get("ticker")) for row in preview_rows if row.get("status") == "ok"})
    st.caption(f"입력 {total}행 · 인식 성공 {ok} · 후보 선택 필요 {candidate} · 오류 {error} · 중복 {max(duplicate, 0)}")


def render_holdings_editor() -> None:
    st.subheader("빠른 입력")
    st.caption("종목명 또는 티커와 수량만 입력해도 됩니다. 평균단가는 선택 입력이며, 입력하면 평가이익과 수익률을 계산합니다.")
    rows = st.session_state.get("holdings_rows", [])
    quick_frame = st.data_editor(
        _quick_frame(rows),
        key="quick_holdings_editor",
        num_rows="dynamic",
        width="stretch",
        column_config={
            "ticker_or_name": st.column_config.TextColumn("종목명 또는 티커", required=True, help="예: 삼성전자, 005930, MU, QURE"),
            "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, required=True, format="%,.4f"),
            "avg_price": st.column_config.NumberColumn("평균 매입단가", min_value=0.0, step=0.01, format="%,.2f", help="국내 종목은 원화, 미국 종목은 달러 기준입니다."),
        },
    )
    duplicate_policy = st.radio("동일 종목 입력 처리", ["새 입력값으로 교체", "기존 수량에 합산"], horizontal=True, key="quick_duplicate_policy")
    if st.button("입력 미리보기", type="primary"):
        _build_preview(quick_frame.to_dict("records"))

    preview_rows = list(st.session_state.get(QUICK_PREVIEW_STATE_KEY, []))
    if preview_rows:
        st.caption("적용 전 미리보기")
        preview_rows = _candidate_resolved_rows(preview_rows)
        _render_quality_summary(preview_rows)
        st.dataframe(
            _preview_frame(preview_rows),
            hide_index=True,
            width="stretch",
            column_config={
                "수량": st.column_config.NumberColumn("수량", format="%,.4f"),
                "평균단가": st.column_config.NumberColumn("평균단가", format="%,.2f"),
            },
        )
        ok_rows = [row for row in preview_rows if row.get("status") == "ok"]
        if st.button("오류 없는 행 적용", disabled=not ok_rows):
            try:
                _apply_quick_records(
                    preview_rows_to_holdings(ok_rows),
                    rows,
                    duplicate_policy="add" if duplicate_policy == "기존 수량에 합산" else "replace",
                )
            except ValueError as exc:
                st.error(f"입력값을 적용할 수 없습니다: {exc}")

    with st.expander("다중 붙여넣기", expanded=False):
        bulk_text = st.text_area("한 줄에 종목명 또는 티커, 수량, 선택 평균단가 붙여넣기", placeholder="삼성전자 10 72300\n005930,10,72300\nMU 20 120.5\nQURE,500", height=110)
        if st.button("붙여넣기 미리보기", disabled=not bulk_text.strip()):
            _build_preview(parse_symbol_quantity_lines(bulk_text))

    with st.expander("CSV 업로드", expanded=False):
        st.download_button(
            "간편 CSV 템플릿",
            data=rows_to_csv(
                [{"ticker_or_name": "삼성전자", "quantity": "10", "avg_price": "72300"}, {"ticker_or_name": "MU", "quantity": "20", "avg_price": "120.5"}],
                SIMPLE_PORTFOLIO_COLUMNS,
            ).encode("utf-8-sig"),
            file_name="portfolio_simple_template.csv",
            mime="text/csv",
        )
        uploaded = st.file_uploader("간편 CSV 업로드", type=["csv"], key="quick_simple_csv_upload")
        if uploaded is not None and st.button("CSV 미리보기"):
            _build_preview(csv_to_rows(uploaded.getvalue()))

    message = st.session_state.pop("holdings_message", None)
    if message:
        if "\n" in message:
            st.warning(message)
        else:
            st.toast(message)

    with st.expander("고급 설정", expanded=False):
        advanced = st.data_editor(
            _advanced_frame(st.session_state.get("holdings_rows", [])),
            key="advanced_holdings_editor",
            num_rows="dynamic",
            width="stretch",
            column_config={
                "ticker": st.column_config.TextColumn("티커", required=True),
                "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, required=True, format="%,.4f"),
                "market": st.column_config.SelectboxColumn("시장", options=["US", "KR"], required=True),
                "currency": st.column_config.SelectboxColumn("통화", options=["USD", "KRW"], required=True),
                "display_name": st.column_config.TextColumn("표시명"),
                "account_name": st.column_config.TextColumn("계좌"),
                "strategy_tag": st.column_config.TextColumn("전략 태그"),
                "avg_price": st.column_config.NumberColumn("평균 매수가", min_value=0.0, step=0.01, format="%,.2f"),
                "target_weight": st.column_config.NumberColumn("목표 비중", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
                "current_price": st.column_config.NumberColumn("현재가", min_value=0.0, step=0.01, format="%,.2f"),
                "previous_close": st.column_config.NumberColumn("전일 종가", min_value=0.0, step=0.01, format="%,.2f"),
                "note": st.column_config.TextColumn("메모"),
            },
        )
        if st.button("고급 설정 적용"):
            try:
                st.session_state.holdings_rows = normalize_holding_rows(advanced.to_dict("records"))
                st.rerun()
            except ValueError as exc:
                st.error(f"고급 설정을 적용할 수 없습니다: {exc}")


def _holdings_table_rows(metrics: PortfolioMetrics) -> list[dict[str, object]]:
    rows = []
    for item in metrics.rows:
        holding = item.holding
        rows.append(
            {
                "ticker": str(holding["ticker"]),
                "종목": instrument_label(holding),
                "종목명": holding["display_name"],
                "시장": holding["market"],
                "수량": holding["quantity"],
                "수량 표시": format_number(float(holding["quantity"]), digits=4, trim=True),
                "통화": holding["currency"],
                "평균단가 표시": format_price(holding.get("avg_price"), holding.get("currency")),
                "최근 제공 가격": holding.get("current_price"),
                "최근 제공 가격 표시": format_price(holding.get("current_price"), holding.get("currency")),
                "평가액": item.market_value_krw or 0.0,
                "평가액 표시": full_krw(item.market_value_krw),
                "오늘 변동액": signed_krw(item.day_change_krw),
                "오늘 변동률": signed_percentage(item.day_change_pct),
                "비중": item.weight * 100,
                "가격 상태": quote_status_label(holding.get("quote_status")),
                "raw_status": str(holding.get("quote_status") or ""),
                "조회 시각": format_kst(holding.get("fetched_at"), compact=True),
                "가격 기준일": holding.get("price_date") or "-",
                "기준시각": format_kst(holding.get("as_of_timestamp"), compact=True),
                "출처": holding.get("source") or holding.get("provider") or "-",
                "오류": holding.get("error_message") or "",
                "provider": holding.get("provider") or "-",
                "비중 표시": percentage(item.weight),
            }
        )
    return rows


def _mobile_text(value: object) -> str:
    try:
        if pd.isna(value):
            return "-"
    except (TypeError, ValueError):
        pass
    text = str(value or "").strip()
    return text or "-"


def _mobile_change_text(amount: object, pct_value: object) -> str:
    amount_text = _mobile_text(amount)
    pct_text = _mobile_text(pct_value)
    if amount_text == "-" and pct_text == "-":
        return "-"
    if pct_text == "-":
        return amount_text
    return f"{amount_text} ({pct_text})"


def _mobile_change_class(value: object) -> str:
    text = _mobile_text(value)
    if text.startswith("+"):
        return "mobile-holding-up"
    if text.startswith("-"):
        return "mobile-holding-down"
    return "mobile-holding-neutral"


def _mobile_holdings_cards_html(frame: pd.DataFrame) -> str:
    cards = []
    for _, row in frame.iterrows():
        weight = percentage(float(row.get("비중") or 0.0) / 100.0, digits=2)
        today_change = _mobile_change_text(row.get("오늘 변동액"), row.get("오늘 변동률"))
        today_class = _mobile_change_class(row.get("오늘 변동액"))
        cards.append(
            "<article class='mobile-holding-card'>"
            "<div class='mobile-holding-head'>"
            f"<div class='mobile-holding-name'>{escape(_mobile_text(row.get('종목')))}</div>"
            f"<div class='mobile-holding-weight'>{escape(weight)}</div>"
            "</div>"
            f"<div class='mobile-holding-value'>{escape(_mobile_text(row.get('평가액 표시')))}</div>"
            "<div class='mobile-holding-grid'>"
            f"<div class='mobile-holding-cell'><span>수량</span><strong>{escape(_mobile_text(row.get('수량 표시')))}</strong></div>"
            f"<div class='mobile-holding-cell'><span>현재가</span><strong>{escape(_mobile_text(row.get('최근 제공 가격 표시')))}</strong></div>"
            f"<div class='mobile-holding-cell'><span>시장</span><strong>{escape(_mobile_text(row.get('시장')))}</strong></div>"
            f"<div class='mobile-holding-cell'><span>가격 상태</span><strong>{escape(_mobile_text(row.get('가격 상태')))}</strong></div>"
            "</div>"
            "<div class='mobile-holding-line'>"
            "<span>오늘 변동</span>"
            f"<strong class='{today_class}'>{escape(today_change)}</strong>"
            "</div>"
            "</article>"
        )
    return "<div class='mobile-holdings-cards'>" + "".join(cards) + "</div>"


def _render_mobile_holdings_cards(frame: pd.DataFrame) -> None:
    st.markdown(_mobile_holdings_cards_html(frame), unsafe_allow_html=True)


def render_holdings_table(metrics: PortfolioMetrics) -> None:
    st.subheader("보유 현황")
    rows = _holdings_table_rows(metrics)
    if not rows:
        st.info("보유 종목을 입력하면 표가 표시됩니다.")
        return

    search = st.text_input("검색", placeholder="종목명 또는 ticker", key="holdings_search")
    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
    market_label = filter_col1.selectbox("시장", list(MARKET_LABELS.keys()), key="holdings_market_filter")
    status_label = filter_col2.selectbox("가격 상태", list(STATUS_FILTERS.keys()), key="holdings_status_filter")
    show_details = filter_col3.checkbox("상세 열 보기", value=False, key="holdings_show_details")

    frame = pd.DataFrame(rows)
    if search:
        lowered = search.strip().lower()
        frame = frame[
            frame["ticker"].str.lower().str.contains(lowered, na=False)
            | frame["종목명"].astype(str).str.lower().str.contains(lowered, na=False)
        ]
    market_value = MARKET_LABELS[market_label]
    if market_value:
        frame = frame[frame["시장"] == market_value]
    raw_status = STATUS_FILTERS[status_label]
    if raw_status == "__issues__":
        frame = frame[frame["raw_status"].isin(ISSUE_STATUSES)]
    elif raw_status:
        frame = frame[frame["raw_status"] == raw_status]

    frame = frame.sort_values("평가액", ascending=False)
    if frame.empty:
        st.info("필터 조건에 맞는 보유 종목이 없습니다.")
        return

    base_columns = ["종목", "시장", "수량 표시", "최근 제공 가격 표시", "평가액 표시", "오늘 변동액", "오늘 변동률", "비중", "가격 상태", "조회 시각"]
    detail_columns = ["ticker", "종목명", "통화", "평균단가 표시", "가격 기준일", "기준시각", "출처", "오류", "provider", "비중 표시"]
    visible_columns = base_columns + detail_columns if show_details else base_columns
    _render_mobile_holdings_cards(frame)
    st.dataframe(
        frame[visible_columns],
        hide_index=True,
        width="stretch",
        height=min(DIMENSIONS.max_table_height, 100 + len(frame) * DIMENSIONS.row_height),
        column_config={
            "종목": st.column_config.TextColumn("종목"),
            "ticker": st.column_config.TextColumn("ticker"),
            "종목명": st.column_config.TextColumn("종목명"),
            "시장": st.column_config.TextColumn("시장"),
            "수량 표시": st.column_config.TextColumn("수량"),
            "평균단가 표시": st.column_config.TextColumn("평균단가"),
            "최근 제공 가격 표시": st.column_config.TextColumn("최근 제공 가격"),
            "평가액 표시": st.column_config.TextColumn("평가액"),
            "오늘 변동액": st.column_config.TextColumn("오늘 변동액"),
            "오늘 변동률": st.column_config.TextColumn("오늘 변동률"),
            "비중": st.column_config.ProgressColumn("비중", min_value=0, max_value=100, format="%.1f%%"),
            "가격 상태": st.column_config.TextColumn("가격 상태"),
            "조회 시각": st.column_config.TextColumn("조회 시각"),
            "가격 기준일": st.column_config.TextColumn("가격 기준일"),
            "기준시각": st.column_config.TextColumn("기준시각"),
            "출처": st.column_config.TextColumn("출처"),
            "오류": st.column_config.TextColumn("오류"),
        },
    )
