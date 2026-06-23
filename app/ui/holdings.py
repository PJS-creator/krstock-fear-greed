from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio.holdings import HOLDING_COLUMNS, PortfolioMetrics, merge_quick_rows_with_existing, normalize_holding_rows

from .formatters import format_kst, full_krw, percentage, signed_krw, signed_percentage
from .status import ISSUE_STATUSES, parse_bulk_input, prepare_quick_input_records, quote_status_label
from .theme import DIMENSIONS

QUICK_EDITOR_COLUMNS = ["ticker", "quantity"]
MARKET_LABELS = {"전체": None, "미국": "US", "국내": "KR"}
STATUS_FILTERS = {
    "전체": None,
    "문제만": "__issues__",
    "최신": "updated",
    "캐시": "cached",
    "이전 가격": "stale",
    "실패": "failed",
    "미조회": "missing",
    "수동": "manual",
}


def _quick_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=QUICK_EDITOR_COLUMNS)
    return pd.DataFrame(
        [{"ticker": row.get("ticker") or row.get("symbol"), "quantity": row.get("quantity")} for row in rows],
        columns=QUICK_EDITOR_COLUMNS,
    )


def _advanced_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=HOLDING_COLUMNS)


def _preview_frame(records: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["market", "ticker", "quantity"])


def _apply_quick_records(records: list[dict[str, object]], existing_rows: list[dict[str, object]]) -> None:
    st.session_state.holdings_rows = merge_quick_rows_with_existing(records, existing_rows)
    st.session_state.holdings_message = "입력값을 적용했습니다. 가격 새로고침 버튼을 눌러 최근 제공 가격을 갱신하세요."
    st.rerun()


def render_holdings_editor() -> None:
    st.subheader("빠른 입력")
    st.caption("ticker와 quantity만 입력해도 됩니다. 6자리 숫자는 국내 KR/KRW, 영문 ticker는 미국 US/USD로 추론합니다. 가격 조회는 자동 실행되지 않습니다.")
    rows = st.session_state.get("holdings_rows", [])
    quick_frame = st.data_editor(
        _quick_frame(rows),
        key="quick_holdings_editor",
        num_rows="dynamic",
        width="stretch",
        column_config={
            "ticker": st.column_config.TextColumn("ticker", required=True, help="예: 005930, MU, GOOG"),
            "quantity": st.column_config.NumberColumn("quantity", min_value=0.0, step=0.0001, required=True),
        },
    )
    prepared_records: list[dict[str, object]] = []
    try:
        prepared_records = prepare_quick_input_records(quick_frame.to_dict("records"))
    except ValueError as exc:
        st.warning(f"자동 추론을 확인하세요: {exc}")

    if prepared_records:
        st.caption("자동 추론 preview")
        preview_frame = st.data_editor(
            _preview_frame(prepared_records),
            key="quick_holdings_preview",
            num_rows="fixed",
            width="stretch",
            column_config={
                "market": st.column_config.SelectboxColumn("market", options=["US", "KR"], required=True),
                "ticker": st.column_config.TextColumn("ticker", required=True),
                "quantity": st.column_config.NumberColumn("quantity", min_value=0.0, step=0.0001, required=True),
            },
        )
    else:
        preview_frame = pd.DataFrame(columns=["market", "ticker", "quantity"])

    if st.button("입력 적용", type="primary"):
        try:
            _apply_quick_records(preview_frame.to_dict("records"), rows)
        except ValueError as exc:
            st.error(f"입력값을 적용할 수 없습니다: {exc}")

    with st.expander("다중 붙여넣기", expanded=False):
        bulk_text = st.text_area("한 줄에 ticker,quantity 형식으로 붙여넣기", placeholder="005930,10\nMU,20", height=110)
        result = parse_bulk_input(bulk_text) if bulk_text.strip() else None
        if result is not None:
            if result.errors:
                st.warning("\n".join(result.errors))
            if result.rows:
                st.caption("붙여넣기 preview")
                st.dataframe(_preview_frame(result.rows), hide_index=True, width="stretch")
            if st.button("붙여넣기 적용", disabled=not bool(result.rows)):
                try:
                    _apply_quick_records(result.rows, rows)
                except ValueError as exc:
                    st.error(f"붙여넣기 입력을 적용할 수 없습니다: {exc}")

    message = st.session_state.pop("holdings_message", None)
    if message:
        st.toast(message)

    with st.expander("고급 설정", expanded=False):
        advanced = st.data_editor(
            _advanced_frame(st.session_state.get("holdings_rows", [])),
            key="advanced_holdings_editor",
            num_rows="dynamic",
            width="stretch",
            column_config={
                "ticker": st.column_config.TextColumn("ticker", required=True),
                "quantity": st.column_config.NumberColumn("quantity", min_value=0.0, step=0.0001, required=True),
                "market": st.column_config.SelectboxColumn("market", options=["US", "KR"], required=True),
                "currency": st.column_config.SelectboxColumn("currency", options=["USD", "KRW"], required=True),
                "avg_price": st.column_config.NumberColumn("avg_price", min_value=0.0, step=0.01),
                "target_weight": st.column_config.NumberColumn("target_weight", min_value=0.0, max_value=1.0, step=0.01),
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
                "종목명": holding["display_name"],
                "시장": holding["market"],
                "수량": holding["quantity"],
                "통화": holding["currency"],
                "최근 제공 가격": holding.get("current_price"),
                "평가액": item.market_value_krw or 0.0,
                "평가액 표시": full_krw(item.market_value_krw),
                "오늘 변동액": signed_krw(item.day_change_krw),
                "오늘 변동률": signed_percentage(item.day_change_pct),
                "비중": item.weight * 100,
                "가격 상태": quote_status_label(holding.get("quote_status")),
                "raw_status": str(holding.get("quote_status") or ""),
                "조회 시각": format_kst(holding.get("fetched_at"), compact=True),
                "provider": holding.get("provider") or "-",
                "비중 표시": percentage(item.weight),
            }
        )
    return rows


