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
    normalize_trade_input,
    normalize_transaction_rows,
    parse_transaction_lines,
    preview_rows_to_transactions,
    rows_to_csv,
    transactions_to_holdings,
    validate_trade_input,
)

from .charts import plot_transaction_cashflow
from .components import render_plotly_chart
from .formatters import format_number, format_price, full_krw
from .theme import DIMENSIONS

TRANSACTION_PREVIEW_STATE_KEY = "transaction_preview_rows"
TRANSACTION_MESSAGE_KEY = "transaction_message"
QUICK_TRANSACTION_COLUMNS = ["transaction_type", "ticker_or_name", "unit_price", "quantity", "occurred_at"]
DIRECT_HOLDING_OPTION = "직접 입력"
AUTO_CURRENCY_OPTION = "시장 기준 자동"


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
            "fee",
            "tax",
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
            "unit_price": "체결단가",
            "quantity": "수량",
            "fee": "수수료",
            "tax": "세금",
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
        return pd.DataFrame(columns=["구분", "종목", "티커", "시장", "체결단가", "수량", "수수료", "세금", "시점", "거래금액", "메모"])
    normalized = normalize_transaction_rows(rows)
    display_rows = []
    for row in normalized:
        amount = float(row["unit_price"]) * float(row["quantity"])
        fee = float(row.get("fee") or 0.0)
        tax = float(row.get("tax") or 0.0)
        display_rows.append(
            {
                "구분": TRANSACTION_TYPE_LABELS[str(row["transaction_type"])],
                "종목": row["display_name"],
                "티커": row["ticker"],
                "시장": row["market"],
                "체결단가": format_price(float(row["unit_price"]), row["currency"]),
                "수량": format_number(float(row["quantity"]), digits=4, trim=True),
                "수수료": format_price(fee, row["currency"]) if fee else "-",
                "세금": format_price(tax, row["currency"]) if tax else "-",
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
        raise ValueError(f"평균단가 또는 현재가가 없어 시작 거래로 전환할 수 없습니다: {', '.join(missing_price_labels)}")
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


def _build_preview(rows: list[dict[str, object]], *, auto_market_hint: bool = False) -> None:
    preview = build_transaction_preview(rows, korea_listing_records=_cached_korea_listing_records())
    st.session_state[TRANSACTION_PREVIEW_STATE_KEY] = preview.rows
    if preview.errors:
        messages = list(preview.errors)
        if auto_market_hint:
            messages.insert(0, "시장 자동감지가 실패하면 시장을 KR 또는 US로 직접 선택하세요.")
        _set_message("\n".join(messages))


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
                    "currency": next_row.get("currency") or selected["currency"],
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
            "체결단가": st.column_config.NumberColumn("체결단가", format="%,.2f"),
            "수량": st.column_config.NumberColumn("수량", format="%,.4f"),
            "수수료": st.column_config.NumberColumn("수수료", format="%,.2f"),
            "세금": st.column_config.NumberColumn("세금", format="%,.2f"),
        },
    )
    ok_rows = [row for row in preview_rows if row.get("status") == "ok"]
    if st.button("오류 없는 거래 반영", disabled=not ok_rows, type="primary"):
        try:
            _append_transactions(preview_rows_to_transactions(ok_rows))
        except ValueError as exc:
            st.error(_format_transaction_error(exc))


def _holding_options(rows: list[dict[str, object]]) -> tuple[list[str], dict[str, dict[str, object]]]:
    options = [DIRECT_HOLDING_OPTION]
    by_label: dict[str, dict[str, object]] = {}
    for holding in normalize_holding_rows(rows):
        quantity = format_number(float(holding["quantity"]), digits=4, trim=True)
        label = f"{holding['market']} · {holding['display_name']} · {holding['ticker']} · {quantity}주"
        options.append(label)
        by_label[label] = holding
    return options, by_label


def _default_currency_option(market: str, selected_holding: dict[str, object] | None) -> str:
    if selected_holding is not None:
        return str(selected_holding.get("currency") or AUTO_CURRENCY_OPTION)
    if market == "KR":
        return "KRW"
    if market == "US":
        return "USD"
    return AUTO_CURRENCY_OPTION


def _format_transaction_error(exc: Exception) -> str:
    message = str(exc)
    if "sell quantity exceeds current holdings" in message:
        return "현재 보유 수량을 초과해 매도할 수 없습니다. 수량을 확인하세요."
    return f"거래를 반영할 수 없습니다: {message}"


