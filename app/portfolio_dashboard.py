from __future__ import annotations

import os
from pathlib import Path
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


_ensure_project_root_on_path()

import streamlit as st

SUPPORTED_PYTHON_RUNTIMES = {(3, 11), (3, 12)}


def _is_supported_python_runtime(version_info=sys.version_info) -> bool:
    return (int(version_info.major), int(version_info.minor)) in SUPPORTED_PYTHON_RUNTIMES


def _stop_if_unsupported_python_runtime() -> None:
    if _is_supported_python_runtime():
        return
    st.set_page_config(page_title="포트폴리오 대시보드", layout="wide")
    st.error("이 앱은 Python 3.11 또는 3.12 환경에서 실행해야 합니다.")
    st.info("Streamlit Community Cloud의 App settings > Advanced settings에서 Python version을 3.12로 변경한 뒤 Reboot 또는 Redeploy를 실행하세요.")
    st.stop()


_stop_if_unsupported_python_runtime()

from app.ui.components import render_price_update_log
from app.ui.formatters import format_kst, format_relative_time
from app.ui.holdings import render_holdings_table
from app.ui.history import render_history_tab
from app.ui.investment_summary_card import render_investment_summary_card
from app.ui.manage import (
    list_portfolios_cached,
    queue_portfolio_record_load,
    render_csv_tools,
    render_manual_capture,
    render_storage_tools,
)
from app.ui.overview import render_overview
from app.ui.status import aggregate_price_statuses, dirty_signature, select_price_refresh_rows
from app.ui.styles import inject_public_cloud_chrome_guard, inject_styles
from app.ui.theme import APP_THEME_KEY, DEFAULT_THEME_MODE, normalize_theme_mode
from app.ui.transactions import render_transaction_cashflow, render_transaction_editor
from portfolio.auth import (
    AccountConfig,
    AppSecurityConfig,
    available_account_ids,
    config_from_secrets,
    should_lock_entire_app,
    should_lock_manual_mode,
    verify_account,
)
from portfolio.history import build_history_record, build_supabase_history_store
from portfolio.holdings import build_portfolio_metrics
from portfolio.historical_holdings import HistoricalScheduleStoreError, build_supabase_historical_schedule_store
from portfolio.pricing import (
    TTLFxCache,
    TTLQuoteCache,
    build_korea_quote_provider,
    build_public_fx_provider,
    build_yfinance_fx_provider,
    build_yfinance_intraday_provider,
    build_yfinance_provider,
    refresh_holding_quotes,
    refresh_usd_krw,
)
from portfolio.storage import (
    PortfolioStoreError,
    build_supabase_store,
    has_supabase_credentials,
    serialize_portfolio_payload,
    should_enable_storage,
    supabase_config_from_secrets,
)
from portfolio.supabase_auth import (
    SupabaseAuthAccount,
    SupabaseAuthError,
    SupabaseAuthStore,
    SupabaseAuthValidationError,
)

AUTHENTICATED_KEY = "is_authenticated"
ACCOUNT_ID_KEY = "authenticated_account_id"
OWNER_ID_KEY = "authenticated_owner_id"
DEFAULT_PORTFOLIO_KEY = "authenticated_default_portfolio"
AUTH_ACCESS_TOKEN_KEY = "authenticated_access_token"
AUTH_REFRESH_TOKEN_KEY = "authenticated_refresh_token"
PORTFOLIO_NAME_KEY = "portfolio_name"
PORTFOLIO_NAME_INPUT_KEY = "portfolio_name_input"
PENDING_PORTFOLIO_NAME_KEY = "pending_portfolio_name"
PENDING_PORTFOLIO_STATE_KEY = "pending_portfolio_state"
SAVED_SIGNATURE_KEY = "saved_portfolio_signature"
LAST_SAVED_STATE_KEY = "last_saved_portfolio_state"
MARK_CLEAN_KEY = "mark_portfolio_clean"
SAVE_STATUS_KEY = "portfolio_save_status_message"
PRICE_REFRESH_MODE_KEY = "price_refresh_mode"
AUTO_LOAD_ATTEMPTED_KEY = "account_auto_load_attempted"
AUTO_PRICE_REFRESHED_KEY = "account_auto_price_refreshed"
ACCOUNT_STATUS_KEY = "account_status_message"
PUBLIC_SAVE_STATUS_KEY = "public_auto_save_status"
PUBLIC_SECTION_KEY = "public_dashboard_section"
PUBLIC_HOLDINGS_VIEW_KEY = "public_holdings_view"
CASH_FX_INPUT_SYNC_KEY = "cash_fx_inline_input_sync"
INLINE_CASH_KRW_KEY = "cash_fx_inline_cash_krw"
INLINE_CASH_USD_KEY = "cash_fx_inline_cash_usd"
INLINE_USD_KRW_KEY = "cash_fx_inline_usd_krw"
PUBLIC_AUTH_ENV_KEY = "PORTFOLIO_PUBLIC_AUTH"
PUBLIC_AUTH_SECRET_KEY = "PUBLIC_USER_AUTH"
UNPROTECTED_WARNING = "공개 앱에서 저장소와 직접 입력 보호를 위해 APP_PASSWORD 설정을 권장합니다."
PUBLIC_PORTFOLIO_NAME = "main"
APP_THEME_CHOICE_KEY = "app_theme_choice"
THEME_LABEL_BY_MODE = {"dark": "다크", "light": "라이트"}
THEME_MODE_BY_LABEL = {label: mode for mode, label in THEME_LABEL_BY_MODE.items()}
PUBLIC_SECTION_LABELS = {
    "summary": "총괄현황",
    "details": "세부내역",
    "input": "사용자입력",
    "history": "자산추이",
}
PUBLIC_SECTION_LEGACY_MAP = {
    "투자 총괄 카드": "summary",
    "총괄현황": "summary",
    "개요": "details",
    "세부내역": "details",
    "보유자산": "input",
    "사용자 입력": "input",
    "사용자입력": "input",
    "자산추이": "history",
}
PUBLIC_HOLDINGS_VIEW_LABELS = {
    "holdings": "보유 현황",
    "cash_fx": "현금·환율",
    "transactions": "거래 입력",
}
PUBLIC_HOLDINGS_VIEW_LEGACY_MAP = {
    "현황": "holdings",
    "보유 현황": "holdings",
    "현금/환율": "cash_fx",
    "현금·환율": "cash_fx",
    "거래 입력": "transactions",
}


