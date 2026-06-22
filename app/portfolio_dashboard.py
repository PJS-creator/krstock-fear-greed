from __future__ import annotations

from io import BytesIO
from pathlib import Path
import hashlib
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


_ensure_project_root_on_path()

import pandas as pd
import streamlit as st

from portfolio.analytics import build_portfolio_snapshot
from portfolio.auth import (
    AppSecurityConfig,
    config_from_secrets,
    should_disable_price_update,
    should_lock_entire_app,
    should_lock_manual_mode,
    verify_password,
)
from portfolio.manual_input import (
    PORTFOLIO_CSV_COLUMNS,
    csv_template,
    normalize_portfolio_row,
    normalize_portfolio_rows,
    positions_quotes_to_rows,
    rows_to_csv,
    rows_to_positions_quotes,
)
from portfolio.models import PortfolioSnapshot
from portfolio.pricing import build_alpha_vantage_provider, update_us_quotes
from portfolio.sample_data import sample_portfolio
from portfolio.storage import (
    PortfolioRecord,
    PortfolioStore,
    PortfolioStoreError,
    SupabaseStorageConfig,
    build_supabase_store,
    deserialize_portfolio_payload,
    serialize_portfolio_payload,
    should_enable_storage,
    supabase_config_from_secrets,
)

SAMPLE_MODE = "샘플 포트폴리오 사용"
MANUAL_MODE = "내 포트폴리오 직접 입력"
AUTHENTICATED_KEY = "is_authenticated"
PENDING_PORTFOLIO_LOAD_KEY = "pending_portfolio_load"
STORAGE_STATUS_KEY = "storage_status_message"
UNPROTECTED_WARNING = "공개 앱에서 API key quota 보호를 위해 APP_PASSWORD 설정을 권장합니다."
STORAGE_UNCONFIGURED_MESSAGE = "저장소가 설정되지 않아 CSV 방식만 사용할 수 있습니다"
STORAGE_PASSWORD_WARNING = "저장/불러오기는 APP_PASSWORD를 설정한 인증 사용자에게만 사용할 수 있습니다. CSV 방식만 사용할 수 있습니다."


def krw(value: float) -> str:
    return f"₩{value:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:,.2f}%"


def _read_security_config() -> AppSecurityConfig:
    try:
        secrets = {
            "APP_PASSWORD": st.secrets.get("APP_PASSWORD", ""),
            "APP_AUTH_SCOPE": st.secrets.get("APP_AUTH_SCOPE", ""),
            "ALPHA_VANTAGE_API_KEY": st.secrets.get("ALPHA_VANTAGE_API_KEY", ""),
        }
    except Exception:
        secrets = {}
    return config_from_secrets(secrets)


