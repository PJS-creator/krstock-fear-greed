from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from portfolio.symbols import load_korea_listing_records
from portfolio.holdings import normalize_holding_rows
from portfolio.transactions import (
    TRANSACTION_COLUMNS,
    TRANSACTION_CSV_COLUMNS,
    TRANSACTION_TYPE_LABELS,
    build_transaction_preview,
    csv_to_rows,
    normalize_transaction_rows,
    parse_transaction_lines,
    preview_rows_to_transactions,
    rows_to_csv,
    transactions_to_holdings,
)

from .charts import plot_transaction_cashflow
from .components import render_plotly_chart
from .formatters import format_number, format_price, full_krw
from .theme import DIMENSIONS

TRANSACTION_PREVIEW_STATE_KEY = "transaction_preview_rows"
TRANSACTION_MESSAGE_KEY = "transaction_message"
QUICK_TRANSACTION_COLUMNS = ["transaction_type", "ticker_or_name", "unit_price", "quantity", "occurred_at"]


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


def _empty_quick_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=QUICK_TRANSACTION_COLUMNS)


def _preview_frame(records: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(
        records,
        columns=[
            "row_number",
            "transaction_label",
            "raw_input",
            "ticker",
            "display_name",
            "market",
            "currency",
            "unit_price",
            "quantity",
            "occurred_at",
            "status",
            "message",
        ],
    )
    return frame.rename(
        columns={
            "row_number": "행",
            "transaction_label": "구분",
            "raw_input": "입력값",
            "ticker": "티커",
            "display_name": "종목명",
            "market": "시장",
            "currency": "통화",
            "unit_price": "평단가",
            "quantity": "수량",
            "occurred_at": "시점",
            "status": "상태",
            "message": "메시지",
        }
    )


def _ledger_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    normalized = normalize_transaction_rows(rows)
    return pd.DataFrame(normalized, columns=TRANSACTION_COLUMNS)


def _display_ledger_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["구분", "종목", "티커", "시장", "평단가", "수량", "시점", "거래금액", "메모"])
    normalized = normalize_transaction_rows(rows)
    display_rows = []
    for row in normalized:
        amount = float(row["unit_price"]) * float(row["quantity"])
        display_rows.append(
            {
                "구분": TRANSACTION_TYPE_LABELS[str(row["transaction_type"])],
                "종목": row["display_name"],
                "티커": row["ticker"],
                "시장": row["market"],
                "평단가": format_price(float(row["unit_price"]), row["currency"]),
                "수량": format_number(float(row["quantity"]), digits=4, trim=True),
                "시점": row["occurred_at"],
                "거래금액": format_price(amount, row["currency"]),
                "메모": row.get("note") or "",
            }
        )
    return pd.DataFrame(display_rows)


def _set_message(message: str) -> None:
    st.session_state[TRANSACTION_MESSAGE_KEY] = message


def _opening_transactions_from_holdings(rows: list[dict[str, object]], occurred_at: str) -> list[dict[str, object]]:
    transactions: list[dict[str, object]] = []
    missing_price_labels: list[str] = []
    for holding in normalize_holding_rows(rows):
        unit_price = holding.get("avg_price") if holding.get("avg_price") is not None else holding.get("current_price")
        if unit_price is None:
            missing_price_labels.append(str(holding.get("display_name") or holding.get("ticker")))
            continue
        transactions.append(
            {
                "transaction_type": "buy",
                "ticker": holding["ticker"],
                "market": holding["market"],
                "currency": holding["currency"],
                "display_name": holding["display_name"],
                "unit_price": unit_price,
                "quantity": holding["quantity"],
                "occurred_at": occurred_at,
                "note": "기존 보유현황 시작 잔고",
            }
        )
    if missing_price_labels:
        raise ValueError(f"평단가 또는 현재가가 없어 시작 거래로 전환할 수 없습니다: {', '.join(missing_price_labels)}")
    return transactions


def _rebuild_holdings_from_transactions(transactions: list[dict[str, object]]) -> None:
    st.session_state.portfolio_transactions = normalize_transaction_rows(transactions)
    st.session_state.holdings_rows = transactions_to_holdings(
        st.session_state.portfolio_transactions,
        previous_holdings=st.session_state.get("holdings_rows", []),
    )


def _append_transactions(new_transactions: list[dict[str, object]]) -> None:
    existing = normalize_transaction_rows(st.session_state.get("portfolio_transactions", []))
    combined = existing + new_transactions
    _rebuild_holdings_from_transactions(combined)
    st.session_state.pop(TRANSACTION_PREVIEW_STATE_KEY, None)
    _set_message("거래내역을 반영했습니다. 전체 보유현황이 거래 기준으로 다시 계산되었습니다.")
    st.rerun()


def _build_preview(rows: list[dict[str, object]]) -> None:
    preview = build_transaction_preview(rows, korea_listing_records=_cached_korea_listing_records())
    st.session_state[TRANSACTION_PREVIEW_STATE_KEY] = preview.rows
    if preview.errors:
        _set_message("\n".join(preview.errors))


