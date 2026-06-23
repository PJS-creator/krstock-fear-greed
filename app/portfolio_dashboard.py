from __future__ import annotations

from pathlib import Path
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


_ensure_project_root_on_path()

import streamlit as st

from app.ui.components import render_price_update_log
from app.ui.formatters import format_kst, format_relative_time
from app.ui.holdings import render_holdings_editor, render_holdings_table
from app.ui.history import render_history_tab
from app.ui.manage import render_csv_tools, render_manual_capture, render_storage_tools
from app.ui.overview import render_overview
from app.ui.status import aggregate_price_statuses, dirty_signature
from app.ui.styles import inject_styles
from portfolio.auth import (
    AppSecurityConfig,
    config_from_secrets,
    should_disable_price_update,
    should_lock_entire_app,
    should_lock_manual_mode,
    verify_password,
)
from portfolio.history import build_history_record, build_supabase_history_store
from portfolio.holdings import build_portfolio_metrics
from portfolio.pricing import build_alpha_vantage_provider, build_korea_quote_provider, refresh_holding_quotes, refresh_usd_krw
from portfolio.storage import (
    PortfolioStoreError,
    build_supabase_store,
    serialize_portfolio_payload,
    should_enable_storage,
    supabase_config_from_secrets,
)

AUTHENTICATED_KEY = "is_authenticated"
PORTFOLIO_NAME_KEY = "portfolio_name"
PORTFOLIO_NAME_INPUT_KEY = "portfolio_name_input"
PENDING_PORTFOLIO_NAME_KEY = "pending_portfolio_name"
PENDING_PORTFOLIO_STATE_KEY = "pending_portfolio_state"
SAVED_SIGNATURE_KEY = "saved_portfolio_signature"
MARK_CLEAN_KEY = "mark_portfolio_clean"
SAVE_STATUS_KEY = "portfolio_save_status_message"
UNPROTECTED_WARNING = "공개 앱에서 API key quota 보호를 위해 APP_PASSWORD 설정을 권장합니다."


def _clean_portfolio_name(value: object) -> str:
    return str(value or "main").strip() or "main"


def _current_portfolio_signature() -> str:
    return dirty_signature(
        {
            "portfolio_name": _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_KEY)),
            "holdings_rows": st.session_state.get("holdings_rows", []),
            "cash_krw": st.session_state.get("cash_krw", 0.0),
            "cash_usd": st.session_state.get("cash_usd", 0.0),
            "usd_krw": st.session_state.get("usd_krw", 1380.0),
        }
    )


def _mark_portfolio_clean() -> None:
    st.session_state[SAVED_SIGNATURE_KEY] = _current_portfolio_signature()


def _portfolio_is_dirty() -> bool:
    return st.session_state.get(SAVED_SIGNATURE_KEY) != _current_portfolio_signature()


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


def _read_storage_config():
    try:
        secrets = {
            "SUPABASE_URL": st.secrets.get("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_ROLE_KEY": st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            "PORTFOLIO_OWNER_ID": st.secrets.get("PORTFOLIO_OWNER_ID", ""),
        }
    except Exception:
        secrets = {}
    return supabase_config_from_secrets(secrets)


def _apply_pending_portfolio_state() -> None:
    pending_state = st.session_state.pop(PENDING_PORTFOLIO_STATE_KEY, None)
    if not isinstance(pending_state, dict):
        return
    loaded_portfolio_state = "portfolio_name" in pending_state or "holdings_rows" in pending_state
    if "portfolio_name" in pending_state:
        clean_name = _clean_portfolio_name(pending_state["portfolio_name"])
        st.session_state[PORTFOLIO_NAME_KEY] = clean_name
        st.session_state[PORTFOLIO_NAME_INPUT_KEY] = clean_name
    for key in ("holdings_rows", "cash_krw", "cash_usd", "usd_krw", "fx_status_message", "fx_fetched_at"):
        if key in pending_state:
            st.session_state[key] = pending_state[key]
    if loaded_portfolio_state:
        st.session_state[MARK_CLEAN_KEY] = True


def _initialize_session_state() -> None:
    st.session_state.setdefault(AUTHENTICATED_KEY, False)
    st.session_state.setdefault(PORTFOLIO_NAME_KEY, "main")
    pending_portfolio_name = st.session_state.pop(PENDING_PORTFOLIO_NAME_KEY, None)
    if pending_portfolio_name is not None:
        clean_name = _clean_portfolio_name(pending_portfolio_name)
        st.session_state[PORTFOLIO_NAME_KEY] = clean_name
        st.session_state[PORTFOLIO_NAME_INPUT_KEY] = clean_name
        st.session_state[MARK_CLEAN_KEY] = True
    _apply_pending_portfolio_state()
    st.session_state.setdefault(PORTFOLIO_NAME_INPUT_KEY, st.session_state[PORTFOLIO_NAME_KEY])
    st.session_state.setdefault("holdings_rows", [])
    st.session_state.setdefault("cash_krw", 0.0)
    st.session_state.setdefault("cash_usd", 0.0)
    st.session_state.setdefault("usd_krw", 1380.0)
    st.session_state.setdefault("fx_status_message", "수동 USD/KRW 환율")
    st.session_state.setdefault("fx_fetched_at", None)
    st.session_state.setdefault("price_update_statuses", [])
    st.session_state.setdefault("last_price_refresh_at", None)
    if st.session_state.pop(MARK_CLEAN_KEY, False) or SAVED_SIGNATURE_KEY not in st.session_state:
        _mark_portfolio_clean()


def _current_portfolio_name() -> str:
    return _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_KEY))