def render_holdings_table(metrics: PortfolioMetrics) -> None:
    st.subheader("보유자산")
    rows = _holdings_table_rows(metrics)
    if not rows:
        st.info("보유자산을 입력하면 표가 표시됩니다.")
        return

    search = st.text_input("검색", placeholder="ticker 또는 종목명", key="holdings_search")
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
        st.info("필터 조건에 맞는 보유자산이 없습니다.")
        return

    base_columns = ["ticker", "종목명", "시장", "수량", "최근 제공 가격", "평가액 표시", "오늘 변동액", "오늘 변동률", "비중", "가격 상태", "조회 시각"]
    detail_columns = ["통화", "provider", "비중 표시"]
    visible_columns = base_columns + detail_columns if show_details else base_columns
    st.dataframe(
        frame[visible_columns],
        hide_index=True,
        width="stretch",
        height=min(DIMENSIONS.max_table_height, 100 + len(frame) * DIMENSIONS.row_height),
        column_config={
            "ticker": st.column_config.TextColumn("ticker"),
            "종목명": st.column_config.TextColumn("종목명"),
            "시장": st.column_config.TextColumn("시장"),
            "수량": st.column_config.NumberColumn("수량", format="%.4f"),
            "최근 제공 가격": st.column_config.NumberColumn("최근 제공 가격", format="%.2f"),
            "평가액 표시": st.column_config.TextColumn("평가액"),
            "오늘 변동액": st.column_config.TextColumn("오늘 변동액"),
            "오늘 변동률": st.column_config.TextColumn("오늘 변동률"),
            "비중": st.column_config.ProgressColumn("비중", min_value=0, max_value=100, format="%.1f%%"),
            "가격 상태": st.column_config.TextColumn("가격 상태"),
            "조회 시각": st.column_config.TextColumn("조회 시각"),
        },
    )
