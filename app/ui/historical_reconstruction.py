from __future__ import annotations

import time
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from portfolio.historical_holdings import (
    CASH_COLUMNS,
    HOLDINGS_COLUMNS,
    FinanceDataReaderHistoricalPriceProvider,
    HistoricalHoldingsError,
    HistoricalPriceProviderError,
    HistoricalReconstructionError,
    HistoricalScheduleStore,
    HistoricalScheduleStoreError,
    ReconstructionResult,
    cash_template_csv,
    current_cash_to_historical_snapshot,
    current_holdings_to_historical_snapshot,
    csv_to_rows,
    daily_rows_as_dicts,
    deserialize_schedule_payload,
    historical_cash_to_current_cash,
    historical_snapshot_to_current_holdings,
    holding_rows_as_dicts,
    holding_template_csv,
    normalize_cash_snapshots,
    normalize_holding_snapshots,
    reconstruct_historical_holdings,
    rows_to_csv,
    serialize_schedule_payload,
    upsert_cash_snapshot,
    upsert_historical_snapshot,
)
from portfolio.historical_holdings.price_provider import HistoricalPriceProvider
from portfolio.symbols import (
    EVENT_COLUMNS,
    SIMPLE_HISTORICAL_COLUMNS,
    build_input_preview,
    copy_previous_snapshot,
    csv_to_rows as simple_csv_to_rows,
    event_rows_to_snapshots,
    load_korea_listing_records,
    parse_symbol_quantity_lines,
    preview_rows_to_historical_snapshots,
    rows_to_csv as simple_rows_to_csv,
    snapshot_diff,
)

from .charts import plot_reconstructed_holdings_area, plot_reconstructed_total_value
from .components import render_plotly_chart
from .formatters import compact_krw, format_kst, format_number, format_price, full_krw, instrument_label, percentage, signed_krw, signed_percentage
from .status import dirty_signature
from .theme import DIMENSIONS


HOLDINGS_STATE_KEY = "historical_holdings_schedule_rows"
CASH_STATE_KEY = "historical_cash_schedule_rows"
HOLDINGS_EDITOR_KEY = "historical_holdings_schedule_editor"
CASH_EDITOR_KEY = "historical_cash_schedule_editor"
SIMPLE_EDITOR_KEY = "historical_simple_schedule_editor"
EVENT_EDITOR_KEY = "historical_event_schedule_editor"
EVENT_ROWS_KEY = "historical_event_rows"
INPUT_MODE_KEY = "historical_input_mode"
SIMPLE_PREVIEW_KEY = "historical_simple_preview_rows"
EVENT_PREVIEW_KEY = "historical_event_preview_rows"
RESULT_STATE_KEY = "historical_reconstruction_result"
RESULT_SIGNATURE_KEY = "historical_reconstruction_signature"
SCHEDULE_NAME_KEY = "historical_schedule_name"
NOTES_KEY = "historical_schedule_notes"
LINK_MESSAGE_KEY = "historical_current_portfolio_link_message"
PENDING_PORTFOLIO_STATE_KEY = "pending_portfolio_state"
DEFAULT_HOLDING_ROWS = [
    {column: "" for column in HOLDINGS_COLUMNS},
]
DEFAULT_CASH_ROWS = [
    {"as_of_date": "", "cash_krw": 0.0, "cash_usd": 0.0, "usd_krw": ""},
]
DEFAULT_SIMPLE_ROWS = [{"as_of_date": "", "ticker_or_name": "", "quantity": 0.0}]
DEFAULT_EVENT_ROWS = [{"date": "", "ticker_or_name": "", "quantity_after": 0.0}]
SAMPLE_HOLDINGS = [
    {"as_of_date": "2026-06-01", "market": "KR", "ticker": "005930", "quantity": 100, "display_name": "가상 삼성전자", "currency": "KRW"},
    {"as_of_date": "2026-06-07", "market": "KR", "ticker": "005930", "quantity": 200, "display_name": "가상 삼성전자", "currency": "KRW"},
    {"as_of_date": "2026-06-16", "market": "KR", "ticker": "005930", "quantity": 100, "display_name": "가상 삼성전자", "currency": "KRW"},
    {"as_of_date": "2026-06-16", "market": "KR", "ticker": "000660", "quantity": 10, "display_name": "가상 SK하이닉스", "currency": "KRW"},
]
SAMPLE_CASH = [{"as_of_date": "2026-06-01", "cash_krw": 1000000.0, "cash_usd": 0.0, "usd_krw": 1380.0}]


@st.cache_data(ttl=60, show_spinner=False)
def _list_schedules_cached(_store: HistoricalScheduleStore, owner_id: str):
    return _store.list_schedules(owner_id)


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def _fetch_close_prices_cached(market: str, ticker: str, start_date_text: str, end_date_text: str, cache_buster: int) -> dict[date, float]:
    del cache_buster
    return FinanceDataReaderHistoricalPriceProvider().get_close_prices(
        market=market,
        ticker=ticker,
        start_date=date.fromisoformat(start_date_text),
        end_date=date.fromisoformat(end_date_text),
    )


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def _fetch_usd_krw_cached(start_date_text: str, end_date_text: str, cache_buster: int) -> dict[date, float]:
    del cache_buster
    return FinanceDataReaderHistoricalPriceProvider().get_usd_krw_rates(
        start_date=date.fromisoformat(start_date_text),
        end_date=date.fromisoformat(end_date_text),
    )


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