def _normalize_radio_state(key: str, labels: dict[str, str], legacy_map: dict[str, str], default: str) -> None:
    current = st.session_state.get(key)
    if current in labels:
        return
    st.session_state[key] = legacy_map.get(str(current), default)


def _initialize_theme_state() -> None:
    selected_label = st.session_state.get(APP_THEME_CHOICE_KEY)
    if selected_label in THEME_MODE_BY_LABEL:
        mode = THEME_MODE_BY_LABEL[str(selected_label)]
    else:
        mode = normalize_theme_mode(st.session_state.get(APP_THEME_KEY, DEFAULT_THEME_MODE))
    st.session_state[APP_THEME_KEY] = mode
    st.session_state[APP_THEME_CHOICE_KEY] = THEME_LABEL_BY_MODE[mode]


def _current_theme_mode() -> str:
    return normalize_theme_mode(st.session_state.get(APP_THEME_KEY, DEFAULT_THEME_MODE))


def _render_theme_selector() -> None:
    current_mode = _current_theme_mode()
    with st.container(key="app_theme_topbar"):
        st.radio(
            "테마",
            list(THEME_MODE_BY_LABEL.keys()),
            index=list(THEME_MODE_BY_LABEL).index(THEME_LABEL_BY_MODE[current_mode]),
            key=APP_THEME_CHOICE_KEY,
            horizontal=True,
            label_visibility="collapsed",
        )


def _clean_portfolio_name(value: object) -> str:
    return str(value or "main").strip() or "main"


def _current_portfolio_signature() -> str:
    return dirty_signature(_current_portfolio_state())


def _current_portfolio_state() -> dict[str, object]:
    return {
        "portfolio_name": _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_KEY)),
        "portfolio_transactions": st.session_state.get("portfolio_transactions", []),
        "holdings_rows": st.session_state.get("holdings_rows", []),
        "cash_krw": st.session_state.get("cash_krw", 0.0),
        "cash_usd": st.session_state.get("cash_usd", 0.0),
        "usd_krw": st.session_state.get("usd_krw", 1380.0),
    }


def _mark_portfolio_clean() -> None:
    st.session_state[SAVED_SIGNATURE_KEY] = _current_portfolio_signature()
    st.session_state[LAST_SAVED_STATE_KEY] = _current_portfolio_state()


def _portfolio_is_dirty() -> bool:
    return st.session_state.get(SAVED_SIGNATURE_KEY) != _current_portfolio_signature()


def _restore_last_saved_state() -> None:
    state = st.session_state.get(LAST_SAVED_STATE_KEY)
    if not isinstance(state, dict):
        return
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
        "portfolio_name": _clean_portfolio_name(state.get("portfolio_name")),
        "portfolio_transactions": list(state.get("portfolio_transactions") or []),
        "holdings_rows": list(state.get("holdings_rows") or []),
        "cash_krw": float(state.get("cash_krw") or 0.0),
        "cash_usd": float(state.get("cash_usd") or 0.0),
        "usd_krw": float(state.get("usd_krw") or 1380.0),
        "mark_clean": True,
    }


def _reset_current_portfolio_state(portfolio_name: str = "main") -> None:
    clean_name = _clean_portfolio_name(portfolio_name)
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
        "portfolio_name": clean_name,
        "portfolio_transactions": [],
        "holdings_rows": [],
        "cash_krw": 0.0,
        "cash_usd": 0.0,
        "usd_krw": 1380.0,
        "fx_status_message": "수동 USD/KRW 환율",
        "fx_fetched_at": None,
        "price_update_statuses": [],
        "last_price_refresh_at": None,
        "mark_clean": True,
    }


def _authenticate_account(account: AccountConfig) -> None:
    st.session_state[AUTHENTICATED_KEY] = True
    st.session_state[ACCOUNT_ID_KEY] = account.account_id
    st.session_state[OWNER_ID_KEY] = account.owner_id
    st.session_state[DEFAULT_PORTFOLIO_KEY] = account.default_portfolio
    st.session_state.pop(AUTO_LOAD_ATTEMPTED_KEY, None)
    st.session_state.pop(AUTO_PRICE_REFRESHED_KEY, None)
    _reset_current_portfolio_state(account.default_portfolio)


def _authenticate_public_account(account: SupabaseAuthAccount) -> None:
    _authenticate_account(
        AccountConfig(
            account_id=account.account_id,
            password="",
            owner_id=account.owner_id,
            default_portfolio=PUBLIC_PORTFOLIO_NAME,
        )
    )
    st.session_state[AUTH_ACCESS_TOKEN_KEY] = account.access_token
    st.session_state[AUTH_REFRESH_TOKEN_KEY] = account.refresh_token


def _logout() -> None:
    st.session_state[AUTHENTICATED_KEY] = False
    for key in (
        ACCOUNT_ID_KEY,
        OWNER_ID_KEY,
        DEFAULT_PORTFOLIO_KEY,
        AUTH_ACCESS_TOKEN_KEY,
        AUTH_REFRESH_TOKEN_KEY,
        AUTO_LOAD_ATTEMPTED_KEY,
        AUTO_PRICE_REFRESHED_KEY,
        PUBLIC_SAVE_STATUS_KEY,
    ):
        st.session_state.pop(key, None)
    _reset_current_portfolio_state()