def _candidate_resolved_rows(preview_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    for row in preview_rows:
        next_row = dict(row)
        candidates = list(next_row.get("candidates") or [])
        if next_row.get("status") == "candidate_required" and candidates:
            labels = [f"{candidate['ticker']} · {candidate['display_name']}" for candidate in candidates]
            selected_label = st.selectbox(f"{next_row.get('row_number')}행 후보 선택", labels, key=f"transaction_candidate_{next_row.get('row_number')}")
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
    st.caption(f"입력 {total}행 · 인식 성공 {ok} · 후보 선택 필요 {candidate} · 오류 {error}")


def _render_preview() -> None:
    preview_rows = list(st.session_state.get(TRANSACTION_PREVIEW_STATE_KEY, []))
    if not preview_rows:
        return
    st.caption("적용 전 미리보기")
    preview_rows = _candidate_resolved_rows(preview_rows)
    _render_quality_summary(preview_rows)
    st.dataframe(
        _preview_frame(preview_rows),
        hide_index=True,
        width="stretch",
        column_config={
            "평단가": st.column_config.NumberColumn("평단가", format="%,.2f"),
            "수량": st.column_config.NumberColumn("수량", format="%,.4f"),
        },
    )
    ok_rows = [row for row in preview_rows if row.get("status") == "ok"]
    if st.button("오류 없는 거래 반영", disabled=not ok_rows, type="primary"):
        try:
            _append_transactions(preview_rows_to_transactions(ok_rows))
        except ValueError as exc:
            st.error(f"거래를 반영할 수 없습니다: {exc}")


def _render_single_transaction_form() -> None:
    st.subheader("거래 1건 입력")
    with st.form("single_transaction_form", clear_on_submit=False):
        col1, col2, col3, col4, col5 = st.columns([0.9, 1.6, 1, 1, 1.1])
        transaction_type = col1.selectbox("구분", ["매입", "매도"], key="single_transaction_type")
        ticker_or_name = col2.text_input("주식명", placeholder="예: 삼성전자, 005930, MU")
        unit_price = col3.number_input("평단가", min_value=0.0, step=0.01, format="%.2f")
        quantity = col4.number_input("수량", min_value=0.0, step=0.0001, format="%.4f")
        occurred_at = col5.date_input("시점", value=date.today())
        submitted = st.form_submit_button("거래 미리보기", type="primary")
    if submitted:
        _build_preview(
            [
                {
                    "transaction_type": transaction_type,
                    "ticker_or_name": ticker_or_name,
                    "unit_price": unit_price,
                    "quantity": quantity,
                    "occurred_at": occurred_at.isoformat(),
                }
            ]
        )


def _render_legacy_holdings_migration() -> None:
    if st.session_state.get("portfolio_transactions") or not st.session_state.get("holdings_rows"):
        return
    st.warning("현재 보유현황은 거래내역 없이 저장된 기존 데이터입니다. 앞으로 매입/매도 기준으로 관리하려면 시작 거래로 한 번 전환하세요.")
    col1, col2 = st.columns([1, 2], vertical_alignment="bottom")
    opening_date = col1.date_input("시작 거래 시점", value=date.today(), key="opening_transaction_date")
    if col2.button("현재 보유현황을 시작 매입 거래로 전환"):
        try:
            opening_transactions = _opening_transactions_from_holdings(
                list(st.session_state.get("holdings_rows", [])),
                opening_date.isoformat(),
            )
            _rebuild_holdings_from_transactions(opening_transactions)
            _set_message("기존 보유현황을 시작 매입 거래로 전환했습니다.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _render_quick_transaction_input() -> None:
    with st.expander("여러 개 빠른 입력", expanded=True):
        st.caption("행을 추가해 여러 거래를 한 번에 입력합니다. 구분은 매입 또는 매도, 평단가는 국내 종목은 원화·미국 종목은 달러 기준입니다.")
        quick_frame = st.data_editor(
            _empty_quick_frame(),
            key="quick_transactions_editor",
            num_rows="dynamic",
            width="stretch",
            column_config={
                "transaction_type": st.column_config.SelectboxColumn("구분", options=["매입", "매도"], required=True),
                "ticker_or_name": st.column_config.TextColumn("주식명", required=True, help="예: 삼성전자, 005930, MU, QURE"),
                "unit_price": st.column_config.NumberColumn("평단가", min_value=0.0, step=0.01, required=True, format="%,.2f"),
                "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, required=True, format="%,.4f"),
                "occurred_at": st.column_config.TextColumn("시점", required=True, help="YYYY-MM-DD 또는 ISO datetime"),
            },
        )
        if st.button("빠른 입력 미리보기"):
            _build_preview(quick_frame.to_dict("records"))

        bulk_text = st.text_area(
            "붙여넣기 입력",
            placeholder="매입 삼성전자 72300 200 2026-04-13\n매도 MU 120.5 10 2026-06-01",
            height=96,
        )
        if st.button("붙여넣기 미리보기", disabled=not bulk_text.strip()):
            _build_preview(parse_transaction_lines(bulk_text))


def _render_transaction_csv_tools() -> None:
    with st.expander("CSV로 한번에 입력", expanded=False):
        st.download_button(
            "거래 CSV 템플릿",
            data=rows_to_csv(
                [
                    {
                        "transaction_type": "매입",
                        "ticker_or_name": "삼성전자",
                        "unit_price": "72300",
                        "quantity": "200",
                        "occurred_at": "2026-04-13",
                    },
                    {
                        "transaction_type": "매도",
                        "ticker_or_name": "MU",
                        "unit_price": "120.5",
                        "quantity": "10",
                        "occurred_at": "2026-06-01",
                    },
                ],
                TRANSACTION_CSV_COLUMNS,
            ).encode("utf-8-sig"),
            file_name="portfolio_transactions_template.csv",
            mime="text/csv",
        )
        uploaded = st.file_uploader("거래 CSV 업로드", type=["csv"], key="transaction_csv_upload")
        if uploaded is not None and st.button("CSV 미리보기"):
            _build_preview(csv_to_rows(uploaded.getvalue()))


def _render_transaction_ledger() -> None:
    transactions = normalize_transaction_rows(st.session_state.get("portfolio_transactions", []))
    st.subheader("거래내역")
    if not transactions:
        st.info("매입/매도 거래를 입력하면 거래내역과 전체 보유현황이 표시됩니다.")
        return
    st.dataframe(
        _display_ledger_frame(transactions),
        hide_index=True,
        width="stretch",
        height=min(DIMENSIONS.max_table_height, 100 + len(transactions) * DIMENSIONS.row_height),
    )
    with st.expander("거래내역 직접 수정", expanded=False):
        st.caption("잘못 입력한 거래를 고칠 때만 사용합니다. 수정 후 적용하면 전체 보유현황이 다시 계산됩니다.")
        edited = st.data_editor(
            _ledger_frame(transactions),
            key="transaction_ledger_editor",
            num_rows="dynamic",
            width="stretch",
            column_config={
                "transaction_type": st.column_config.SelectboxColumn("구분", options=["buy", "sell"], required=True, help="buy=매입, sell=매도"),
                "ticker": st.column_config.TextColumn("티커", required=True),
                "market": st.column_config.SelectboxColumn("시장", options=["KR", "US"], required=True),
                "currency": st.column_config.SelectboxColumn("통화", options=["KRW", "USD"], required=True),
                "display_name": st.column_config.TextColumn("종목명"),
                "unit_price": st.column_config.NumberColumn("평단가", min_value=0.0, step=0.01, required=True, format="%,.2f"),
                "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, required=True, format="%,.4f"),
                "occurred_at": st.column_config.TextColumn("시점", required=True),
                "note": st.column_config.TextColumn("메모"),
            },
        )
        if st.button("거래내역 수정 적용"):
            try:
                _rebuild_holdings_from_transactions(edited.to_dict("records"))
                _set_message("수정한 거래내역을 반영했습니다.")
                st.rerun()
            except ValueError as exc:
                st.error(f"거래내역을 적용할 수 없습니다: {exc}")


def render_transaction_editor() -> None:
    st.subheader("자산 입력")
    st.caption("자산 입력은 매입/매도 거래로만 관리합니다. 거래를 입력하면 전체 보유현황과 평단가가 자동으로 다시 계산됩니다.")
    _render_legacy_holdings_migration()
    _render_single_transaction_form()
    _render_quick_transaction_input()
    _render_transaction_csv_tools()
    _render_preview()
    message = st.session_state.pop(TRANSACTION_MESSAGE_KEY, None)
    if message:
        if "\n" in message:
            st.warning(message)
        else:
            st.toast(message)
    _render_transaction_ledger()


def render_transaction_cashflow(transactions: list[dict[str, object]], *, usd_krw: float) -> None:
    st.subheader("매입/매도 기준 자산 증감")
    if not transactions:
        st.info("거래내역을 입력하면 매입·매도에 따른 일별 순매입과 누적 순매입 그래프가 표시됩니다.")
        return
    try:
        fig = plot_transaction_cashflow(transactions, usd_krw=usd_krw)
    except ValueError as exc:
        st.error(f"거래 그래프를 계산할 수 없습니다: {exc}")
        return
    if fig is None:
        st.info("표시할 거래 그래프 데이터가 없습니다.")
        return
    render_plotly_chart(fig, key="transaction_cashflow_chart")
    rows = []
    for row in transactions:
        fx_rate = 1.0 if row.get("currency") == "KRW" else usd_krw
        amount_krw = float(row["unit_price"]) * float(row["quantity"]) * fx_rate
        rows.append(amount_krw if row["transaction_type"] == "buy" else -amount_krw)
    st.caption(f"누적 순매입 {full_krw(sum(rows))} · 매입은 양수, 매도는 음수로 계산합니다.")