def _read_storage_config() -> SupabaseStorageConfig:
    try:
        secrets = {
            "SUPABASE_URL": st.secrets.get("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_ROLE_KEY": st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            "PORTFOLIO_OWNER_ID": st.secrets.get("PORTFOLIO_OWNER_ID", ""),
        }
    except Exception:
        secrets = {}
    return supabase_config_from_secrets(secrets)


def _initialize_session_state() -> None:
    st.session_state.setdefault("manual_portfolio_rows", [])
    st.session_state.setdefault("manual_upload_token", None)
    st.session_state.setdefault("manual_usd_krw", 1380.0)
    st.session_state.setdefault("manual_cash_krw", 0.0)
    st.session_state.setdefault("price_update_statuses", [])
    st.session_state.setdefault(PENDING_PORTFOLIO_LOAD_KEY, None)
    st.session_state.setdefault(AUTHENTICATED_KEY, False)


def _apply_pending_portfolio_load() -> None:
    pending = st.session_state.get(PENDING_PORTFOLIO_LOAD_KEY)
    if not pending:
        return
    del st.session_state[PENDING_PORTFOLIO_LOAD_KEY]
    st.session_state.manual_portfolio_rows = pending["rows"]
    st.session_state.manual_usd_krw = pending["usd_krw"]
    st.session_state.manual_cash_krw = pending["cash_krw"]
    st.session_state.manual_upload_token = None
    st.session_state.price_update_statuses = []


def _is_authenticated() -> bool:
    return bool(st.session_state.get(AUTHENTICATED_KEY, False))


def _set_storage_status(message: str) -> None:
    st.session_state[STORAGE_STATUS_KEY] = message


def _render_storage_status() -> None:
    message = st.session_state.get(STORAGE_STATUS_KEY)
    if not message:
        return
    del st.session_state[STORAGE_STATUS_KEY]
    st.success(message)


def _render_login_form(config: AppSecurityConfig) -> None:
    st.title("Personal Portfolio Control Panel")
    st.subheader("비밀번호가 필요합니다")
    st.caption("공개 앱의 포트폴리오 입력 기능과 API quota를 보호하기 위한 개인용 경량 보호입니다.")
    with st.form("password_form"):
        candidate_password = st.text_input("APP_PASSWORD", type="password")
        submitted = st.form_submit_button("로그인")
    if submitted:
        if verify_password(candidate_password, config.app_password):
            st.session_state[AUTHENTICATED_KEY] = True
            st.rerun()
        st.error("비밀번호가 올바르지 않습니다.")
    st.stop()


def _render_security_status(config: AppSecurityConfig) -> None:
    if not config.has_password:
        st.warning(UNPROTECTED_WARNING)
        return
    with st.sidebar:
        if _is_authenticated():
            st.success("인증됨")
            if st.button("로그아웃"):
                st.session_state[AUTHENTICATED_KEY] = False
                st.session_state.price_update_statuses = []
                st.rerun()
        else:
            st.info("샘플 모드는 공개 상태입니다. 직접 입력 모드는 비밀번호가 필요합니다.")


def _snapshot_frame(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    rows = []
    for item in snapshot.positions:
        rows.append(
            {
                "시장": item.position.market,
                "티커": item.position.symbol,
                "종목명": item.position.name,
                "전략": item.position.strategy_tag,
                "수량": item.position.quantity,
                "평균단가": item.position.avg_price,
                "현재가": item.quote.price,
                "평가액(KRW)": round(item.market_value_krw),
                "일간손익(KRW)": round(item.day_pnl_krw),
                "총손익(KRW)": round(item.total_pnl_krw),
                "총수익률": item.total_pnl_pct,
                "현재비중": item.weight,
                "목표비중": item.position.target_weight,
                "비중차이": item.target_gap,
            }
        )
    return pd.DataFrame(rows)


def _render_snapshot(snapshot: PortfolioSnapshot) -> None:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("총자산", krw(snapshot.total_value_krw))
    col2.metric("오늘 손익", krw(snapshot.day_pnl_krw))
    col3.metric("총 손익", krw(snapshot.total_pnl_krw))
    col4.metric("총수익률", pct(snapshot.total_pnl_pct))
    col5.metric("현금 비중", pct(snapshot.cash_krw / snapshot.total_value_krw if snapshot.total_value_krw else 0))

    frame = _snapshot_frame(snapshot)
    st.subheader("Action Board")
    if frame.empty:
        st.info("입력된 종목이 없습니다. 현금만 반영한 상태입니다.")
    else:
        left, right = st.columns(2)
        overweight = frame.sort_values("비중차이", ascending=False).iloc[0]
        underweight = frame.sort_values("비중차이", ascending=True).iloc[0]
        left.warning(f"목표 비중 초과: {overweight['종목명']} ({overweight['비중차이'] * 100:.2f}%p)")
        right.info(f"목표 비중 미달: {underweight['종목명']} ({underweight['비중차이'] * 100:.2f}%p)")

    st.subheader("보유 종목")
    if frame.empty:
        st.dataframe(pd.DataFrame(columns=["시장", "티커", "종목명", "평가액(KRW)", "현재비중", "비중차이"]), use_container_width=True)
    else:
        st.dataframe(
            frame.style.format(
                {
                    "평균단가": "{:,.2f}",
                    "현재가": "{:,.2f}",
                    "평가액(KRW)": "{:,.0f}",
                    "일간손익(KRW)": "{:,.0f}",
                    "총손익(KRW)": "{:,.0f}",
                    "총수익률": "{:.2%}",
                    "현재비중": "{:.2%}",
                    "목표비중": "{:.2%}",
                    "비중차이": "{:.2%}",
                }
            ),
            use_container_width=True,
        )

    st.subheader("전략 태그별 평가액")
    if frame.empty:
        st.bar_chart(pd.DataFrame({"전략": [], "평가액(KRW)": []}), x="전략", y="평가액(KRW)")
    else:
        tag_frame = frame.groupby("전략", as_index=False)["평가액(KRW)"].sum()
        st.bar_chart(tag_frame, x="전략", y="평가액(KRW)")


def _render_csv_tools() -> None:
    uploaded_file = st.file_uploader("CSV 업로드", type=["csv"])
    if uploaded_file is not None:
        uploaded_bytes = uploaded_file.getvalue()
        upload_token = hashlib.sha256(uploaded_bytes).hexdigest()
        if st.session_state.manual_upload_token != upload_token:
            try:
                uploaded_frame = pd.read_csv(BytesIO(uploaded_bytes), dtype=str)
                st.session_state.manual_portfolio_rows = normalize_portfolio_rows(uploaded_frame.to_dict("records"))
                st.session_state.manual_upload_token = upload_token
                st.session_state.price_update_statuses = []
                st.success("CSV 포트폴리오를 불러왔습니다.")
            except ValueError as exc:
                st.error(f"CSV를 불러올 수 없습니다: {exc}")

    col1, col2 = st.columns(2)
    col1.download_button(
        "CSV 템플릿 다운로드",
        data=csv_template(),
        file_name="portfolio_template.csv",
        mime="text/csv",
    )
    col2.download_button(
        "현재 포트폴리오 CSV 다운로드",
        data=rows_to_csv(st.session_state.manual_portfolio_rows),
        file_name="portfolio.csv",
        mime="text/csv",
        disabled=not st.session_state.manual_portfolio_rows,
    )


def _render_add_position_form() -> None:
    with st.form("manual_position_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        market = col1.selectbox("market", ["KR", "US"])
        symbol = col2.text_input("symbol")
        name = col3.text_input("name")

        col4, col5, col6 = st.columns(3)
        currency = col4.selectbox("currency", ["KRW", "USD"])
        quantity = col5.number_input("quantity", min_value=0.0, value=0.0, step=1.0)
        avg_price = col6.number_input("avg_price", min_value=0.0, value=0.0, step=100.0)

        col7, col8, col9 = st.columns(3)
        current_price = col7.number_input("current_price", min_value=0.0, value=0.0, step=100.0)
        previous_close = col8.number_input("previous_close", min_value=0.0, value=0.0, step=100.0)
        target_weight = col9.number_input("target_weight", min_value=0.0, value=0.0, step=0.01, format="%.4f")

        strategy_tag = st.text_input("strategy_tag", value="Manual")
        submitted = st.form_submit_button("종목 추가")

    if submitted:
        raw_row = {
            "market": market,
            "symbol": symbol,
            "name": name,
            "currency": currency,
            "quantity": quantity,
            "avg_price": avg_price,
            "current_price": current_price,
            "previous_close": previous_close,
            "target_weight": target_weight,
            "strategy_tag": strategy_tag,
        }
        try:
            next_rows = [*st.session_state.manual_portfolio_rows, normalize_portfolio_row(raw_row)]
            rows_to_positions_quotes(next_rows)
            st.session_state.manual_portfolio_rows = next_rows
            st.session_state.price_update_statuses = []
            st.success("종목이 추가되었습니다.")
        except ValueError as exc:
            st.error(f"종목을 추가할 수 없습니다: {exc}")


def _render_price_update_statuses() -> None:
    for status in st.session_state.price_update_statuses:
        text = f"{status.symbol}: {status.message}"
        if status.status == "updated":
            st.success(text)
        elif status.status in {"failed", "missing_api_key"}:
            st.warning(text)
        else:
            st.info(text)


def _render_price_update_control(config: AppSecurityConfig) -> None:
    st.subheader("미국 주식 가격 자동 업데이트")
    st.caption("Alpha Vantage API key가 Streamlit secrets에 있을 때만 US/USD 종목의 현재가와 전일종가를 갱신합니다. 한국/KRW 종목은 수동 입력을 유지합니다.")
    disable_for_security = should_disable_price_update(config)
    if disable_for_security:
        st.warning(f"{UNPROTECTED_WARNING} APP_PASSWORD가 없어 가격 자동 업데이트 버튼을 비활성화했습니다.")
    if st.button("미국 주식 가격 자동 업데이트", disabled=not st.session_state.manual_portfolio_rows or disable_for_security):
        provider = build_alpha_vantage_provider(config.alpha_vantage_api_key)
        try:
            updated_rows, statuses = update_us_quotes(st.session_state.manual_portfolio_rows, provider)
            st.session_state.manual_portfolio_rows = updated_rows
            st.session_state.price_update_statuses = statuses
        except ValueError as exc:
            st.error(f"가격 업데이트를 실행할 수 없습니다: {exc}")
            st.session_state.price_update_statuses = []
    _render_price_update_statuses()


def _record_label(record: PortfolioRecord) -> str:
    changed_at = record.updated_at or record.created_at or ""
    if changed_at:
        return f"{record.portfolio_name} ({changed_at[:10]})"
    return record.portfolio_name


def _render_storage_tools(usd_krw: float, cash_krw: float, security_config: AppSecurityConfig) -> None:
    st.subheader("포트폴리오 저장/불러오기")
    _render_storage_status()

    storage_config = _read_storage_config()
    if not should_enable_storage(storage_config):
        st.info(STORAGE_UNCONFIGURED_MESSAGE)
        return
    if not security_config.has_password:
        st.warning(STORAGE_PASSWORD_WARNING)
        return

    try:
        store: PortfolioStore | None = build_supabase_store(storage_config)
    except PortfolioStoreError as exc:
        st.warning(f"저장소를 초기화할 수 없습니다: {exc}")
        return
    if store is None or storage_config.owner_id is None:
        st.info(STORAGE_UNCONFIGURED_MESSAGE)
        return

    with st.form("portfolio_save_form"):
        st.text_input("portfolio_name", key="portfolio_save_name")
        save_submitted = st.form_submit_button("현재 포트폴리오 저장")
    if save_submitted:
        portfolio_name = str(st.session_state.get("portfolio_save_name", "")).strip()
        if not portfolio_name:
            st.error("portfolio_name을 입력하세요.")
        else:
            try:
                payload = serialize_portfolio_payload(st.session_state.manual_portfolio_rows, usd_krw, cash_krw)
                store.save_portfolio(storage_config.owner_id, portfolio_name, payload)
                _set_storage_status(f"{portfolio_name} 포트폴리오를 저장했습니다.")
                st.rerun()
            except (PortfolioStoreError, ValueError) as exc:
                st.error(f"포트폴리오를 저장할 수 없습니다: {exc}")

    try:
        records = store.list_portfolios(storage_config.owner_id)
    except PortfolioStoreError as exc:
        st.warning(f"저장된 포트폴리오 목록을 불러올 수 없습니다: {exc}")
        return

    if not records:
        st.info("저장된 포트폴리오가 없습니다.")
        return

    labels = {_record_label(record): record.portfolio_name for record in records}
    selected_label = st.selectbox("저장된 포트폴리오", options=list(labels.keys()))
    selected_name = labels[selected_label]

    load_col, delete_col = st.columns(2)
    if load_col.button("선택 포트폴리오 불러오기"):
        try:
            record = store.get_portfolio(storage_config.owner_id, selected_name)
            if record is None:
                st.error("선택한 포트폴리오를 찾을 수 없습니다.")
            else:
                rows, loaded_usd_krw, loaded_cash_krw = deserialize_portfolio_payload(record.payload_json)
                st.session_state[PENDING_PORTFOLIO_LOAD_KEY] = {
                    "rows": rows,
                    "usd_krw": loaded_usd_krw,
                    "cash_krw": loaded_cash_krw,
                }
                _set_storage_status(f"{selected_name} 포트폴리오를 불러왔습니다.")
                st.rerun()
        except (PortfolioStoreError, ValueError) as exc:
            st.error(f"포트폴리오를 불러올 수 없습니다: {exc}")

    st.warning("삭제하면 Supabase 저장소에서 선택한 포트폴리오가 제거됩니다.")
    confirm_delete = st.checkbox("선택한 포트폴리오를 삭제합니다", key=f"confirm_delete_portfolio_{selected_name}")
    if delete_col.button("선택 포트폴리오 삭제", disabled=not confirm_delete):
        try:
            deleted = store.delete_portfolio(storage_config.owner_id, selected_name)
            if deleted:
                _set_storage_status(f"{selected_name} 포트폴리오를 삭제했습니다.")
                st.rerun()
            else:
                st.error("선택한 포트폴리오를 찾을 수 없습니다.")
        except PortfolioStoreError as exc:
            st.error(f"포트폴리오를 삭제할 수 없습니다: {exc}")


def _render_delete_control() -> None:
    rows = st.session_state.manual_portfolio_rows
    if not rows:
        return
    options = {
        f"{index + 1}. {row['market']}:{row['symbol']} {row['name']}": index
        for index, row in enumerate(rows)
    }
    selected = st.selectbox("삭제할 종목", options=list(options.keys()))
    if st.button("선택 종목 삭제"):
        delete_index = options[selected]
        st.session_state.manual_portfolio_rows = [row for index, row in enumerate(rows) if index != delete_index]
        st.session_state.price_update_statuses = []
        st.rerun()


def _render_manual_mode(usd_krw: float, cash_krw: float, config: AppSecurityConfig) -> None:
    st.subheader("내 포트폴리오 직접 입력")
    _render_csv_tools()
    _render_add_position_form()
    _render_price_update_control(config)
    _render_storage_tools(usd_krw, cash_krw, config)

    st.subheader("현재 포트폴리오 입력값")
    current_rows = st.session_state.manual_portfolio_rows
    st.dataframe(pd.DataFrame(current_rows, columns=PORTFOLIO_CSV_COLUMNS), use_container_width=True)
    _render_delete_control()

    try:
        positions, quotes = rows_to_positions_quotes(current_rows)
        snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)
    except ValueError as exc:
        st.error(f"포트폴리오를 계산할 수 없습니다: {exc}")
        st.stop()

    _render_snapshot(snapshot)


def _render_sample_mode(usd_krw: float, cash_krw: float) -> None:
    positions, quotes, _, _ = sample_portfolio()
    sample_rows = positions_quotes_to_rows(positions, quotes)
    st.subheader("샘플 포트폴리오")
    st.dataframe(pd.DataFrame(sample_rows, columns=PORTFOLIO_CSV_COLUMNS), use_container_width=True)
    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)
    _render_snapshot(snapshot)


st.set_page_config(page_title="Personal Portfolio Control Panel", layout="wide")
_initialize_session_state()
_apply_pending_portfolio_load()
security_config = _read_security_config()
if should_lock_entire_app(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)

st.title("Personal Portfolio Control Panel")
st.caption("샘플 포트폴리오 또는 브라우저 세션의 직접 입력 데이터로 계산하는 수동 입력형 포트폴리오 앱")
_render_security_status(security_config)

_, _, sample_usd_krw, sample_cash_krw = sample_portfolio()
with st.sidebar:
    mode = st.radio("포트폴리오 모드", [SAMPLE_MODE, MANUAL_MODE])
    if mode == SAMPLE_MODE:
        usd_krw = st.number_input("USD/KRW", min_value=0.01, value=float(sample_usd_krw), step=1.0)
        cash_krw = st.number_input("현금(KRW)", min_value=0.0, value=float(sample_cash_krw), step=100000.0)
    else:
        usd_krw = st.number_input("USD/KRW", min_value=0.01, value=float(st.session_state.manual_usd_krw), step=1.0)
        cash_krw = st.number_input("현금(KRW)", min_value=0.0, value=float(st.session_state.manual_cash_krw), step=100000.0)
        st.session_state.manual_usd_krw = float(usd_krw)
        st.session_state.manual_cash_krw = float(cash_krw)

if mode == SAMPLE_MODE:
    _render_sample_mode(usd_krw, cash_krw)
elif should_lock_manual_mode(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)
else:
    _render_manual_mode(usd_krw, cash_krw, security_config)