def _read_security_config() -> AppSecurityConfig:
    try:
        secrets = {
            "APP_PASSWORD": st.secrets.get("APP_PASSWORD", ""),
            "APP_AUTH_SCOPE": st.secrets.get("APP_AUTH_SCOPE", ""),
            "PORTFOLIO_OWNER_ID": st.secrets.get("PORTFOLIO_OWNER_ID", ""),
            "DEFAULT_PORTFOLIO_NAME": st.secrets.get("DEFAULT_PORTFOLIO_NAME", ""),
            "ACCOUNTS": st.secrets.get("ACCOUNTS", st.secrets.get("accounts", {})),
            "APP_ACCOUNTS": st.secrets.get("APP_ACCOUNTS", ""),
        }
    except Exception:
        secrets = {}
    return config_from_secrets(secrets)


def _read_storage_config(*, public_auth_enabled: bool = False):
    try:
        secrets = {
            "SUPABASE_URL": st.secrets.get("SUPABASE_URL", ""),
            "SUPABASE_SERVICE_ROLE_KEY": "" if public_auth_enabled else st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            "SUPABASE_PUBLISHABLE_KEY": st.secrets.get("SUPABASE_PUBLISHABLE_KEY", ""),
            "SUPABASE_ANON_KEY": st.secrets.get("SUPABASE_ANON_KEY", ""),
            "PORTFOLIO_OWNER_ID": st.secrets.get("PORTFOLIO_OWNER_ID", ""),
        }
    except Exception:
        secrets = {}
    config = supabase_config_from_secrets(secrets)
    if public_auth_enabled:
        return config.with_auth_session(
            owner_id=st.session_state.get(OWNER_ID_KEY),
            access_token=st.session_state.get(AUTH_ACCESS_TOKEN_KEY),
            refresh_token=st.session_state.get(AUTH_REFRESH_TOKEN_KEY),
        )
    return config


def _truthy(value: object | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_public_auth_settings() -> bool:
    enabled = _truthy(os.environ.get(PUBLIC_AUTH_ENV_KEY))
    try:
        enabled = enabled or _truthy(st.secrets.get(PUBLIC_AUTH_SECRET_KEY, ""))
    except Exception:
        pass
    return enabled


@st.cache_resource(show_spinner=False)
def _build_public_auth_store(storage_config) -> SupabaseAuthStore | None:
    if not storage_config.supabase_url or not storage_config.publishable_key:
        return None
    return SupabaseAuthStore(storage_config)


def _apply_pending_portfolio_state() -> None:
    pending_state = st.session_state.pop(PENDING_PORTFOLIO_STATE_KEY, None)
    if not isinstance(pending_state, dict):
        return
    loaded_portfolio_state = "portfolio_name" in pending_state or "holdings_rows" in pending_state or "portfolio_transactions" in pending_state
    mark_clean = bool(pending_state.pop("mark_clean", loaded_portfolio_state))
    if "portfolio_name" in pending_state:
        clean_name = _clean_portfolio_name(pending_state["portfolio_name"])
        st.session_state[PORTFOLIO_NAME_KEY] = clean_name
        st.session_state[PORTFOLIO_NAME_INPUT_KEY] = clean_name
    for key in (
        "holdings_rows",
        "portfolio_transactions",
        "cash_krw",
        "cash_usd",
        "usd_krw",
        "fx_status_message",
        "fx_fetched_at",
        "price_update_statuses",
        "last_price_refresh_at",
    ):
        if key in pending_state:
            st.session_state[key] = pending_state[key]
    if loaded_portfolio_state and mark_clean:
        st.session_state[MARK_CLEAN_KEY] = True


def _initialize_session_state(*, public_auth_enabled: bool = False) -> None:
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
    st.session_state.setdefault("portfolio_transactions", [])
    st.session_state.setdefault("holdings_rows", [])
    st.session_state.setdefault("cash_krw", 0.0)
    st.session_state.setdefault("cash_usd", 0.0)
    st.session_state.setdefault("usd_krw", 1380.0)
    st.session_state.setdefault("fx_status_message", "수동 USD/KRW 환율")
    st.session_state.setdefault("fx_fetched_at", None)
    st.session_state.setdefault("price_update_statuses", [])
    st.session_state.setdefault("last_price_refresh_at", None)
    st.session_state.setdefault(PRICE_REFRESH_MODE_KEY, "미조회/오래된 가격만")
    if public_auth_enabled:
        st.session_state[PORTFOLIO_NAME_KEY] = PUBLIC_PORTFOLIO_NAME
        st.session_state[PORTFOLIO_NAME_INPUT_KEY] = PUBLIC_PORTFOLIO_NAME
        st.session_state[DEFAULT_PORTFOLIO_KEY] = PUBLIC_PORTFOLIO_NAME
    if st.session_state.pop(MARK_CLEAN_KEY, False) or SAVED_SIGNATURE_KEY not in st.session_state:
        _mark_portfolio_clean()


def _current_portfolio_name() -> str:
    return _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_KEY))


def _is_authenticated() -> bool:
    return bool(st.session_state.get(AUTHENTICATED_KEY, False))


def _render_login_form(config: AppSecurityConfig) -> None:
    _render_theme_selector()
    st.title("포트폴리오 대시보드")
    st.subheader("로그인이 필요합니다")
    st.caption("계정별 저장 포트폴리오와 Supabase 저장소를 보호하기 위한 개인용 보호입니다.")
    account_ids = available_account_ids(config)
    with st.form("password_form"):
        if account_ids:
            selected_account_id = st.selectbox("계정", account_ids)
        else:
            selected_account_id = config.legacy_owner_id or "main"
        candidate_password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")
    if submitted:
        account = verify_account(selected_account_id, candidate_password, config)
        if account is not None:
            _authenticate_account(account)
            st.rerun()
        st.error("계정 또는 비밀번호가 올바르지 않습니다.")
    st.stop()