def _render_standard_transaction_form() -> None:
    st.subheader("표준 거래 입력")
    st.caption("PC에서는 핵심 거래 정보를 한 줄로 입력하고, 수수료·세금·메모는 상세 옵션에서 입력합니다.")
    holding_options, holdings_by_label = _holding_options(list(st.session_state.get("holdings_rows", [])))

    default_market = "자동감지"
    market_options = ["자동감지", "KR", "US"]
    currency_options = [AUTO_CURRENCY_OPTION, "KRW", "USD"]
    default_currency = _default_currency_option(default_market, None)

    with st.form("standard_transaction_form", clear_on_submit=False):
        core_cols = st.columns([0.85, 0.85, 2.1, 1.05, 1.0, 1.1, 1.05], gap="small", vertical_alignment="bottom")
        transaction_type = core_cols[0].selectbox("구분", ["매입", "매도"], help="매입은 보유 수량을 늘리고, 매도는 보유 수량을 줄입니다.")
        market = core_cols[1].selectbox("시장", market_options, index=market_options.index(default_market), help="자동감지가 실패하면 KR 또는 US를 직접 선택하세요.")
        ticker_or_name = core_cols[2].text_input(
            "종목",
            placeholder="삼성전자, 005930, GOOGL",
            help="국내 종목은 종목명 또는 6자리 코드, 미국 종목은 ticker를 입력하세요.",
        )
        unit_price = core_cols[3].number_input("체결단가", min_value=0.0, step=0.01, format="%.2f", help="실제 체결된 1주당 가격입니다.")
        quantity = core_cols[4].number_input("수량", min_value=0.0, step=0.0001, format="%.4f", help="매입 또는 매도한 주식 수량입니다.")
        occurred_at = core_cols[5].date_input("거래일", value=date.today(), help="문자열 대신 달력에서 선택합니다.")
        submitted = core_cols[6].form_submit_button("미리보기", type="primary", use_container_width=True)

        with st.expander("상세 옵션", expanded=False):
            detail_cols = st.columns([1.6, 1.0, 1.0, 1.0], gap="small")
            holding_choice = detail_cols[0].selectbox(
                "기존 보유 종목",
                holding_options,
                key="standard_transaction_existing_holding",
                help="매도할 때 선택하면 입력한 종목 대신 보유 종목의 티커와 시장을 사용합니다.",
            )
            currency = detail_cols[1].selectbox(
                "거래통화",
                currency_options,
                index=currency_options.index(default_currency) if default_currency in currency_options else 0,
                help="시장 기준 자동을 선택하면 KR은 KRW, US는 USD로 처리합니다.",
            )
            fee = detail_cols[2].number_input("수수료", min_value=0.0, step=0.01, format="%.2f", help="없으면 0으로 둡니다.")
            tax = detail_cols[3].number_input("세금", min_value=0.0, step=0.01, format="%.2f", help="없으면 0으로 둡니다.")
            note = st.text_input("메모", placeholder="선택 입력", help="계좌명, 거래 사유 등 필요한 내용을 남길 수 있습니다.")
    if submitted:
        selected_holding = holdings_by_label.get(holding_choice)
        raw_row: dict[str, object] = {
            "transaction_type": transaction_type,
            "market": str(selected_holding.get("market")) if selected_holding else market,
            "currency": currency,
            "ticker_or_name": str(selected_holding.get("ticker")) if selected_holding else ticker_or_name,
            "display_name": selected_holding.get("display_name") if selected_holding else "",
            "unit_price": unit_price,
            "quantity": quantity,
            "fee": fee,
            "tax": tax,
            "occurred_at": occurred_at.isoformat(),
            "note": note,
        }
        errors = validate_trade_input(
            raw_row,
            existing_holdings=st.session_state.get("holdings_rows", []),
            korea_listing_records=_cached_korea_listing_records(),
        )
        if errors:
            _set_message("\n".join(errors))
            return
        try:
            _build_preview([normalize_trade_input(raw_row)], auto_market_hint=market == "자동감지" and selected_holding is None)
        except ValueError as exc:
            _set_message(str(exc))


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
    with st.expander("고급 입력 · 빠른 입력", expanded=False):
        st.caption("행을 추가해 여러 거래를 한 번에 입력합니다. 구분은 매입 또는 매도, 체결단가는 국내 종목은 원화·미국 종목은 달러 기준입니다.")
        quick_frame = st.data_editor(
            _empty_quick_frame(),
            key="quick_transactions_editor",
            num_rows="dynamic",
            width="stretch",
            column_config={
                "transaction_type": st.column_config.SelectboxColumn("구분", options=["매입", "매도"], required=True),
                "ticker_or_name": st.column_config.TextColumn("주식명", required=True, help="예: 삼성전자, 005930, MU, QURE"),
                "unit_price": st.column_config.NumberColumn("체결단가", min_value=0.0, step=0.01, required=True, format="%,.2f"),
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
    with st.expander("고급 입력 · CSV 업로드", expanded=False):
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
                "unit_price": st.column_config.NumberColumn("체결단가", min_value=0.0, step=0.01, required=True, format="%,.2f"),
                "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, required=True, format="%,.4f"),
                "fee": st.column_config.NumberColumn("수수료", min_value=0.0, step=0.01, format="%,.2f"),
                "tax": st.column_config.NumberColumn("세금", min_value=0.0, step=0.01, format="%,.2f"),
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
                st.error(_format_transaction_error(exc))


def render_transaction_editor() -> None:
    st.subheader("자산 입력")
    st.caption("자산 입력은 매입/매도 거래로 관리합니다. 거래를 입력하면 전체 보유현황과 평균단가가 자동으로 다시 계산됩니다.")
    _render_legacy_holdings_migration()
    _render_standard_transaction_form()
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