class CachedStreamlitHistoricalPriceProvider:
    def __init__(self, *, cache_buster: int = 0) -> None:
        self.cache_buster = cache_buster

    def get_close_prices(self, *, market: str, ticker: str, start_date: date, end_date: date) -> dict[date, float]:
        return _fetch_close_prices_cached(market, ticker, start_date.isoformat(), end_date.isoformat(), self.cache_buster)

    def get_usd_krw_rates(self, *, start_date: date, end_date: date) -> dict[date, float]:
        return _fetch_usd_krw_cached(start_date.isoformat(), end_date.isoformat(), self.cache_buster)


def _ensure_state() -> None:
    st.session_state.setdefault(HOLDINGS_STATE_KEY, list(DEFAULT_HOLDING_ROWS))
    st.session_state.setdefault(CASH_STATE_KEY, list(DEFAULT_CASH_ROWS))
    st.session_state.setdefault(EVENT_ROWS_KEY, list(DEFAULT_EVENT_ROWS))
    st.session_state.setdefault(INPUT_MODE_KEY, "전체 보유현황")
    st.session_state.setdefault(SCHEDULE_NAME_KEY, "main-historical")
    st.session_state.setdefault(NOTES_KEY, "")


def _input_signature(start_date: date | None, end_date: date | None) -> str:
    return dirty_signature(
        {
            "holdings": st.session_state.get(HOLDINGS_STATE_KEY, []),
            "cash": st.session_state.get(CASH_STATE_KEY, []),
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }
    )