def _render_public_auth_gate(storage_config) -> None:
    _render_theme_selector()
    st.title("포트폴리오 대시보드")
    try:
        auth_store = _build_public_auth_store(storage_config)
    except SupabaseAuthError as exc:
        st.error(f"로그인 저장소를 초기화할 수 없습니다: {exc}")
        st.stop()
    if auth_store is None:
        st.error("로그인 설정이 필요합니다. Streamlit Secrets에 SUPABASE_URL과 SUPABASE_PUBLISHABLE_KEY 또는 SUPABASE_ANON_KEY를 입력하세요.")
        st.stop()

    login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
    with login_tab:
        with st.form("public_login_form"):
            email = st.text_input("이메일", key="public_login_email")
            password = st.text_input("비밀번호", type="password", key="public_login_password")
            submitted = st.form_submit_button("로그인", type="primary")
        if submitted:
            try:
                account = auth_store.sign_in(email, password)
            except (SupabaseAuthValidationError, SupabaseAuthError) as exc:
                st.error(str(exc))
            else:
                _authenticate_public_account(account)
                st.rerun()

    with signup_tab:
        with st.form("public_signup_form"):
            email = st.text_input("이메일", key="public_signup_email")
            password = st.text_input("비밀번호", type="password", key="public_signup_password")
            password_confirm = st.text_input("비밀번호 확인", type="password", key="public_signup_password_confirm")
            submitted = st.form_submit_button("회원가입", type="primary")
        if submitted:
            if password != password_confirm:
                st.error("비밀번호 확인이 일치하지 않습니다.")
            else:
                try:
                    result = auth_store.sign_up(email, password)
                except (SupabaseAuthValidationError, SupabaseAuthError) as exc:
                    st.error(str(exc))
                else:
                    if result.account is not None:
                        _authenticate_public_account(result.account)
                        st.rerun()
                    if result.confirmation_required:
                        st.success("회원가입 요청을 보냈습니다. Supabase Auth 설정에서 이메일 확인이 켜져 있으면 메일 확인 후 로그인하세요.")
    st.stop()


def _render_security_status(config: AppSecurityConfig, *, public_auth_enabled: bool = False) -> None:
    with st.sidebar:
        st.subheader("인증 상태")
        if public_auth_enabled:
            account_id = st.session_state.get(ACCOUNT_ID_KEY) or "account"
            st.caption(f"상태: 로그인됨 · {account_id}")
            if st.button("로그아웃", icon=":material/logout:"):
                _logout()
                st.rerun()
            return
        if not config.has_password:
            st.warning(UNPROTECTED_WARNING)
            return
        if _is_authenticated():
            account_id = st.session_state.get(ACCOUNT_ID_KEY) or st.session_state.get(OWNER_ID_KEY) or "main"
            st.caption(f"상태: 인증됨 · {account_id}")
            if st.button("로그아웃", icon=":material/logout:"):
                _logout()
                st.rerun()
        else:
            st.caption("직접 입력 기능은 비밀번호가 필요합니다.")


@st.cache_resource(show_spinner=False)
def _build_stores(storage_config):
    if not has_supabase_credentials(storage_config):
        return None, None, None
    try:
        return (
            build_supabase_store(storage_config),
            build_supabase_history_store(storage_config),
            build_supabase_historical_schedule_store(storage_config),
        )
    except (PortfolioStoreError, HistoricalScheduleStoreError, RuntimeError) as exc:
        st.sidebar.warning(f"Supabase 저장소를 초기화할 수 없습니다: {exc}")
        return None, None, None


def _resolve_owner_id(storage_config) -> str | None:
    authenticated_owner_id = st.session_state.get(OWNER_ID_KEY)
    if authenticated_owner_id:
        return str(authenticated_owner_id)
    if should_enable_storage(storage_config):
        return storage_config.owner_id
    return None


def _current_metrics():
    return build_portfolio_metrics(
        st.session_state.holdings_rows,
        cash_krw=st.session_state.cash_krw,
        cash_usd=st.session_state.cash_usd,
        usd_krw=st.session_state.usd_krw,
    )


def _current_portfolio_payload():
    return serialize_portfolio_payload(
        st.session_state.holdings_rows,
        usd_krw=st.session_state.usd_krw,
        cash_krw=st.session_state.cash_krw,
        cash_usd=st.session_state.cash_usd,
        transactions=st.session_state.get("portfolio_transactions", []),
    )


def _persist_current_portfolio(owner_id, store) -> None:
    portfolio_name = _current_portfolio_name()
    store.save_portfolio(owner_id, portfolio_name, _current_portfolio_payload())
    st.cache_data.clear()
    _mark_portfolio_clean()


def _save_current_portfolio(owner_id, store, history_store, metrics) -> None:
    if owner_id is None or store is None:
        st.warning("Supabase 저장소가 설정되지 않아 저장할 수 없습니다.")
        return
    portfolio_name = _current_portfolio_name()
    try:
        _persist_current_portfolio(owner_id, store)
        if history_store is not None:
            history_store.save_snapshot(
                build_history_record(
                    owner_id=owner_id,
                    portfolio_name=portfolio_name,
                    event_type="portfolio_save",
                    metrics=metrics,
                )
            )
        st.session_state[SAVE_STATUS_KEY] = f"{portfolio_name} 포트폴리오를 저장했습니다."
        st.rerun()
    except (PortfolioStoreError, ValueError) as exc:
        st.error(f"포트폴리오를 저장할 수 없습니다: {exc}")


def _auto_save_public_portfolio(owner_id, store, history_store, metrics) -> None:
    if not _is_authenticated():
        return
    st.session_state[PORTFOLIO_NAME_KEY] = PUBLIC_PORTFOLIO_NAME
    st.session_state[PORTFOLIO_NAME_INPUT_KEY] = PUBLIC_PORTFOLIO_NAME
    if owner_id is None or store is None:
        st.session_state[PUBLIC_SAVE_STATUS_KEY] = "저장 실패: Supabase 저장소 설정이 필요합니다."
        return
    if not _portfolio_is_dirty():
        st.session_state[PUBLIC_SAVE_STATUS_KEY] = "저장됨"
        return
    try:
        st.session_state[PUBLIC_SAVE_STATUS_KEY] = "저장 중"
        _persist_current_portfolio(owner_id, store)
        if history_store is not None:
            history_store.save_snapshot(
                build_history_record(
                    owner_id=owner_id,
                    portfolio_name=PUBLIC_PORTFOLIO_NAME,
                    event_type="portfolio_save",
                    metrics=metrics,
                )
            )
        st.session_state[PUBLIC_SAVE_STATUS_KEY] = "저장됨"
    except (PortfolioStoreError, ValueError) as exc:
        st.session_state[PUBLIC_SAVE_STATUS_KEY] = f"저장 실패: {exc}"


