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
from app.ui.styles import inject_styles
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
    TTLQuoteCache,
    build_korea_quote_provider,
    build_yfinance_fx_provider,
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

AUTHENTICATED_KEY = "is_authenticated"
ACCOUNT_ID_KEY = "authenticated_account_id"
OWNER_ID_KEY = "authenticated_owner_id"
DEFAULT_PORTFOLIO_KEY = "authenticated_default_portfolio"
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
UNPROTECTED_WARNING = "공개 앱에서 저장소와 직접 입력 보호를 위해 APP_PASSWORD 설정을 권장합니다."


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


def _logout() -> None:
    st.session_state[AUTHENTICATED_KEY] = False
    for key in (ACCOUNT_ID_KEY, OWNER_ID_KEY, DEFAULT_PORTFOLIO_KEY, AUTO_LOAD_ATTEMPTED_KEY, AUTO_PRICE_REFRESHED_KEY):
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
    if st.session_state.pop(MARK_CLEAN_KEY, False) or SAVED_SIGNATURE_KEY not in st.session_state:
        _mark_portfolio_clean()


def _current_portfolio_name() -> str:
    return _clean_portfolio_name(st.session_state.get(PORTFOLIO_NAME_KEY))


def _is_authenticated() -> bool:
    return bool(st.session_state.get(AUTHENTICATED_KEY, False))


def _render_login_form(config: AppSecurityConfig) -> None:
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


def _render_security_status(config: AppSecurityConfig) -> None:
    with st.sidebar:
        st.subheader("인증 상태")
        if not config.has_password:
            st.warning(UNPROTECTED_WARNING)
            return
        if _is_authenticated():
            account_id = st.session_state.get(ACCOUNT_ID_KEY) or st.session_state.get(OWNER_ID_KEY) or "main"
            st.caption(f"상태: 인증됨 · {account_id}")
            if st.button("로그아웃"):
                _logout()
                st.rerun()
        else:
            st.caption("직접 입력 기능은 비밀번호가 필요합니다.")


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