def _is_authenticated() -> bool:
    return bool(st.session_state.get(AUTHENTICATED_KEY, False))


def _render_login_form(config: AppSecurityConfig) -> None:
    st.title("포트폴리오 대시보드")
    st.subheader("비밀번호가 필요합니다")
    st.caption("공개 앱의 포트폴리오 입력, 가격 API quota, Supabase 저장소를 보호하기 위한 개인용 보호입니다.")
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
    with st.sidebar:
        st.subheader("인증 상태")
        if not config.has_password:
            st.warning(UNPROTECTED_WARNING)
            return
        if _is_authenticated():
            st.caption("상태: 인증됨")
            if st.button("로그아웃"):
                st.session_state[AUTHENTICATED_KEY] = False
                st.session_state.price_update_statuses = []
                st.rerun()
        else:
            st.caption("직접 입력 기능은 비밀번호가 필요합니다.")


def _build_stores(storage_config):
    if not should_enable_storage(storage_config):
        return None, None
    try:
        return build_supabase_store(storage_config), build_supabase_history_store(storage_config)
    except (PortfolioStoreError, RuntimeError) as exc:
        st.sidebar.warning(f"Supabase 저장소를 초기화할 수 없습니다: {exc}")
        return None, None


def _current_metrics():
    return build_portfolio_metrics(
        st.session_state.holdings_rows,
        cash_krw=st.session_state.cash_krw,
        cash_usd=st.session_state.cash_usd,
        usd_krw=st.session_state.usd_krw,
    )


def _save_current_portfolio(owner_id, store, history_store, metrics) -> None:
    if owner_id is None or store is None:
        st.warning("Supabase 저장소가 설정되지 않아 저장할 수 없습니다.")
        return
    portfolio_name = _current_portfolio_name()
    try:
        payload = serialize_portfolio_payload(
            st.session_state.holdings_rows,
            usd_krw=st.session_state.usd_krw,
            cash_krw=st.session_state.cash_krw,
            cash_usd=st.session_state.cash_usd,
        )
        store.save_portfolio(owner_id, portfolio_name, payload)
        if history_store is not None:
            history_store.save_snapshot(
                build_history_record(
                    owner_id=owner_id,
                    portfolio_name=portfolio_name,
                    event_type="portfolio_save",
                    metrics=metrics,
                )
            )
        st.cache_data.clear()
        _mark_portfolio_clean()
        st.session_state[SAVE_STATUS_KEY] = f"{portfolio_name} 포트폴리오를 저장했습니다."
        st.rerun()
    except (PortfolioStoreError, ValueError) as exc:
        st.error(f"포트폴리오를 저장할 수 없습니다: {exc}")


def _refresh_prices(config: AppSecurityConfig, owner_id, history_store) -> None:
    if should_disable_price_update(config):
        st.warning(f"{UNPROTECTED_WARNING} APP_PASSWORD가 없어 가격 새로고침을 비활성화했습니다.")
        return
    alpha_provider = build_alpha_vantage_provider(config.alpha_vantage_api_key)
    korea_provider = build_korea_quote_provider()
    progress = st.progress(0, text="최근 제공 가격 조회 준비 중")

    def update_progress(completed: int, total: int, symbol: str) -> None:
        percent = int((completed / max(total, 1)) * 100)
        progress.progress(percent, text=f"최근 제공 가격 조회 중: {symbol} ({completed}/{total})")

    updated_rows, statuses = refresh_holding_quotes(
        st.session_state.holdings_rows,
        alpha_provider,
        korea_provider=korea_provider,
        on_progress=update_progress,
    )
    progress.empty()
    st.session_state.holdings_rows = updated_rows
    st.session_state.price_update_statuses = statuses
    fetched_times = [status.fetched_at for status in statuses if status.fetched_at]
    if fetched_times:
        st.session_state.last_price_refresh_at = max(fetched_times)
    if owner_id is not None and history_store is not None and any(status.status in {"updated", "cached"} for status in statuses):
        metrics = _current_metrics()
        history_store.save_snapshot(
            build_history_record(
                owner_id=owner_id,
                portfolio_name=_current_portfolio_name(),
                event_type="price_refresh",
                metrics=metrics,
            )
        )
        st.cache_data.clear()
    st.rerun()