def _current_save_status_text(*, public_auth_enabled: bool, dirty: bool) -> str:
    if public_auth_enabled:
        return str(st.session_state.get(PUBLIC_SAVE_STATUS_KEY) or ("저장 중" if dirty else "저장됨"))
    return "저장하지 않은 변경 있음" if dirty else "저장됨"


def _refresh_price_rows(
    owner_id,
    history_store,
    *,
    mode: str,
    include_intraday: bool = False,
    on_progress=None,
) -> bool:
    us_provider = build_yfinance_provider()
    korea_provider = build_korea_quote_provider()
    intraday_provider = build_yfinance_intraday_provider() if include_intraday else None
    all_rows = list(st.session_state.holdings_rows)
    target_rows = list(select_price_refresh_rows(all_rows, mode))
    if not target_rows:
        return False

    updated_rows, statuses = refresh_holding_quotes(
        target_rows,
        us_provider,
        korea_provider=korea_provider,
        intraday_provider=intraday_provider,
        cache=TTLQuoteCache() if mode == "전체 강제 재조회" else None,
        on_progress=on_progress,
    )
    updated_by_key = {(str(row.get("market")), str(row.get("ticker"))): row for row in updated_rows}
    st.session_state.holdings_rows = [updated_by_key.get((str(row.get("market")), str(row.get("ticker"))), row) for row in all_rows]
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
    return True


def _refresh_prices(
    _config: AppSecurityConfig,
    owner_id,
    history_store,
    *,
    mode: str = "전체 강제 재조회",
    refresh_fx: bool = True,
    public_auth_enabled: bool = False,
) -> None:
    progress = st.progress(0, text="최근 제공 가격 조회 준비 중")

    def update_progress(completed: int, total: int, symbol: str) -> None:
        percent = int((completed / max(total, 1)) * 100)
        progress.progress(percent, text=f"최근 제공 가격 조회 중: {symbol} ({completed}/{total})")

    refreshed = _refresh_price_rows(owner_id, history_store, mode=mode, include_intraday=True, on_progress=update_progress)
    progress.empty()
    refreshed_fx = False
    if refresh_fx:
        fx_result = _fetch_fx_rate(public_auth_enabled=public_auth_enabled, force_refresh=True)
        if fx_result is not None:
            refreshed_fx = _apply_fx_rate(*fx_result)
    if not refreshed and not refreshed_fx:
        st.info("새로 조회할 대상 종목이 없습니다.")
        return
    st.rerun()


def _fetch_fx_rate(*, public_auth_enabled: bool = False, force_refresh: bool = False):
    provider = build_public_fx_provider() if public_auth_enabled else build_yfinance_fx_provider()
    try:
        cache = TTLFxCache() if force_refresh else None
        new_rate, status = refresh_usd_krw(provider, float(st.session_state.usd_krw), cache=cache)
    except ValueError as exc:
        st.error(f"환율을 갱신할 수 없습니다: {exc}")
        return None
    except Exception as exc:
        st.session_state.fx_status_message = f"USD/KRW 환율 갱신 실패: {exc}. 기존 수동 환율을 유지했습니다."
        st.error(st.session_state.fx_status_message)
        return None
    return new_rate, status


def _apply_fx_rate(new_rate, status) -> bool:
    st.session_state.usd_krw = new_rate
    st.session_state.fx_status_message = status.message
    st.session_state.fx_fetched_at = status.fetched_at
    return status.status in {"updated", "cached"}


def _refresh_fx(_config: AppSecurityConfig, *, public_auth_enabled: bool = False) -> None:
    with st.spinner("USD/KRW 환율 조회 중..."):
        result = _fetch_fx_rate(public_auth_enabled=public_auth_enabled, force_refresh=True)
    if result is None:
        return
    new_rate, status = result
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
        "usd_krw": new_rate,
        "fx_status_message": status.message,
        "fx_fetched_at": status.fetched_at,
    }
    st.rerun()


def _cash_fx_input_signature() -> str:
    return "|".join(
        [
            f"{float(st.session_state.get('cash_krw') or 0.0):.4f}",
            f"{float(st.session_state.get('cash_usd') or 0.0):.4f}",
            f"{float(st.session_state.get('usd_krw') or 0.0):.4f}",
        ]
    )


def _sync_inline_cash_fx_inputs() -> None:
    signature = _cash_fx_input_signature()
    if st.session_state.get(CASH_FX_INPUT_SYNC_KEY) == signature:
        return
    st.session_state[INLINE_CASH_KRW_KEY] = float(st.session_state.get("cash_krw") or 0.0)
    st.session_state[INLINE_CASH_USD_KEY] = float(st.session_state.get("cash_usd") or 0.0)
    st.session_state[INLINE_USD_KRW_KEY] = float(st.session_state.get("usd_krw") or 1380.0)
    st.session_state[CASH_FX_INPUT_SYNC_KEY] = signature


def _queue_inline_cash_fx_update() -> None:
    current_rate = float(st.session_state.get("usd_krw") or 1380.0)
    new_rate = float(st.session_state.get(INLINE_USD_KRW_KEY) or current_rate)
    pending_state = {
        "cash_krw": float(st.session_state.get(INLINE_CASH_KRW_KEY) or 0.0),
        "cash_usd": float(st.session_state.get(INLINE_CASH_USD_KEY) or 0.0),
        "usd_krw": new_rate,
    }
    if abs(new_rate - current_rate) > 1e-9:
        pending_state["fx_status_message"] = "수동 USD/KRW 환율"
        pending_state["fx_fetched_at"] = None
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = pending_state
    st.rerun()