def _refresh_price_rows(
    owner_id,
    history_store,
    *,
    mode: str,
    on_progress=None,
) -> bool:
    us_provider = build_yfinance_provider()
    korea_provider = build_korea_quote_provider()
    all_rows = list(st.session_state.holdings_rows)
    target_rows = list(select_price_refresh_rows(all_rows, mode))
    if not target_rows:
        return False

    updated_rows, statuses = refresh_holding_quotes(
        target_rows,
        us_provider,
        korea_provider=korea_provider,
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


def _refresh_prices(_config: AppSecurityConfig, owner_id, history_store) -> None:
    progress = st.progress(0, text="최근 제공 가격 조회 준비 중")

    def update_progress(completed: int, total: int, symbol: str) -> None:
        percent = int((completed / max(total, 1)) * 100)
        progress.progress(percent, text=f"최근 제공 가격 조회 중: {symbol} ({completed}/{total})")

    mode = st.session_state.get(PRICE_REFRESH_MODE_KEY, "미조회/오래된 가격만")
    refreshed = _refresh_price_rows(owner_id, history_store, mode=mode, on_progress=update_progress)
    progress.empty()
    if not refreshed:
        st.info("새로 조회할 대상 종목이 없습니다.")
        return
    st.rerun()


def _fetch_fx_rate():
    provider = build_yfinance_fx_provider()
    try:
        new_rate, status = refresh_usd_krw(provider, float(st.session_state.usd_krw))
    except ValueError as exc:
        st.error(f"환율을 갱신할 수 없습니다: {exc}")
        return None
    return new_rate, status


def _apply_fx_rate(new_rate, status) -> bool:
    st.session_state.usd_krw = new_rate
    st.session_state.fx_status_message = status.message
    st.session_state.fx_fetched_at = status.fetched_at
    return status.status in {"updated", "cached"}


def _refresh_fx(_config: AppSecurityConfig) -> None:
    result = _fetch_fx_rate()
    if result is None:
        return
    new_rate, status = result
    st.session_state[PENDING_PORTFOLIO_STATE_KEY] = {
        "usd_krw": new_rate,
        "fx_status_message": status.message,
        "fx_fetched_at": status.fetched_at,
    }
    st.rerun()


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
    if owner_id is None or not st.session_state.get("holdings_rows"):
        return
    refresh_key = f"{owner_id}:{_current_portfolio_name()}"
    if st.session_state.get(AUTO_PRICE_REFRESHED_KEY) == refresh_key:
        return
    st.session_state[AUTO_PRICE_REFRESHED_KEY] = refresh_key
    fx_result = _fetch_fx_rate()
    refreshed_fx = _apply_fx_rate(*fx_result) if fx_result is not None else False
    refreshed = _refresh_price_rows(owner_id, history_store, mode="전체 강제 재조회")
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
        if st.button("선택 포트폴리오 불러오기", disabled=_portfolio_is_dirty(), width="stretch"):
            try:
                queue_portfolio_record_load(selected)
                st.rerun()
            except (PortfolioStoreError, ValueError) as exc:
                st.error(f"포트폴리오를 불러올 수 없습니다: {exc}")
    st.caption("새 포트폴리오 생성과 이름 변경은 관리 탭에서 처리합니다.")


def _render_sidebar(config: AppSecurityConfig, owner_id, store) -> None:
    with st.sidebar:
        st.subheader("현재 포트폴리오")
        _render_saved_portfolio_selector(owner_id, store)
        if _portfolio_is_dirty():
            st.caption("저장하지 않은 변경 있음")
            if st.button("변경사항 되돌리기", width="stretch"):
                _restore_last_saved_state()
                st.rerun()
        else:
            st.caption("저장됨")
        confirm_reset = st.checkbox("현재 입력 초기화 확인", key="confirm_reset_portfolio")
        if st.button("현재 입력 초기화", disabled=not confirm_reset, width="stretch"):
            _reset_current_portfolio_state(_current_portfolio_name())
            st.rerun()
        with st.expander("현금 및 환율", expanded=True):
            st.number_input("원화 현금", min_value=0.0, step=100000.0, key="cash_krw")
            st.number_input("달러 현금", min_value=0.0, step=100.0, key="cash_usd")
            st.number_input("환율", min_value=0.01, step=1.0, key="usd_krw", help="USD/KRW")
            if st.button("환율 갱신"):
                _refresh_fx(config)
            st.caption(st.session_state.fx_status_message)
            if st.session_state.fx_fetched_at:
                st.caption(f"환율 조회: {format_kst(st.session_state.fx_fetched_at, compact=True)}")
        with st.expander("데이터 정보", expanded=False):
            st.caption("미국 주식과 USD/KRW 환율은 yfinance, 국내 주식은 FinanceDataReader 기반 최근 제공 가격을 사용합니다. 무료 데이터라 실시간을 보장하지 않습니다.")
        with st.expander("가격 조회 옵션", expanded=False):
            st.radio(
                "가격 새로고침 대상",
                ["미조회/오래된 가격만", "실패 종목만", "전체 강제 재조회"],
                key=PRICE_REFRESH_MODE_KEY,
                help="전체 강제 재조회는 현재 세션의 가격 캐시를 우회합니다.",
            )


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
        if summary.failed and st.button("실패 종목 다시 시도", width="stretch"):
            st.session_state[PRICE_REFRESH_MODE_KEY] = "실패 종목만"
            _refresh_prices(config, owner_id, history_store)
        save_disabled = not dirty or owner_id is None or store is None
        if st.button("현재 포트폴리오 저장", disabled=save_disabled, width="stretch"):
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


st.set_page_config(page_title="포트폴리오 대시보드", layout="wide")
inject_styles()
_initialize_session_state()
security_config = _read_security_config()
if should_lock_entire_app(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)

storage_config = _read_storage_config()
portfolio_store, history_store, historical_schedule_store = _build_stores(storage_config)
owner_id = _resolve_owner_id(storage_config)
_auto_load_account_portfolio(owner_id, portfolio_store)
_auto_refresh_loaded_prices(owner_id, portfolio_store, history_store)
_render_sidebar(security_config, owner_id, portfolio_store)
_render_security_status(security_config)
if should_lock_manual_mode(security_config, is_authenticated=_is_authenticated()):
    _render_login_form(security_config)
metrics = _current_metrics()
_render_header(security_config, owner_id, portfolio_store, history_store, metrics)
_render_status_messages()

summary_card_tab, overview_tab, holdings_tab, history_tab, manage_tab = st.tabs(["투자 총괄 카드", "개요", "보유자산", "자산추이", "관리"])
with summary_card_tab:
    render_investment_summary_card(
        metrics,
        portfolio_name=_current_portfolio_name(),
        last_refresh=metrics.last_price_refresh_at or st.session_state.last_price_refresh_at,
    )
with overview_tab:
    render_overview(metrics)
with holdings_tab:
    render_transaction_editor()
    render_transaction_cashflow(
        list(st.session_state.get("portfolio_transactions", [])),
        usd_krw=float(st.session_state.usd_krw),
    )
    metrics = _current_metrics()
    render_holdings_table(metrics)
with history_tab:
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