def _rows_from_editor(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        return value.fillna("").to_dict("records")
    return list(value or [])


def _replace_schedule_rows(holdings: list[dict[str, Any]], cash: list[dict[str, Any]]) -> None:
    st.session_state[HOLDINGS_STATE_KEY] = list(holdings)
    st.session_state[CASH_STATE_KEY] = list(cash)
    _clear_schedule_edit_state()


def _clear_schedule_edit_state() -> None:
    st.session_state.pop(HOLDINGS_EDITOR_KEY, None)
    st.session_state.pop(CASH_EDITOR_KEY, None)
    st.session_state.pop(SIMPLE_EDITOR_KEY, None)
    st.session_state.pop(EVENT_EDITOR_KEY, None)
    st.session_state[EVENT_ROWS_KEY] = list(DEFAULT_EVENT_ROWS)
    st.session_state.pop(SIMPLE_PREVIEW_KEY, None)
    st.session_state.pop(EVENT_PREVIEW_KEY, None)
    st.session_state[RESULT_STATE_KEY] = None


def _simple_rows_from_holdings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if not any(_clean_row_value(row.get(column)) for column in ("as_of_date", "ticker", "quantity")):
            continue
        output.append(
            {
                "as_of_date": row.get("as_of_date", ""),
                "ticker_or_name": row.get("display_name") or row.get("ticker", ""),
                "quantity": row.get("quantity", 0.0),
            }
        )
    return output or list(DEFAULT_SIMPLE_ROWS)


def _clean_row_value(value: object) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except TypeError:
        pass
    return str(value).strip()


def _render_preview_rows(preview_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for row in preview_rows:
        next_row = dict(row)
        candidates = list(next_row.get("candidates") or [])
        if next_row.get("status") == "candidate_required" and candidates:
            labels = [f"{candidate['ticker']} · {candidate['display_name']}" for candidate in candidates]
            selected_label = st.selectbox(f"{next_row.get('row_number')}행 후보 선택", labels, key=f"historical_candidate_{next_row.get('row_number')}")
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
    if resolved:
        total = len(resolved)
        ok = sum(1 for row in resolved if row.get("status") == "ok")
        candidate = sum(1 for row in resolved if row.get("status") == "candidate_required")
        error = sum(1 for row in resolved if row.get("status") == "error")
        st.caption(f"입력 {total}행 · 인식 성공 {ok} · 후보 선택 필요 {candidate} · 오류 {error}")
        frame = pd.DataFrame(
            resolved,
            columns=["as_of_date", "raw_input", "ticker", "display_name", "market", "currency", "quantity", "quantity_after", "status", "message"],
        ).rename(
            columns={
                "as_of_date": "기준일",
                "raw_input": "입력값",
                "ticker": "티커",
                "display_name": "표시명",
                "market": "시장",
                "currency": "통화",
                "quantity": "수량",
                "quantity_after": "변경 후 수량",
                "status": "상태",
                "message": "메시지",
            }
        )
        st.dataframe(
            frame,
            hide_index=True,
            width="stretch",
            height=min(DIMENSIONS.max_table_height, 90 + len(frame) * DIMENSIONS.row_height),
            column_config={
                "수량": st.column_config.NumberColumn("수량", format="%,.4f"),
                "변경 후 수량": st.column_config.NumberColumn("변경 후 수량", format="%,.4f"),
            },
        )
    return resolved


def _group_rows_by_date(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        date_text = _clean_row_value(row.get("as_of_date"))[:10]
        if not date_text:
            continue
        grouped.setdefault(date_text, []).append(dict(row))
    return dict(sorted(grouped.items()))


def _render_snapshot_cards(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    grouped = _group_rows_by_date(rows)
    if not grouped:
        return rows, False
    st.subheader("기준일 보유현황")
    combined: list[dict[str, Any]] = []
    previous_rows: list[dict[str, Any]] = []
    has_unconfirmed_removal = False
    for date_text, date_rows in grouped.items():
        diff = snapshot_diff(previous_rows, date_rows) if previous_rows else {"new": [], "removed": [], "increased": [], "decreased": [], "unchanged": []}
        total_quantity = sum(float(row.get("quantity") or 0) for row in date_rows)
        changed_count = len(diff["new"]) + len(diff["removed"]) + len(diff["increased"]) + len(diff["decreased"])
        with st.expander(f"{date_text} · {len(date_rows)}종목 · 총수량 {total_quantity:,.4g} · 변경 {changed_count}개", expanded=False):
            if diff["new"]:
                st.caption("신규 종목: " + ", ".join(diff["new"]))
            if diff["increased"]:
                st.caption("수량 증가: " + ", ".join(diff["increased"]))
            if diff["decreased"]:
                st.caption("수량 감소: " + ", ".join(diff["decreased"]))
            if diff["removed"]:
                st.warning("이 날짜부터 아래 종목은 보유 종료로 처리됩니다: " + ", ".join(diff["removed"]))
                confirmed = st.checkbox("위 보유 종료를 확인했습니다", key=f"confirm_removed_{date_text}")
                has_unconfirmed_removal = has_unconfirmed_removal or not confirmed
            edited = st.data_editor(
                pd.DataFrame(date_rows, columns=HOLDINGS_COLUMNS),
                key=f"historical_snapshot_card_{date_text}",
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                column_config={
                    "as_of_date": st.column_config.TextColumn("기준일"),
                    "ticker": st.column_config.TextColumn("티커"),
                    "display_name": st.column_config.TextColumn("표시명"),
                    "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, format="%,.4f"),
                    "market": st.column_config.SelectboxColumn("시장", options=["KR", "US"]),
                    "currency": st.column_config.SelectboxColumn("통화", options=["KRW", "USD"]),
                },
            )
            combined.extend(_rows_from_editor(edited))
        previous_rows = date_rows
    return combined, has_unconfirmed_removal


def _render_add_date_controls(holding_rows: list[dict[str, Any]]) -> None:
    add_col1, add_col2 = st.columns([1, 2])
    new_date = add_col1.date_input("추가할 기준일", value=date.today(), key="historical_new_snapshot_date")
    if add_col2.button("날짜 추가 - 직전 보유현황 복사", width="stretch"):
        copied = copy_previous_snapshot(holding_rows, new_date)
        if not copied:
            st.warning("복사할 직전 기준일 보유현황이 없습니다.")
            return
        existing_dates = {str(row.get("as_of_date"))[:10] for row in holding_rows}
        if new_date.isoformat() in existing_dates:
            st.warning("이미 같은 기준일이 있습니다.")
            return
        st.session_state[HOLDINGS_STATE_KEY] = holding_rows + copied
        st.session_state.pop(HOLDINGS_EDITOR_KEY, None)
        st.session_state.pop(SIMPLE_EDITOR_KEY, None)
        st.session_state[RESULT_STATE_KEY] = None
        st.rerun()


def _render_upload_preview(label: str, columns: list[str], key: str) -> list[dict[str, str]] | None:
    uploaded = st.file_uploader(label, type=["csv"], key=key)
    if uploaded is None:
        return None
    rows = csv_to_rows(uploaded.getvalue())
    frame = pd.DataFrame(rows, columns=columns)
    st.dataframe(frame, hide_index=True, width="stretch", height=min(DIMENSIONS.max_table_height, 90 + len(frame) * DIMENSIONS.row_height))
    return rows


def _render_schedule_controls(owner_id: str | None, schedule_store: HistoricalScheduleStore | None) -> None:
    st.subheader("보유현황 스케줄")
    control_col1, control_col2 = st.columns([2, 1])
    with control_col1:
        st.text_input("스케줄 이름", key=SCHEDULE_NAME_KEY)
        st.text_area("메모", key=NOTES_KEY, height=80)
    with control_col2:
        if st.button("샘플 스케줄 불러오기", width="stretch"):
            _replace_schedule_rows(list(SAMPLE_HOLDINGS), list(SAMPLE_CASH))
            st.rerun()
        st.download_button(
            "보유현황 CSV 템플릿",
            data=holding_template_csv().encode("utf-8-sig"),
            file_name="historical_holdings_template.csv",
            mime="text/csv",
            width="stretch",
        )
        st.download_button(
            "현금/환율 CSV 템플릿",
            data=cash_template_csv().encode("utf-8-sig"),
            file_name="historical_cash_template.csv",
            mime="text/csv",
            width="stretch",
        )

    if schedule_store is None or owner_id is None:
        st.caption("Supabase v0.8 migration이 없거나 저장소가 설정되지 않으면 스케줄 저장/불러오기는 비활성화되고 CSV 방식만 사용할 수 있습니다.")
        return
    try:
        records = _list_schedules_cached(schedule_store, owner_id)
    except HistoricalScheduleStoreError as exc:
        st.warning(f"과거 보유현황 스케줄 목록을 불러올 수 없습니다: {exc}")
        return
    if records:
        labels = {f"{record.schedule_name} · {format_kst(record.updated_at or record.created_at, compact=True)}": record for record in records}
        selected_label = st.selectbox("저장된 스케줄", list(labels.keys()), key="historical_saved_schedule")
        selected = labels[selected_label]
        load_col, delete_col = st.columns(2)
        confirm_load = st.checkbox("현재 입력을 선택 스케줄로 교체 확인", key=f"load_schedule_{selected.schedule_name}")
        if load_col.button("선택 스케줄 불러오기", width="stretch", disabled=not confirm_load):
            try:
                payload = deserialize_schedule_payload(selected.payload_json)
                st.session_state[SCHEDULE_NAME_KEY] = selected.schedule_name
                st.session_state[NOTES_KEY] = payload["notes"]
                _replace_schedule_rows(payload["holdings_snapshots"], payload["cash_snapshots"])
                st.rerun()
            except (HistoricalScheduleStoreError, HistoricalHoldingsError) as exc:
                st.error(f"스케줄을 불러올 수 없습니다: {exc}")
        confirm_delete = st.checkbox("선택 스케줄 삭제 확인", key=f"delete_schedule_{selected.schedule_name}")
        if delete_col.button("선택 스케줄 삭제", width="stretch", disabled=not confirm_delete):
            try:
                schedule_store.delete_schedule(owner_id, selected.schedule_name)
                st.cache_data.clear()
                st.rerun()
            except HistoricalScheduleStoreError as exc:
                st.error(f"스케줄을 삭제할 수 없습니다: {exc}")
        with st.expander("과거 보유현황 목록 이름 변경", expanded=False):
            new_name = st.text_input("새 이름", value=selected.schedule_name, key=f"rename_schedule_{selected.schedule_name}")
            confirm_rename = st.checkbox("선택한 목록 이름 변경 확인", key=f"confirm_rename_schedule_{selected.schedule_name}")
            if st.button("목록 이름 변경", disabled=not confirm_rename):
                clean_name = str(new_name or "").strip()
                if not clean_name:
                    st.error("새 이름을 입력하세요.")
                else:
                    try:
                        schedule_store.save_schedule(owner_id, clean_name, selected.payload_json)
                        if clean_name != selected.schedule_name:
                            schedule_store.delete_schedule(owner_id, selected.schedule_name)
                        st.cache_data.clear()
                        st.session_state[SCHEDULE_NAME_KEY] = clean_name
                        st.rerun()
                    except HistoricalScheduleStoreError as exc:
                        st.error(f"목록 이름을 변경할 수 없습니다: {exc}")

    if st.button("현재 스케줄 저장", width="stretch"):
        try:
            payload = serialize_schedule_payload(
                _rows_from_editor(st.session_state.get(HOLDINGS_STATE_KEY)),
                _rows_from_editor(st.session_state.get(CASH_STATE_KEY)),
                notes=st.session_state.get(NOTES_KEY, ""),
            )
            schedule_store.save_schedule(owner_id, str(st.session_state.get(SCHEDULE_NAME_KEY) or "main-historical"), payload)
            st.cache_data.clear()
            st.success("과거 보유현황 스케줄을 저장했습니다.")
        except (HistoricalScheduleStoreError, HistoricalHoldingsError) as exc:
            st.error(f"스케줄을 저장할 수 없습니다: {exc}")


def _render_current_portfolio_link_controls(
    *,
    holding_rows: list[dict[str, Any]],
    cash_rows: list[dict[str, Any]],
    current_holdings_rows: list[dict[str, Any]],
    current_cash_krw: float,
    current_cash_usd: float,
    current_usd_krw: float,
) -> None:
    st.subheader("현재 포트폴리오 연동")
    message = st.session_state.pop(LINK_MESSAGE_KEY, None)
    if message:
        st.success(message)
    st.caption(
        "과거 재구성 입력과 현재 보유자산은 자동으로 덮어쓰지 않습니다. 아래 버튼으로 적용 방향을 직접 선택하세요."
    )

    latest_snapshot_date: date | None = None
    latest_current_rows: list[dict[str, object]] = []
    latest_error: str | None = None
    try:
        latest_snapshot_date, latest_current_rows = historical_snapshot_to_current_holdings(holding_rows)
    except HistoricalHoldingsError as exc:
        latest_error = str(exc)

    import_col, apply_col = st.columns(2)
    with import_col:
        st.markdown("**현재 보유자산 → 과거 스케줄**")
        st.caption("현재 보유자산과 현금/환율을 선택한 기준일의 과거 보유현황으로 추가하거나 교체합니다.")
        snapshot_date = st.date_input("현재 보유자산을 넣을 기준일", value=date.today(), key="current_to_historical_date")
        confirm_import = st.checkbox("현재 보유자산을 과거 스케줄에 반영 확인", key="confirm_current_to_historical")
        if st.button(
            "현재 보유자산을 과거 스케줄에 반영",
            disabled=not current_holdings_rows or not confirm_import,
            width="stretch",
        ):
            try:
                snapshot_rows = current_holdings_to_historical_snapshot(current_holdings_rows, snapshot_date)
                cash_snapshot = current_cash_to_historical_snapshot(
                    as_of_date=snapshot_date,
                    cash_krw=current_cash_krw,
                    cash_usd=current_cash_usd,
                    usd_krw=current_usd_krw,
                )
                st.session_state[HOLDINGS_STATE_KEY] = upsert_historical_snapshot(holding_rows, snapshot_rows)
                st.session_state[CASH_STATE_KEY] = upsert_cash_snapshot(cash_rows, cash_snapshot)
                _clear_schedule_edit_state()
                st.session_state[LINK_MESSAGE_KEY] = f"{snapshot_date.isoformat()} 기준으로 현재 보유자산을 과거 스케줄에 반영했습니다."
                st.rerun()
            except (ValueError, HistoricalHoldingsError) as exc:
                st.error(f"현재 보유자산을 과거 스케줄에 반영할 수 없습니다: {exc}")
        if not current_holdings_rows:
            st.info("현재 보유자산이 비어 있어 추가할 수 없습니다.")

    with apply_col:
        st.markdown("**과거 스케줄 → 현재 보유자산**")
        if latest_snapshot_date is None:
            st.caption("적용할 수 있는 과거 보유현황이 아직 없습니다.")
            if latest_error:
                st.caption(latest_error)
        else:
            st.caption(f"최신 기준일 {latest_snapshot_date.isoformat()} · {len(latest_current_rows)}종목을 현재 포트폴리오로 가져옵니다.")
            cash_match = historical_cash_to_current_cash(cash_rows, as_of_date=latest_snapshot_date, current_usd_krw=current_usd_krw)
            if cash_match is None:
                st.caption("현금/환율 스케줄이 없으면 현재 사이드바 현금/환율은 유지됩니다.")
            else:
                cash_date, cash_state = cash_match
                st.caption(
                    f"현금/환율은 {cash_date.isoformat()} 기준 값을 함께 적용합니다: "
                    f"원화 {cash_state['cash_krw']:,.0f}, 달러 {cash_state['cash_usd']:,.2f}, 환율 {cash_state['usd_krw']:,.2f}"
                )
            confirm_apply = st.checkbox("최신 과거 보유현황을 현재 포트폴리오로 적용 확인", key="confirm_historical_to_current")
            if st.button("최신 기준일을 현재 포트폴리오로 적용", disabled=not confirm_apply, width="stretch"):
                pending_state: dict[str, Any] = {
                    "holdings_rows": latest_current_rows,
                    "price_update_statuses": [],
                    "last_price_refresh_at": None,
                    "mark_clean": False,
                }
                if cash_match is not None:
                    cash_date, cash_state = cash_match
                    pending_state.update(
                        {
                            "cash_krw": cash_state["cash_krw"],
                            "cash_usd": cash_state["cash_usd"],
                            "usd_krw": cash_state["usd_krw"],
                            "fx_status_message": f"{cash_date.isoformat()} 과거 현금/환율 스케줄에서 가져옴",
                            "fx_fetched_at": None,
                        }
                    )
                st.session_state[PENDING_PORTFOLIO_STATE_KEY] = pending_state
                st.session_state[LINK_MESSAGE_KEY] = (
                    f"{latest_snapshot_date.isoformat()} 기준 과거 보유현황을 현재 포트폴리오에 적용했습니다. "
                    "가격 새로고침 후 저장하면 실제 기록에도 반영됩니다."
                )
                st.rerun()


def _apply_simple_preview(preview_rows: list[dict[str, Any]], *, event_mode: bool = False) -> None:
    if any(row.get("status") != "ok" for row in preview_rows):
        st.error("후보 선택 또는 오류가 남아 있어 적용할 수 없습니다.")
        return
    if event_mode:
        event_rows = []
        for row in preview_rows:
            next_row = dict(row)
            next_row["quantity_after"] = row.get("quantity_after")
            event_rows.append(next_row)
        snapshots = event_rows_to_snapshots(event_rows)
    else:
        snapshots = preview_rows_to_historical_snapshots(preview_rows)
    try:
        normalize_holding_snapshots(snapshots)
    except HistoricalHoldingsError as exc:
        st.error(f"간편 입력을 적용할 수 없습니다: {exc}")
        return
    st.session_state[HOLDINGS_STATE_KEY] = snapshots
    st.session_state.pop(HOLDINGS_EDITOR_KEY, None)
    st.session_state.pop(SIMPLE_EDITOR_KEY, None)
    st.session_state.pop(EVENT_EDITOR_KEY, None)
    st.session_state.pop(SIMPLE_PREVIEW_KEY, None)
    st.session_state.pop(EVENT_PREVIEW_KEY, None)
    st.session_state[RESULT_STATE_KEY] = None
    st.rerun()


def _render_simple_snapshot_input() -> None:
    st.caption("각 날짜는 그 시점의 전체 보유현황입니다. 다음 날짜 전까지 유지됩니다.")
    simple_frame = pd.DataFrame(_simple_rows_from_holdings(st.session_state.get(HOLDINGS_STATE_KEY, DEFAULT_HOLDING_ROWS)), columns=SIMPLE_HISTORICAL_COLUMNS)
    edited = st.data_editor(
        simple_frame,
        key=SIMPLE_EDITOR_KEY,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "as_of_date": st.column_config.TextColumn("기준일", help="YYYY-MM-DD"),
            "ticker_or_name": st.column_config.TextColumn("종목명 또는 티커", help="예: 삼성전자, 005930, MU"),
            "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, format="%,.4f"),
        },
    )
    if st.button("보유현황 미리보기", key="historical_simple_preview_button"):
        preview = build_input_preview(edited.to_dict("records"), korea_listing_records=_cached_korea_listing_records(), require_date=True)
        st.session_state[SIMPLE_PREVIEW_KEY] = preview.rows
        st.session_state.pop(EVENT_PREVIEW_KEY, None)
        if preview.errors:
            st.warning("\n".join(preview.errors))

    preview_rows = list(st.session_state.get(SIMPLE_PREVIEW_KEY, []))
    if preview_rows:
        resolved = _render_preview_rows(preview_rows)
        if st.button("미리보기 적용", disabled=any(row.get("status") != "ok" for row in resolved), key="historical_apply_simple_preview"):
            _apply_simple_preview(resolved)


def _render_event_input() -> None:
    st.caption("이 모드는 매수/매도 금액을 계산하지 않고, 날짜별 총 보유수량만 업데이트합니다. quantity_after=0이면 그 날짜부터 보유 종료입니다.")
    event_frame = pd.DataFrame(st.session_state.get(EVENT_ROWS_KEY, DEFAULT_EVENT_ROWS), columns=EVENT_COLUMNS)
    edited = st.data_editor(
        event_frame,
        key=EVENT_EDITOR_KEY,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "date": st.column_config.TextColumn("기준일", help="YYYY-MM-DD"),
            "ticker_or_name": st.column_config.TextColumn("종목명 또는 티커"),
            "quantity_after": st.column_config.NumberColumn("변경 후 수량", min_value=0.0, step=0.0001, format="%,.4f"),
        },
    )
    if st.button("이벤트 변환 미리보기", key="historical_event_preview_button"):
        st.session_state[EVENT_ROWS_KEY] = edited.to_dict("records")
        st.session_state.pop(SIMPLE_PREVIEW_KEY, None)
        raw_rows = []
        for row in edited.to_dict("records"):
            next_row = dict(row)
            next_row["as_of_date"] = next_row.get("date")
            raw_rows.append(next_row)
        preview = build_input_preview(raw_rows, korea_listing_records=_cached_korea_listing_records(), require_date=True, quantity_field="quantity_after")
        st.session_state[EVENT_PREVIEW_KEY] = preview.rows
        if preview.errors:
            st.warning("\n".join(preview.errors))

    preview_rows = list(st.session_state.get(EVENT_PREVIEW_KEY, []))
    if preview_rows:
        resolved = _render_preview_rows(preview_rows)
        if all(row.get("status") == "ok" for row in resolved):
            converted = event_rows_to_snapshots(resolved)
            st.caption("snapshot 변환 결과")
            st.dataframe(pd.DataFrame(converted, columns=HOLDINGS_COLUMNS), hide_index=True, width="stretch")
        if st.button("이벤트 변환 결과 적용", disabled=any(row.get("status") != "ok" for row in resolved), key="historical_apply_event_preview"):
            _apply_simple_preview(resolved, event_mode=True)


def _render_editors(*, current_cash_krw: float, current_cash_usd: float, current_usd_krw: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    st.caption("각 날짜의 입력값은 거래 이벤트가 아니라 그 날짜부터 유효한 전체 보유현황입니다. 새 날짜에 누락된 종목은 그 날짜부터 보유하지 않는 것으로 계산됩니다.")
    input_mode = st.radio("입력 방식", ["전체 보유현황", "보유수량 변경 이벤트"], horizontal=True, key=INPUT_MODE_KEY)
    if input_mode == "전체 보유현황":
        _render_simple_snapshot_input()
    else:
        _render_event_input()

    holding_rows = list(st.session_state.get(HOLDINGS_STATE_KEY, DEFAULT_HOLDING_ROWS))
    _render_add_date_controls(holding_rows)
    card_rows, has_unconfirmed_removal = _render_snapshot_cards(holding_rows)
    if card_rows:
        st.session_state[HOLDINGS_STATE_KEY] = card_rows
        holding_rows = card_rows

    holdings_upload, cash_upload = st.columns(2)
    with holdings_upload.expander("CSV 업로드", expanded=False):
        st.download_button(
            "간편 CSV 템플릿",
            data=simple_rows_to_csv(
                [
                    {"as_of_date": "2026-06-01", "ticker_or_name": "삼성전자", "quantity": "100"},
                    {"as_of_date": "2026-06-16", "ticker_or_name": "SK하이닉스", "quantity": "10"},
                ],
                SIMPLE_HISTORICAL_COLUMNS,
            ).encode("utf-8-sig"),
            file_name="historical_simple_template.csv",
            mime="text/csv",
        )
        rows = _render_upload_preview("보유현황 CSV", HOLDINGS_COLUMNS, "historical_holdings_upload")
        if rows is not None and st.button("보유현황 CSV 적용"):
            try:
                normalize_holding_snapshots(rows)
                st.session_state[HOLDINGS_STATE_KEY] = rows
                st.session_state.pop(HOLDINGS_EDITOR_KEY, None)
                st.session_state[RESULT_STATE_KEY] = None
                st.rerun()
            except HistoricalHoldingsError as exc:
                st.error(f"보유현황 CSV 오류: {exc}")
        simple_upload = st.file_uploader("간편 CSV 업로드", type=["csv"], key="historical_simple_csv_upload")
        if simple_upload is not None and st.button("간편 CSV 미리보기"):
            preview = build_input_preview(simple_csv_to_rows(simple_upload.getvalue()), korea_listing_records=_cached_korea_listing_records(), require_date=True)
            st.session_state[SIMPLE_PREVIEW_KEY] = preview.rows
            st.session_state.pop(EVENT_PREVIEW_KEY, None)
            if preview.errors:
                st.warning("\n".join(preview.errors))
    with cash_upload.expander("현금/환율 CSV 업로드", expanded=False):
        st.caption("현금/환율은 선택 입력입니다. 비워 두면 0원/0달러와 현재 또는 historical 환율 fallback을 사용합니다.")
        if st.button("현재 현금/환율을 첫 기준일 기본값으로 가져오기"):
            first_date = next((str(row.get("as_of_date"))[:10] for row in holding_rows if str(row.get("as_of_date", "")).strip()), date.today().isoformat())
            st.session_state[CASH_STATE_KEY] = [{"as_of_date": first_date, "cash_krw": current_cash_krw, "cash_usd": current_cash_usd, "usd_krw": current_usd_krw}]
            st.session_state.pop(CASH_EDITOR_KEY, None)
            st.rerun()
        rows = _render_upload_preview("현금/환율 CSV", CASH_COLUMNS, "historical_cash_upload")
        if rows is not None and st.button("현금/환율 CSV 적용"):
            try:
                normalize_cash_snapshots(rows)
                st.session_state[CASH_STATE_KEY] = rows
                st.session_state.pop(CASH_EDITOR_KEY, None)
                st.session_state[RESULT_STATE_KEY] = None
                st.rerun()
            except HistoricalHoldingsError as exc:
                st.error(f"현금/환율 CSV 오류: {exc}")

    with st.expander("전체 컬럼 고급 편집", expanded=False):
        holdings_frame = pd.DataFrame(st.session_state.get(HOLDINGS_STATE_KEY, DEFAULT_HOLDING_ROWS), columns=HOLDINGS_COLUMNS)
        edited_holdings = st.data_editor(
            holdings_frame,
            key=HOLDINGS_EDITOR_KEY,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "as_of_date": st.column_config.TextColumn("기준일", help="YYYY-MM-DD"),
                "market": st.column_config.SelectboxColumn("시장", options=["", "KR", "US"]),
                "ticker": st.column_config.TextColumn("티커"),
                "quantity": st.column_config.NumberColumn("수량", min_value=0.0, step=0.0001, format="%,.4f"),
                "display_name": st.column_config.TextColumn("표시명"),
                "currency": st.column_config.SelectboxColumn("통화", options=["", "KRW", "USD"]),
                "account_name": st.column_config.TextColumn("계좌"),
                "strategy_tag": st.column_config.TextColumn("전략 태그"),
                "note": st.column_config.TextColumn("메모"),
            },
        )
        holding_rows = _rows_from_editor(edited_holdings)

    st.subheader("현금/환율")
    st.caption("현금/환율은 선택 입력입니다.")
    cash_frame = pd.DataFrame(st.session_state.get(CASH_STATE_KEY, DEFAULT_CASH_ROWS), columns=CASH_COLUMNS)
    edited_cash = st.data_editor(
        cash_frame,
        key=CASH_EDITOR_KEY,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "as_of_date": st.column_config.TextColumn("기준일", help="YYYY-MM-DD"),
            "cash_krw": st.column_config.NumberColumn("원화 현금", min_value=0.0, step=100000.0, format="%,.0f"),
            "cash_usd": st.column_config.NumberColumn("달러 현금", min_value=0.0, step=100.0, format="%,.2f"),
            "usd_krw": st.column_config.NumberColumn("환율", min_value=0.01, step=1.0, help="USD/KRW", format="%,.2f"),
        },
    )
    cash_rows = _rows_from_editor(edited_cash)
    st.session_state[HOLDINGS_STATE_KEY] = holding_rows
    st.session_state[CASH_STATE_KEY] = cash_rows
    return holding_rows, cash_rows, has_unconfirmed_removal


def _date_bounds(holding_rows: list[dict[str, Any]]) -> tuple[date | None, date]:
    try:
        normalized = normalize_holding_snapshots(holding_rows)
    except HistoricalHoldingsError:
        return None, date.today()
    return min(row.as_of_date for row in normalized), date.today()


def _daily_display_frame(daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in daily.to_dict("records"):
        rows.append(
            {
                "날짜": row.get("date"),
                "총자산": full_krw(row.get("total_value_krw")),
                "투자자산": full_krw(row.get("position_value_krw")),
                "현금": full_krw(row.get("cash_total_krw")),
                "원화 현금": full_krw(row.get("cash_krw")),
                "달러 현금": "$" + format_number(float(row.get("cash_usd") or 0), digits=2, trim=True),
                "환율": format_number(float(row.get("usd_krw") or 0), digits=2, trim=True),
                "보유 종목": f"{int(row.get('holdings_count') or 0):,}개",
                "평가 가능": f"{int(row.get('priced_count') or 0):,}개",
                "가격 누락": f"{int(row.get('missing_price_count') or 0):,}개",
                "적용 스냅샷": row.get("applied_snapshot_date"),
            }
        )
    return pd.DataFrame(rows)


def _holding_display_frame(holdings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in holdings.to_dict("records"):
        market_value = row.get("market_value_krw")
        rows.append(
            {
                "날짜": row.get("date"),
                "종목": instrument_label(row),
                "티커": row.get("ticker"),
                "시장": row.get("market"),
                "수량": format_number(float(row.get("quantity") or 0), digits=4, trim=True),
                "종가": format_price(row.get("close_price"), row.get("currency")),
                "평가액": full_krw(market_value) if market_value is not None else "가격 없음",
                "가격 상태": row.get("price_status"),
                "적용 스냅샷": row.get("applied_snapshot_date"),
            }
        )
    return pd.DataFrame(rows)


def _render_result(result: ReconstructionResult) -> None:
    if not result.daily_rows:
        st.warning("재구성 결과가 없습니다. 가격 데이터가 없거나 모든 종목 조회가 실패했을 수 있습니다.")
        return
    first = result.daily_rows[0]
    last = result.daily_rows[-1]
    change = last.total_value_krw - first.total_value_krw
    change_pct = change / first.total_value_krw if first.total_value_krw else None
    missing_tickers = sorted({row.ticker for row in result.holding_rows if row.market_value_krw is None} | set(result.failed_tickers))
    cols = st.columns(6)
    cols[0].metric("시작 총자산", compact_krw(first.total_value_krw), help=full_krw(first.total_value_krw), border=True)
    cols[1].metric("마지막 총자산", compact_krw(last.total_value_krw), help=full_krw(last.total_value_krw), border=True)
    cols[2].metric("기간 중 변화액", signed_krw(change), border=True)
    cols[3].metric(
        "기간 중 변화율",
        signed_percentage(change_pct),
        help="투자성과 수익률이 아니라 입력 보유현황 기준 총자산 평가액 변화율입니다.",
        border=True,
    )
    cols[4].metric("평가 가능 일수", f"{len(result.daily_rows)}일", border=True)
    cols[5].metric("가격 누락 종목", f"{len(missing_tickers)}개", help=", ".join(missing_tickers) or "없음", border=True)
    for warning in result.warnings:
        st.caption(f"{warning.message}")
    if result.failed_tickers:
        st.warning("가격 데이터 조회 실패 종목: " + ", ".join(result.failed_tickers))
    st.caption("보유현황 변경일의 급격한 변화는 매매, 입출금, 종목 교체가 섞인 스냅샷 평가액 변화일 수 있으며 투자성과 수익률로 해석하지 않습니다.")

    include_cash = st.toggle("총자산 기준으로 보기", value=True, key="historical_include_cash")
    total_fig = plot_reconstructed_total_value(result, include_cash=include_cash)
    if total_fig is not None:
        render_plotly_chart(total_fig, key="historical_total_reconstruction")
    area_fig = plot_reconstructed_holdings_area(result)
    if area_fig is not None:
        render_plotly_chart(area_fig, key="historical_holding_area")

    daily = pd.DataFrame(daily_rows_as_dicts(result.daily_rows))
    holdings = pd.DataFrame(holding_rows_as_dicts(result.holding_rows))
    st.download_button(
        "일별 총자산 CSV 다운로드",
        data=daily.to_csv(index=False).encode("utf-8-sig"),
        file_name="historical_daily_valuation.csv",
        mime="text/csv",
    )
    st.download_button(
        "종목별 평가 CSV 다운로드",
        data=holdings.to_csv(index=False).encode("utf-8-sig"),
        file_name="historical_holding_valuation.csv",
        mime="text/csv",
    )
    daily_display = _daily_display_frame(daily)
    holdings_display = _holding_display_frame(holdings)
    st.dataframe(
        daily_display,
        hide_index=True,
        width="stretch",
        height=min(DIMENSIONS.max_table_height, 90 + len(daily_display) * DIMENSIONS.row_height),
    )
    with st.expander("종목별 일별 평가 상세", expanded=False):
        st.dataframe(
            holdings_display,
            hide_index=True,
            width="stretch",
            height=min(DIMENSIONS.max_table_height, 90 + len(holdings_display) * DIMENSIONS.row_height),
        )


def render_historical_reconstruction_tab(
    *,
    owner_id: str | None,
    schedule_store: HistoricalScheduleStore | None,
    current_holdings_rows: list[dict[str, Any]],
    current_cash_krw: float,
    current_cash_usd: float,
    current_usd_krw: float,
    is_authenticated: bool,
) -> None:
    _ensure_state()
    st.subheader("과거 보유현황 기준 자산 재구성")
    st.info(
        "날짜별 입력은 거래내역이 아니라 전체 보유현황 스냅샷입니다. 각 스냅샷은 다음 입력 날짜 전까지 유지되고, 비거래일 입력은 다음 거래일에 적용됩니다."
    )
    if not is_authenticated:
        st.warning("과거 보유현황 재구성은 직접 입력/저장 기능과 동일하게 APP_PASSWORD 인증 후 사용할 수 있습니다.")
        return

    _render_schedule_controls(owner_id, schedule_store)
    holding_rows, cash_rows, has_unconfirmed_removal = _render_editors(
        current_cash_krw=current_cash_krw,
        current_cash_usd=current_cash_usd,
        current_usd_krw=current_usd_krw,
    )
    _render_current_portfolio_link_controls(
        holding_rows=holding_rows,
        cash_rows=cash_rows,
        current_holdings_rows=current_holdings_rows,
        current_cash_krw=current_cash_krw,
        current_cash_usd=current_cash_usd,
        current_usd_krw=current_usd_krw,
    )
    st.download_button(
        "현재 보유현황 스케줄 CSV 다운로드",
        data=rows_to_csv(holding_rows, HOLDINGS_COLUMNS).encode("utf-8-sig"),
        file_name="historical_holdings_schedule.csv",
        mime="text/csv",
    )
    st.download_button(
        "현재 현금/환율 스케줄 CSV 다운로드",
        data=rows_to_csv(cash_rows, CASH_COLUMNS).encode("utf-8-sig"),
        file_name="historical_cash_schedule.csv",
        mime="text/csv",
    )

    default_start, default_end = _date_bounds(holding_rows)
    period_col1, period_col2 = st.columns(2)
    start_value = period_col1.date_input("시작일", value=default_start or date.today(), key="historical_start_date")
    end_value = period_col2.date_input("종료일", value=default_end, key="historical_end_date")
    with st.expander("고급 설정", expanded=False):
        use_forward_fill = st.checkbox("가격이 없는 날짜에 전일 종가 forward-fill 사용", value=False)
        bypass_cache = st.checkbox("가격 데이터 캐시 무시하고 재조회", value=False)
        if st.button("가격 데이터 캐시 비우기"):
            _fetch_close_prices_cached.clear()
            _fetch_usd_krw_cached.clear()
            st.success("historical 가격 캐시를 비웠습니다.")

    signature = _input_signature(start_value, end_value)
    if st.session_state.get(RESULT_STATE_KEY) is not None and st.session_state.get(RESULT_SIGNATURE_KEY) != signature:
        st.warning("입력이 변경되어 재구성 결과가 오래되었을 수 있습니다. 다시 실행하세요.")

    if has_unconfirmed_removal:
        st.warning("보유 종료 확인이 필요한 기준일이 있습니다. 확인 후 재구성을 실행하세요.")

    if st.button("재구성 실행", type="primary", width="stretch", disabled=has_unconfirmed_removal):
        progress = st.progress(0, text="과거 종가 조회 준비 중")

        def update_progress(completed: int, total: int, symbol: str) -> None:
            progress.progress(int((completed / max(total, 1)) * 100), text=f"과거 종가 조회 중: {symbol} ({completed}/{total})")

        try:
            provider: HistoricalPriceProvider = CachedStreamlitHistoricalPriceProvider(
                cache_buster=time.time_ns() if bypass_cache else 0
            )
            result = reconstruct_historical_holdings(
                holding_rows,
                cash_rows,
                provider,
                start_date=start_value,
                end_date=end_value,
                current_usd_krw=current_usd_krw,
                use_forward_fill_prices=use_forward_fill,
                on_progress=update_progress,
            )
            st.session_state[RESULT_STATE_KEY] = result
            st.session_state[RESULT_SIGNATURE_KEY] = signature
        except (HistoricalHoldingsError, HistoricalPriceProviderError, HistoricalReconstructionError) as exc:
            st.error(f"재구성을 실행할 수 없습니다: {exc}")
        finally:
            progress.empty()

    result = st.session_state.get(RESULT_STATE_KEY)
    if isinstance(result, ReconstructionResult):
        _render_result(result)