def _render_cash_fx_tools(config: AppSecurityConfig, *, public_auth_enabled: bool = False) -> None:
    _sync_inline_cash_fx_inputs()
    with st.expander("현금 및 환율", expanded=True):
        with st.form("inline_cash_fx_form"):
            col1, col2, col3 = st.columns(3)
            col1.number_input("원화 현금", min_value=0.0, step=100000.0, key=INLINE_CASH_KRW_KEY)
            col2.number_input("달러 현금", min_value=0.0, step=100.0, key=INLINE_CASH_USD_KEY)
            col3.number_input("USD/KRW 환율", min_value=0.01, step=1.0, key=INLINE_USD_KRW_KEY)
            submitted = st.form_submit_button("현금/환율 적용", type="primary")
        if submitted:
            _queue_inline_cash_fx_update()
        if st.button("USD/KRW 환율 갱신", icon=":material/currency_exchange:", key="inline_fx_refresh"):
            _refresh_fx(config, public_auth_enabled=public_auth_enabled)
        st.caption(st.session_state.fx_status_message)
        if st.session_state.fx_fetched_at:
            st.caption(f"환율 조회: {format_kst(st.session_state.fx_fetched_at, compact=True)}")


def _load_portfolio_record_now(record) -> None:
    queue_portfolio_record_load(record)
    _apply_pending_portfolio_state()
    if st.session_state.pop(MARK_CLEAN_KEY, False):
        _mark_portfolio_clean()


def _auto_load_account_portfolio(owner_id, store) -> None:
    if owner_id is None or store is None:
        return
    portfolio_name = _current_portfolio_name()
    attempt_key = f"{owner_id}:{portfolio_name}"
    if st.session_state.get(AUTO_LOAD_ATTEMPTED_KEY) == attempt_key:
        return
    st.session_state[AUTO_LOAD_ATTEMPTED_KEY] = attempt_key
    try:
        record = store.get_portfolio(owner_id, portfolio_name)
    except PortfolioStoreError as exc:
        st.session_state[ACCOUNT_STATUS_KEY] = f"저장된 포트폴리오 자동 불러오기에 실패했습니다: {exc}"
        return
    if record is None:
        return
    try:
        _load_portfolio_record_now(record)
    except (PortfolioStoreError, ValueError) as exc:
        st.session_state[ACCOUNT_STATUS_KEY] = f"저장된 포트폴리오를 불러올 수 없습니다: {exc}"
        return
    st.session_state.pop(AUTO_PRICE_REFRESHED_KEY, None)
    st.session_state[ACCOUNT_STATUS_KEY] = f"{record.portfolio_name} 포트폴리오를 자동으로 불러왔습니다."


def _auto_refresh_loaded_prices(owner_id, store, history_store) -> None:
    holdings_rows = list(st.session_state.get("holdings_rows") or [])
    has_usd_cash = float(st.session_state.get("cash_usd") or 0.0) > 0
    if owner_id is None or (not holdings_rows and not has_usd_cash):
        return
    refresh_key = f"{owner_id}:{_current_portfolio_name()}"
    if st.session_state.get(AUTO_PRICE_REFRESHED_KEY) == refresh_key:
        return
    st.session_state[AUTO_PRICE_REFRESHED_KEY] = refresh_key
    fx_result = _fetch_fx_rate()
    refreshed_fx = _apply_fx_rate(*fx_result) if fx_result is not None else False
    refreshed = _refresh_price_rows(owner_id, history_store, mode="전체 강제 재조회", include_intraday=False) if holdings_rows else False
    if not refreshed and not refreshed_fx:
        return
    if store is not None:
        try:
            _persist_current_portfolio(owner_id, store)
        except (PortfolioStoreError, ValueError) as exc:
            st.session_state[ACCOUNT_STATUS_KEY] = f"가격 자동 갱신은 완료했지만 저장에 실패했습니다: {exc}"
            return
    existing_message = st.session_state.get(ACCOUNT_STATUS_KEY)
    suffix = "최근 가격과 USD/KRW 환율을 자동 갱신했습니다." if refreshed_fx else "최근 가격을 자동 갱신했습니다."
    st.session_state[ACCOUNT_STATUS_KEY] = f"{existing_message} {suffix}" if existing_message else suffix


def _render_saved_portfolio_selector(owner_id, store) -> None:
    if owner_id is None or store is None:
        st.text_input("포트폴리오 이름", key=PORTFOLIO_NAME_INPUT_KEY)
        st.session_state[PORTFOLIO_NAME_KEY] = _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_INPUT_KEY))
        return
    try:
        records = list_portfolios_cached(store, owner_id)
    except PortfolioStoreError as exc:
        st.caption(f"저장 목록을 불러올 수 없습니다: {exc}")
        records = []
    if not records:
        st.text_input("포트폴리오 이름", key=PORTFOLIO_NAME_INPUT_KEY)
        st.session_state[PORTFOLIO_NAME_KEY] = _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_INPUT_KEY))
        st.caption("새 포트폴리오 이름 변경은 관리 탭에서 저장할 때 확정됩니다.")
        return

    labels = {f"{record.portfolio_name} · {format_kst(record.updated_at or record.created_at, compact=True)}": record for record in records}
    current_name = _current_portfolio_name()
    selected_index = next((index for index, record in enumerate(labels.values()) if record.portfolio_name == current_name), 0)
    selected_label = st.selectbox("저장된 포트폴리오", list(labels.keys()), index=selected_index, key="sidebar_saved_portfolio")
    selected = labels[selected_label]
    if selected.portfolio_name != current_name:
        if _portfolio_is_dirty():
            st.warning("저장하지 않은 변경이 있습니다. 관리 탭에서 저장한 뒤 다른 포트폴리오를 불러오세요.")
        if st.button("선택 포트폴리오 불러오기", disabled=_portfolio_is_dirty(), width="stretch", icon=":material/folder_open:"):
            try:
                queue_portfolio_record_load(selected)
                st.rerun()
            except (PortfolioStoreError, ValueError) as exc:
                st.error(f"포트폴리오를 불러올 수 없습니다: {exc}")
    st.caption("새 포트폴리오 생성과 이름 변경은 관리 탭에서 처리합니다.")