def _refresh_fx(config: AppSecurityConfig) -> None:
    provider = build_alpha_vantage_provider(config.alpha_vantage_api_key)
    try:
        new_rate, status = refresh_usd_krw(provider, float(st.session_state.usd_krw))
    except ValueError as exc:
        st.error(f"환율을 갱신할 수 없습니다: {exc}")
        return
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
        "usd_krw": new_rate,
        "fx_status_message": status.message,
        "fx_fetched_at": status.fetched_at,
    }
    st.rerun()


def _render_sidebar(config: AppSecurityConfig) -> None:
    with st.sidebar:
        st.subheader("현재 포트폴리오")
        portfolio_name_input = st.text_input("포트폴리오 이름", key=PORTFOLIO_NAME_INPUT_KEY)
        st.session_state[PORTFOLIO_NAME_KEY] = _clean_portfolio_name(portfolio_name_input)
        if _portfolio_is_dirty():
            st.caption("저장하지 않은 변경 있음")
        else:
            st.caption("저장됨")
        with st.expander("현금 및 환율", expanded=True):
            st.number_input("KRW 현금", min_value=0.0, step=100000.0, key="cash_krw")
            st.number_input("USD 현금", min_value=0.0, step=100.0, key="cash_usd")
            st.number_input("USD/KRW", min_value=0.01, step=1.0, key="usd_krw")
            if st.button("USD/KRW 환율 갱신"):
                _refresh_fx(config)
            st.caption(st.session_state.fx_status_message)
            if st.session_state.fx_fetched_at:
                st.caption(f"환율 조회: {format_kst(st.session_state.fx_fetched_at, compact=True)}")
        with st.expander("데이터 정보", expanded=False):
            st.caption("미국 주식은 Alpha Vantage, 국내 주식은 FinanceDataReader 기반 최근 제공 가격을 사용합니다. 무료 데이터라 실시간을 보장하지 않습니다.")


def _render_header(config: AppSecurityConfig, owner_id, store, history_store, metrics) -> None:
    dirty = _portfolio_is_dirty()
    summary = aggregate_price_statuses(st.session_state.get("price_update_statuses", []))
    last_refresh = metrics.last_price_refresh_at or st.session_state.last_price_refresh_at
    left, middle, right = st.columns([2.3, 2.1, 1.4], vertical_alignment="center")
    with left:
        st.title("포트폴리오 대시보드")
        st.caption(f"현재 포트폴리오 · {_current_portfolio_name()}")
    with middle:
        st.caption("마지막 가격 갱신")
        if last_refresh:
            st.write(f"**{format_kst(last_refresh)}** · {format_relative_time(last_refresh)}")
        else:
            st.write("**미조회**")
        st.caption(f"정상 {metrics.priced_count} · 캐시 {summary.cached} · 이전 가격 {metrics.stale_quote_count} · 실패 {metrics.failed_quote_count} · 미조회 {metrics.missing_quote_count}")
        st.caption("저장하지 않은 변경 있음" if dirty else "저장됨")
    with right:
        if st.button("가격 새로고침", type="primary", width="stretch"):
            _refresh_prices(config, owner_id, history_store)
        save_disabled = not dirty or owner_id is None or store is None
        if st.button("현재 포트폴리오 저장", disabled=save_disabled, width="stretch"):
            _save_current_portfolio(owner_id, store, history_store, metrics)


def _render_status_messages() -> None:
    save_message = st.session_state.pop(SAVE_STATUS_KEY, None)
    if save_message:
        st.success(save_message)
    render_price_update_log(
        st.session_state.get("price_update_statuses", []),
        st.session_state.get("holdings_rows", []),
    )


st.set_page_config(page_title="포트폴리오 대시보드", layout="wide")
inject_styles()
_initialize_session_state()
security_config = _read_security_config()
if should_lock_entire_app(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)

storage_config = _read_storage_config()
portfolio_store, history_store = _build_stores(storage_config)
owner_id = storage_config.owner_id if should_enable_storage(storage_config) else None
_render_sidebar(security_config)
_render_security_status(security_config)
if should_lock_manual_mode(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)
metrics = _current_metrics()
_render_header(security_config, owner_id, portfolio_store, history_store, metrics)
_render_status_messages()

overview_tab, holdings_tab, history_tab, manage_tab = st.tabs(["개요", "보유자산", "자산추이", "관리"])
with overview_tab:
    render_overview(metrics)
with holdings_tab:
    render_holdings_editor()
    metrics = _current_metrics()
    render_holdings_table(metrics)
with history_tab:
    render_history_tab(owner_id=owner_id, portfolio_name=_current_portfolio_name(), history_store=history_store)
with manage_tab:
    render_csv_tools()
    metrics = _current_metrics()
    render_storage_tools(
        owner_id=owner_id,
        store=portfolio_store,
        history_store=history_store,
        metrics=metrics,
        on_capture=lambda _: _mark_portfolio_clean(),
    )
    render_manual_capture(owner_id=owner_id, history_store=history_store, metrics=metrics)
