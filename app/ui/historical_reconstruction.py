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
    csv_to_rows,
    daily_rows_as_dicts,
    deserialize_schedule_payload,
    holding_rows_as_dicts,
    holding_template_csv,
    normalize_cash_snapshots,
    normalize_holding_snapshots,
    reconstruct_historical_holdings,
    rows_to_csv,
    serialize_schedule_payload,
)
from portfolio.historical_holdings.price_provider import HistoricalPriceProvider

from .charts import plot_reconstructed_holdings_area, plot_reconstructed_total_value
from .components import render_plotly_chart
from .formatters import compact_krw, full_krw, percentage, signed_krw, signed_percentage
from .status import dirty_signature
from .theme import DIMENSIONS


HOLDINGS_STATE_KEY = "historical_holdings_schedule_rows"
CASH_STATE_KEY = "historical_cash_schedule_rows"
HOLDINGS_EDITOR_KEY = "historical_holdings_schedule_editor"
CASH_EDITOR_KEY = "historical_cash_schedule_editor"
RESULT_STATE_KEY = "historical_reconstruction_result"
RESULT_SIGNATURE_KEY = "historical_reconstruction_signature"
SCHEDULE_NAME_KEY = "historical_schedule_name"
NOTES_KEY = "historical_schedule_notes"
DEFAULT_HOLDING_ROWS = [
    {column: "" for column in HOLDINGS_COLUMNS},
]
DEFAULT_CASH_ROWS = [
    {"as_of_date": "", "cash_krw": 0.0, "cash_usd": 0.0, "usd_krw": ""},
]
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
    st.session_state.pop(HOLDINGS_EDITOR_KEY, None)
    st.session_state.pop(CASH_EDITOR_KEY, None)
    st.session_state[RESULT_STATE_KEY] = None


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
        labels = {f"{record.schedule_name} · {(record.updated_at or record.created_at or '')[:10] or '날짜 없음'}": record for record in records}
        selected_label = st.selectbox("저장된 스케줄", list(labels.keys()), key="historical_saved_schedule")
        selected = labels[selected_label]
        load_col, delete_col = st.columns(2)
        if load_col.button("선택 스케줄 불러오기", width="stretch"):
            try:
                payload = deserialize_schedule_payload(selected.payload_json)
                st.session_state[SCHEDULE_NAME_KEY] = selected.schedule_name
                st.session_state[NOTES_KEY] = payload["notes"]
                _replace_schedule_rows(payload["holdings_snapshots"], payload["cash_snapshots"])
                st.rerun()
            except (HistoricalScheduleStoreError, HistoricalHoldingsError) as exc:
                st.error(f"스케줄을 불러올 수 없습니다: {exc}")
        if delete_col.button("선택 스케줄 삭제", width="stretch"):
            try:
                schedule_store.delete_schedule(owner_id, selected.schedule_name)
                st.cache_data.clear()
                st.rerun()
            except HistoricalScheduleStoreError as exc:
                st.error(f"스케줄을 삭제할 수 없습니다: {exc}")

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


def _render_editors() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    st.caption("각 날짜의 입력값은 거래 이벤트가 아니라 그 날짜부터 유효한 전체 보유현황 스냅샷입니다. 새 날짜에 누락된 종목은 그 날짜부터 보유하지 않는 것으로 계산됩니다.")
    holdings_upload, cash_upload = st.columns(2)
    with holdings_upload.expander("보유현황 CSV 업로드", expanded=False):
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
    with cash_upload.expander("현금/환율 CSV 업로드", expanded=False):
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

    holdings_frame = pd.DataFrame(st.session_state.get(HOLDINGS_STATE_KEY, DEFAULT_HOLDING_ROWS), columns=HOLDINGS_COLUMNS)
    edited_holdings = st.data_editor(
        holdings_frame,
        key=HOLDINGS_EDITOR_KEY,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "as_of_date": st.column_config.TextColumn("as_of_date", help="YYYY-MM-DD"),
            "market": st.column_config.SelectboxColumn("market", options=["", "KR", "US"]),
            "ticker": st.column_config.TextColumn("ticker"),
            "quantity": st.column_config.NumberColumn("quantity", min_value=0.0, step=0.0001),
            "currency": st.column_config.SelectboxColumn("currency", options=["", "KRW", "USD"]),
        },
    )
    cash_frame = pd.DataFrame(st.session_state.get(CASH_STATE_KEY, DEFAULT_CASH_ROWS), columns=CASH_COLUMNS)
    edited_cash = st.data_editor(
        cash_frame,
        key=CASH_EDITOR_KEY,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "as_of_date": st.column_config.TextColumn("as_of_date", help="YYYY-MM-DD"),
            "cash_krw": st.column_config.NumberColumn("cash_krw", min_value=0.0, step=100000.0),
            "cash_usd": st.column_config.NumberColumn("cash_usd", min_value=0.0, step=100.0),
            "usd_krw": st.column_config.NumberColumn("usd_krw", min_value=0.01, step=1.0),
        },
    )
    holding_rows = _rows_from_editor(edited_holdings)
    cash_rows = _rows_from_editor(edited_cash)
    st.session_state[HOLDINGS_STATE_KEY] = holding_rows
    st.session_state[CASH_STATE_KEY] = cash_rows
    return holding_rows, cash_rows


def _date_bounds(holding_rows: list[dict[str, Any]]) -> tuple[date | None, date]:
    try:
        normalized = normalize_holding_snapshots(holding_rows)
    except HistoricalHoldingsError:
        return None, date.today()
    return min(row.as_of_date for row in normalized), date.today()


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
    st.dataframe(daily, hide_index=True, width="stretch", height=min(DIMENSIONS.max_table_height, 90 + len(daily) * DIMENSIONS.row_height))
    with st.expander("종목별 일별 평가 상세", expanded=False):
        st.dataframe(holdings, hide_index=True, width="stretch", height=min(DIMENSIONS.max_table_height, 90 + len(holdings) * DIMENSIONS.row_height))


def render_historical_reconstruction_tab(
    *,
    owner_id: str | None,
    schedule_store: HistoricalScheduleStore | None,
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
    holding_rows, cash_rows = _render_editors()
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

    if st.button("재구성 실행", type="primary", width="stretch"):
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