def _render_sidebar(config: AppSecurityConfig, owner_id, store, *, public_auth_enabled: bool = False) -> None:
    with st.sidebar:
        if public_auth_enabled:
            st.subheader("데이터")
            with st.expander("데이터 정보", expanded=False):
                st.caption("미국 주식은 yfinance, USD/KRW 환율은 Yahoo chart와 open.er-api fallback, 국내 주식은 FinanceDataReader 기반 최근 제공 가격을 사용합니다. 무료 데이터라 실시간을 보장하지 않습니다.")
            with st.expander("가격 조회 옵션", expanded=False):
                st.caption("현재가 갱신은 보유 중인 모든 종목과 USD/KRW 환율을 캐시 없이 다시 조회합니다.")
                st.caption("실패 종목 재시도 버튼은 실패한 종목만 다시 조회합니다.")
            return
        st.subheader("현재 포트폴리오")
        _render_saved_portfolio_selector(owner_id, store)
        if _portfolio_is_dirty():
            st.caption("저장하지 않은 변경 있음")
            if st.button("변경사항 되돌리기", width="stretch", icon=":material/undo:"):
                _restore_last_saved_state()
                st.rerun()
        else:
            st.caption("저장됨")
        confirm_reset = st.checkbox("현재 입력 초기화 확인", key="confirm_reset_portfolio")
        if st.button("현재 입력 초기화", disabled=not confirm_reset, width="stretch", icon=":material/delete:"):
            _reset_current_portfolio_state(_current_portfolio_name())
            st.rerun()
        with st.expander("현금 및 환율", expanded=True):
            st.number_input("원화 현금", min_value=0.0, step=100000.0, key="cash_krw")
            st.number_input("달러 현금", min_value=0.0, step=100.0, key="cash_usd")
            st.number_input("환율", min_value=0.01, step=1.0, key="usd_krw", help="USD/KRW")
            if st.button("환율 갱신", icon=":material/currency_exchange:"):
                _refresh_fx(config, public_auth_enabled=public_auth_enabled)
            st.caption(st.session_state.fx_status_message)
            if st.session_state.fx_fetched_at:
                st.caption(f"환율 조회: {format_kst(st.session_state.fx_fetched_at, compact=True)}")
        with st.expander("데이터 정보", expanded=False):
            st.caption("미국 주식은 yfinance, USD/KRW 환율은 Yahoo chart와 open.er-api fallback, 국내 주식은 FinanceDataReader 기반 최근 제공 가격을 사용합니다. 무료 데이터라 실시간을 보장하지 않습니다.")
        with st.expander("가격 조회 옵션", expanded=False):
            st.caption("현재가 갱신은 보유 중인 모든 종목과 USD/KRW 환율을 캐시 없이 다시 조회합니다.")
            st.caption("실패 종목 재시도 버튼은 실패한 종목만 다시 조회합니다.")


def _render_header(config: AppSecurityConfig, owner_id, store, history_store, metrics, *, public_auth_enabled: bool = False) -> None:
    dirty = _portfolio_is_dirty()
    summary = aggregate_price_statuses(st.session_state.get("price_update_statuses", []))
    last_refresh = metrics.last_price_refresh_at or st.session_state.last_price_refresh_at
    refresh_label = f"{format_kst(last_refresh)} · {format_relative_time(last_refresh)}" if last_refresh else "미조회"
    status_label = (
        f"갱신 {refresh_label} · 정상 {metrics.priced_count} · 캐시 {summary.cached} · "
        f"이전 {metrics.stale_quote_count} · 실패 {metrics.failed_quote_count} · 미조회 {metrics.missing_quote_count}"
    )
    _render_theme_selector()
    left, middle, right = st.columns([2.0, 2.5, 1.35], vertical_alignment="center")
    with left:
        st.title("포트폴리오")
    with middle:
        st.caption(status_label)
        st.caption(_current_save_status_text(public_auth_enabled=public_auth_enabled, dirty=dirty))
    with right:
        if st.button("가격·환율 갱신", type="primary", width="stretch", icon=":material/refresh:"):
            _refresh_prices(config, owner_id, history_store, public_auth_enabled=public_auth_enabled)
        if summary.failed and st.button("실패 재시도", width="stretch", icon=":material/replay:"):
            st.session_state[PRICE_REFRESH_MODE_KEY] = "실패 종목만"
            _refresh_prices(config, owner_id, history_store, mode="실패 종목만", refresh_fx=False, public_auth_enabled=public_auth_enabled)
        if not public_auth_enabled:
            save_disabled = not dirty or owner_id is None or store is None
            if st.button("포트폴리오 저장", disabled=save_disabled, width="stretch", icon=":material/save:"):
                _save_current_portfolio(owner_id, store, history_store, metrics)


def _render_status_messages() -> None:
    account_message = st.session_state.pop(ACCOUNT_STATUS_KEY, None)
    if account_message:
        st.info(account_message)
    save_message = st.session_state.pop(SAVE_STATUS_KEY, None)
    if save_message:
        st.success(save_message)
    render_price_update_log(
        st.session_state.get("price_update_statuses", []),
        st.session_state.get("holdings_rows", []),
    )


def _render_summary_card_section(metrics) -> None:
    render_investment_summary_card(
        metrics,
        portfolio_name=_current_portfolio_name(),
        last_refresh=metrics.last_price_refresh_at or st.session_state.last_price_refresh_at,
        transactions=list(st.session_state.get("portfolio_transactions", [])),
    )


def _render_overview_section(metrics) -> None:
    render_overview(metrics)


def _render_holdings_section(config: AppSecurityConfig, *, public_auth_enabled: bool) -> None:
    _render_cash_fx_tools(config, public_auth_enabled=public_auth_enabled)
    render_transaction_editor()
    render_transaction_cashflow(
        list(st.session_state.get("portfolio_transactions", [])),
        usd_krw=float(st.session_state.usd_krw),
    )
    render_holdings_table(_current_metrics())


def _render_public_holdings_section(config: AppSecurityConfig) -> None:
    _normalize_radio_state(
        PUBLIC_HOLDINGS_VIEW_KEY,
        PUBLIC_HOLDINGS_VIEW_LABELS,
        PUBLIC_HOLDINGS_VIEW_LEGACY_MAP,
        "holdings",
    )
    selected_view = st.radio(
        "사용자 입력 화면",
        list(PUBLIC_HOLDINGS_VIEW_LABELS.keys()),
        format_func=PUBLIC_HOLDINGS_VIEW_LABELS.get,
        key=PUBLIC_HOLDINGS_VIEW_KEY,
        horizontal=True,
        label_visibility="collapsed",
    )
    if selected_view == "holdings":
        render_holdings_table(_current_metrics())
    elif selected_view == "cash_fx":
        _render_cash_fx_tools(config, public_auth_enabled=True)
    else:
        render_transaction_editor()
        render_transaction_cashflow(
            list(st.session_state.get("portfolio_transactions", [])),
            usd_krw=float(st.session_state.usd_krw),
        )


def _render_history_section(owner_id, history_store, historical_schedule_store) -> None:
    render_history_tab(
        owner_id=owner_id,
        portfolio_name=_current_portfolio_name(),
        history_store=history_store,
        historical_schedule_store=historical_schedule_store,
        current_holdings_rows=list(st.session_state.holdings_rows),
        current_cash_krw=float(st.session_state.cash_krw),
        current_cash_usd=float(st.session_state.cash_usd),
        current_usd_krw=float(st.session_state.usd_krw),
        is_authenticated=_is_authenticated(),
    )


def _render_manage_section(owner_id, portfolio_store, history_store) -> None:
    render_csv_tools()
    render_storage_tools(
        owner_id=owner_id,
        store=portfolio_store,
        history_store=history_store,
        metrics=_current_metrics(),
        on_capture=lambda _: _mark_portfolio_clean(),
    )
    render_manual_capture(owner_id=owner_id, history_store=history_store, metrics=_current_metrics())


def _render_private_dashboard_sections(security_config, owner_id, portfolio_store, history_store, historical_schedule_store, metrics) -> None:
    summary_card_tab, overview_tab, holdings_tab, history_tab, manage_tab = st.tabs(["총괄현황", "세부내역", "사용자 입력", "자산추이", "저장 관리"])
    with summary_card_tab:
        _render_summary_card_section(metrics)
    with overview_tab:
        _render_overview_section(metrics)
    with holdings_tab:
        _render_holdings_section(security_config, public_auth_enabled=False)
    with history_tab:
        _render_history_section(owner_id, history_store, historical_schedule_store)
    with manage_tab:
        _render_manage_section(owner_id, portfolio_store, history_store)


def _render_public_dashboard_sections(security_config, owner_id, portfolio_store, history_store, historical_schedule_store, metrics) -> None:
    _normalize_radio_state(PUBLIC_SECTION_KEY, PUBLIC_SECTION_LABELS, PUBLIC_SECTION_LEGACY_MAP, "summary")
    with st.container(key="public_section_tabs"):
        selected_section = st.radio(
            "화면 선택",
            list(PUBLIC_SECTION_LABELS.keys()),
            format_func=PUBLIC_SECTION_LABELS.get,
            key=PUBLIC_SECTION_KEY,
            horizontal=True,
            label_visibility="collapsed",
        )
    if selected_section == "summary":
        _render_summary_card_section(metrics)
    elif selected_section == "details":
        _render_overview_section(metrics)
    elif selected_section == "input":
        _render_public_holdings_section(security_config)
    else:
        _render_history_section(owner_id, history_store, historical_schedule_store)


st.set_page_config(page_title="포트폴리오 대시보드", layout="wide")
_initialize_theme_state()
inject_styles(_current_theme_mode())
public_auth_enabled = _read_public_auth_settings()
if public_auth_enabled:
    inject_public_cloud_chrome_guard()
_initialize_session_state(public_auth_enabled=public_auth_enabled)
security_config = _read_security_config()
storage_config = _read_storage_config(public_auth_enabled=public_auth_enabled)
if public_auth_enabled and not _is_authenticated():
    _render_public_auth_gate(storage_config)
if not public_auth_enabled and should_lock_entire_app(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)

portfolio_store, history_store, historical_schedule_store = _build_stores(storage_config)
owner_id = _resolve_owner_id(storage_config)
_auto_load_account_portfolio(owner_id, portfolio_store)
if not public_auth_enabled:
    _auto_refresh_loaded_prices(owner_id, portfolio_store, history_store)
_render_sidebar(security_config, owner_id, portfolio_store, public_auth_enabled=public_auth_enabled)
_render_security_status(security_config, public_auth_enabled=public_auth_enabled)
if not public_auth_enabled and should_lock_manual_mode(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)
metrics = _current_metrics()
if public_auth_enabled:
    _auto_save_public_portfolio(owner_id, portfolio_store, history_store, metrics)
_render_header(security_config, owner_id, portfolio_store, history_store, metrics, public_auth_enabled=public_auth_enabled)
_render_status_messages()

if public_auth_enabled:
    _render_public_dashboard_sections(security_config, owner_id, portfolio_store, history_store, historical_schedule_store, metrics)
else:
    _render_private_dashboard_sections(security_config, owner_id, portfolio_store, history_store, historical_schedule_store, metrics)
