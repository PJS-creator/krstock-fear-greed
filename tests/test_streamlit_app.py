import re
from pathlib import Path
from urllib.error import URLError

from streamlit.testing.v1 import AppTest

RAW_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


class _FakeYahooFxResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"result":"success","base_code":"USD","rates":{"KRW":1388.25}}'


def _element_texts(elements):
    texts = []
    for element in elements:
        for attr in ("label", "value", "text", "options"):
            value = getattr(element, attr, None)
            if value is not None:
                texts.append(str(value))
    return texts


def _app_text(at: AppTest) -> str:
    names = [
        "title",
        "header",
        "subheader",
        "caption",
        "markdown",
        "info",
        "warning",
        "success",
        "button",
        "tabs",
        "metric",
        "expander",
        "radio",
    ]
    chunks = []
    for name in names:
        chunks.extend(_element_texts(getattr(at, name, [])))
    return "\n".join(chunks)


def test_dashboard_app_smoke_has_tabs_kpis_and_no_raw_iso():
    at = AppTest.from_file("app/portfolio_dashboard.py").run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    for label in ("총괄현황", "세부내역", "사용자 입력", "자산추이", "성과분석", "리스크분석", "매매일지", "리밸런싱", "저장 관리"):
        assert label in text
    for label in ("다크", "라이트"):
        assert label in text
    assert at.session_state["app_theme_mode"] == "dark"
    for label in ("현금·입출금·환율", "입출금 입력", "환전 입력", "현금 원장", "USD/KRW 환율 갱신", "자산 입력", "표준 거래 입력", "상세 옵션", "매입/매도 기준 자산 증감"):
        assert label in text
    assert "가격·환율 갱신" in text
    assert "아직 포트폴리오 데이터가 없습니다." in text
    assert RAW_ISO_RE.search(text) is None


def test_dashboard_theme_toggle_accepts_light_mode():
    at = AppTest.from_file("app/portfolio_dashboard.py")
    at.session_state["app_theme_choice"] = "라이트"
    at.run(timeout=20)

    assert not at.exception
    assert at.session_state["app_theme_mode"] == "light"
    assert at.session_state["theme_mode"] == "light"
    assert "라이트" in _app_text(at)


def test_theme_css_keeps_metric_and_radio_text_readable():
    source = Path("app/ui/styles.py").read_text(encoding="utf-8")

    assert 'div[data-testid="stWidgetLabel"]' in source
    assert 'div[data-testid="stForm"] label' in source
    assert 'div[data-baseweb="select"] *' in source
    assert 'div[data-testid="stMetricLabel"] *' in source
    assert 'div[data-testid="stMetricLabel"] svg' in source
    assert 'div[data-testid="stMetricLabel"] p' in source
    assert 'div[data-testid="stMetric"] label' in source
    assert 'div[data-testid="stMetricValue"] *' in source
    assert 'div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg' in source
    assert '[data-testid="stTooltipIcon"]' in source
    assert '[data-testid="stTooltipHoverTarget"]' in source
    assert 'color: var(--app-text) !important;' in source
    assert 'div[data-testid="stDataFrame"] canvas' in source
    assert ".app-data-table-wrap" in source
    assert ".holdings-data-table-wrap" in source
    assert 'div[data-testid="stDataEditor"] [role="columnheader"]' in source
    assert 'div[data-testid="stExpander"] details > summary' in source
    assert 'div[data-testid="stExpander"] details[open] > summary' in source
    assert 'div[role="radiogroup"] label > div:first-child' in source
    assert ".app-empty-state" in source
    assert ".app-box" in source
    assert ".app-badge" in source
    assert ".metric-grid" in source
    assert ".app-metric-card" in source
    assert ".app-metric-profit" in source
    assert ".app-metric-loss" in source
    assert ".app-metric-title {\n            color: var(--app-heading);" in source
    assert ".app-metric-info .app-metric-title" not in source
    assert ".app-metric-profit .app-metric-title" not in source
    assert "justify-content: center !important;" in source
    assert ".st-key-app_theme_topbar" in source
    assert "grid-template-columns: repeat(2, 4.45rem);" in source
    assert "white-space: nowrap !important;" in source
    assert ".st-key-public_section_tabs" in source
    assert ".st-key-public_input_tabs" in source
    assert 'div[data-testid="stCheckbox"] label > div:first-child' in source
    assert "background: var(--app-input-bg) !important;" in source
    assert "border: 1px solid var(--app-border-strong) !important;" in source
    assert "label:has(input:checked) > div:first-child" in source
    assert ".st-key-public_login_remember_me" in source
    assert ".st-key-public_signup_remember_me" in source
    assert '[data-testid="stTooltipHoverTarget"]::after' in source
    assert 'content: "?";' in source
    assert "content: none !important;" in source
    assert "gap: var(--token-space-1) !important;" in source
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in source
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in source
    assert "border-bottom: 1px solid var(--app-border);" in source
    assert "label:has(input:checked)::after" in source


def test_theme_selector_does_not_set_widget_key_default_from_session_state():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "st.session_state[APP_THEME_CHOICE_KEY] =" not in source
    assert 'radio_kwargs["index"] = None' in source


def test_public_signup_uses_public_redirect_url_for_email_confirmation():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "def _public_auth_redirect_url()" in source
    assert "PUBLIC_APP_URL" in source
    assert "email_redirect_to=_public_auth_redirect_url()" in source
    assert "def _render_public_auth_callback_notice()" in source


def test_public_login_remember_me_restores_encrypted_session_cookie():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")
    persistence_source = Path("portfolio/session_persistence.py").read_text(encoding="utf-8")
    auth_persistence_source = Path("app/ui/auth_persistence.py").read_text(encoding="utf-8")
    requirements_source = Path("app/requirements.txt").read_text(encoding="utf-8")

    assert '"로그인 유지"' in source
    assert '"가입 후 로그인 유지"' in source
    assert 'key="public_login_remember_me"' in source
    assert 'key="public_signup_remember_me"' in source
    assert "AUTH_SESSION_SECRET" in source
    assert "decode_remembered_session" in source
    assert "encode_remembered_session" in source
    assert "_restore_public_auth_session(storage_config)" in source
    assert "restore_session" in Path("portfolio/supabase_auth.py").read_text(encoding="utf-8")
    assert "mobile-public-auth-status" in source
    assert "app_logout" in source
    assert "def _handle_public_logout_query()" in source
    assert "Fernet" in persistence_source
    assert "refresh_token" in persistence_source
    assert "@st.cache_resource" not in auth_persistence_source
    assert "@st.cache_data" not in auth_persistence_source
    assert "extra-streamlit-components" in requirements_source


def test_shared_metric_card_component_exists():
    source = Path("app/ui/components.py").read_text(encoding="utf-8")
    performance_source = Path("app/ui/performance.py").read_text(encoding="utf-8")
    journal_source = Path("app/ui/journal.py").read_text(encoding="utf-8")

    assert "def render_metric_card(" in source
    assert "def render_metric_card_grid(" in source
    assert "app-metric-card" in source
    assert "app-metric-profit" in Path("app/ui/styles.py").read_text(encoding="utf-8")
    assert "render_metric_card(" in performance_source
    assert "render_metric_card(" in journal_source


def test_overview_components_use_shared_metric_cards_instead_of_streamlit_metric():
    source = Path("app/ui/components.py").read_text(encoding="utf-8")

    assert "st.metric(" not in source
    assert "render_metric_card_grid(" in source
    assert "_pnl_status(metrics.day_change_krw)" in source
    assert "eok_man_krw(metrics.total_value_krw)" in source
    assert "최대 상승 기여" in source
    assert "최대 하락 기여" in source


def test_investment_summary_preserves_heatmap_and_adds_cash_split():
    source = Path("app/ui/investment_summary_card.py").read_text(encoding="utf-8")

    assert "summary-heatmap-area" in source
    assert "summary-table-wrap" in source
    assert "summary-split-grid" in source
    assert "summary-split-heading" in source
    assert "summary-split-pct" in source
    assert "주식 평가금액 · 총자산 대비" not in source
    assert "투자자산" in source
    assert "현금" in source


def test_price_log_detail_expander_is_rendered_collapsed_by_default():
    at = AppTest.from_file("app/portfolio_dashboard.py")
    at.session_state["price_update_statuses"] = [
        {
            "symbol": "MU",
            "market": "US",
            "currency": "USD",
            "status": "updated",
            "message": "미국 주식 최근 제공 가격으로 업데이트했습니다.",
            "fetched_at": "2026-06-23T03:00:00+00:00",
        }
    ]
    at.session_state["holdings_rows"] = [
        {
            "market": "US",
            "ticker": "MU",
            "quantity": 1,
            "display_name": "Micron",
            "current_price": 120,
            "previous_close": 119,
            "provider": "yfinance",
            "fetched_at": "2026-06-23T03:00:00+00:00",
        }
    ]
    at.run(timeout=20)

    assert not at.exception
    expanders = [expander for expander in at.expander if str(getattr(expander, "label", "")).startswith("데이터 업데이트 상세")]
    assert expanders
    if hasattr(expanders[0], "expanded"):
        assert expanders[0].expanded is False
    assert RAW_ISO_RE.search(_app_text(at)) is None


def test_sample_portfolio_load_does_not_mutate_widget_keys_after_render():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.run(timeout=20)

    sample_buttons = [button for button in at.button if getattr(button, "label", "") == "샘플 포트폴리오로 둘러보기"]
    assert sample_buttons
    sample_buttons[0].click().run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "삼성전자" in text
    assert RAW_ISO_RE.search(text) is None


def test_public_holdings_section_defers_transaction_editor_by_default():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["public_dashboard_section"] = "보유자산"
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "보유 종목을 입력하면 표가 표시됩니다." in text
    assert "표준 거래 입력" not in text
    assert "고급 입력 · 빠른 입력" not in text
    assert at.session_state["public_dashboard_section"] == "input"


def test_public_onboarding_renders_for_empty_authenticated_portfolio():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    for label in ("처음 시작하기", "샘플 포트폴리오로 둘러보기", "현재 보유종목만 빠르게 입력", "거래/현금 CSV 업로드"):
        assert label in text


def test_public_onboarding_holdings_mode_keeps_quick_editor_visible():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["onboarding_mode"] = "holdings"
    at.session_state["quick_holdings_draft_rows"] = [{"ticker_or_name": "삼성전자", "quantity": 200, "avg_price": 70000}]
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "빠른 입력" in text
    assert at.session_state["quick_holdings_draft_rows"][0]["quantity"] == 200
    source = Path("app/ui/holdings.py").read_text(encoding="utf-8")
    assert 'st.form("quick_holding_add_form"' in source
    assert '"종목명 또는 티커"' in source
    assert '"행 추가"' in source
    assert 'st.expander("표 형태로 한 번에 편집"' in source
    assert 'key="quick_holdings_table_editor"' in source


def test_public_holdings_transaction_input_renders_only_when_selected():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["public_dashboard_section"] = "보유자산"
    at.session_state["public_holdings_view"] = "거래 입력"
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "표준 거래 입력" in text
    assert "고급 입력 · 빠른 입력" in text


def test_public_csv_portability_tools_render_when_selected():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["public_dashboard_section"] = "보유자산"
    at.session_state["public_holdings_view"] = "CSV"
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    for label in ("CSV 가져오기/내보내기", "거래 CSV", "현금 원장 CSV", "내보내기"):
        assert label in text
    source = Path("app/ui/data_portability.py").read_text(encoding="utf-8")
    for label in ("거래 CSV 템플릿 다운로드", "현금 원장 CSV 템플릿 다운로드", "전체 데이터 JSON 내보내기"):
        assert label in source


def test_public_cash_fx_refresh_button_falls_back_and_applies_rate(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        url = getattr(request, "full_url", request)
        calls.append((url, timeout))
        if "query1.finance.yahoo.com" in url:
            raise URLError("blocked")
        return _FakeYahooFxResponse()

    monkeypatch.setattr("portfolio.pricing.yahoo_finance.urlopen", fake_urlopen)
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["public_dashboard_section"] = "보유자산"
    at.session_state["public_holdings_view"] = "현금/환율"
    at.session_state["usd_krw"] = 1300.0
    at.run(timeout=20)

    refresh_buttons = [button for button in at.button if getattr(button, "label", "") == "USD/KRW 환율 갱신"]
    assert len(refresh_buttons) == 1
    refresh_buttons[0].click().run(timeout=20)

    assert not at.exception
    assert calls == [
        ("https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?range=5d&interval=1d", 4.0),
        ("https://open.er-api.com/v6/latest/USD", 4.0),
    ]
    assert at.session_state["usd_krw"] == 1388.25
    assert at.session_state["fx_status_message"] == "USD/KRW 환율을 갱신했습니다."


def test_current_refresh_button_forces_all_quotes_and_fx_refresh():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")
    components_source = Path("app/ui/components.py").read_text(encoding="utf-8")

    assert "def render_app_header(" in components_source
    assert 'st.button("가격·환율 갱신"' in components_source
    assert 'mode: str = "전체 강제 재조회"' in source
    assert "refresh_fx: bool = True" in source
    assert "조회할 보유종목 또는 달러 현금이 없습니다." in source
    assert "PRICE_REFRESH_IN_PROGRESS_KEY" in source
    assert "cache = TTLFxCache() if force_refresh else None" in source
    assert "_fetch_fx_rate(public_auth_enabled=public_auth_enabled, force_refresh=True)" in source
    assert "_run_price_refresh(config, owner_id, history_store, public_auth_enabled=public_auth_enabled)" in source
    assert 'mode="실패 종목만", refresh_fx=False' in source
    assert '"가격 새로고침 대상"' not in source


def test_one_minute_auto_quote_refresh_is_removed_and_manual_refresh_remains():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")
    styles_source = Path("app/ui/styles.py").read_text(encoding="utf-8")
    guide_source = Path("docs/app_user_guide.md").read_text(encoding="utf-8")

    for removed_text in (
        "AUTO_PRICE_REFRESH_INTERVAL_SECONDS",
        "AUTO_PRICE_REFRESH_COOLDOWN_SECONDS",
        "auto_price_refresh_enabled",
        "1분 자동갱신",
        "_render_auto_refresh_controls",
        "_render_sidebar_auto_refresh_status",
        "_render_auto_refresh_runner",
        "_maybe_run_periodic_price_refresh",
        "periodic_price_refresh_failed",
        '@st.fragment(run_every=',
    ):
        assert removed_text not in source
    assert ".st-key-auto_price_refresh_enabled" not in styles_source
    assert "1분 자동갱신은 제공하지 않습니다" in guide_source
    assert 'st.button("가격·환율 갱신"' in Path("app/ui/components.py").read_text(encoding="utf-8")
    assert "현재가 갱신은 보유 중인 모든 종목과 USD/KRW 환율을 캐시 없이 다시 조회합니다." in source
    assert "KIS 설정" in source
    assert "최근 주식 조회 출처" in source
    assert "한국투자 Open API" in source


def test_public_app_renders_manual_refresh_without_auto_refresh_toggle():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.run(timeout=20)

    assert not at.exception
    assert all(getattr(checkbox, "label", "") != "1분 자동갱신" for checkbox in at.checkbox)
    assert len([button for button in at.button if getattr(button, "label", "") == "가격·환율 갱신"]) == 1


def test_public_header_refresh_does_not_call_fx_api_without_assets(monkeypatch):
    def fail_urlopen(*args, **kwargs):
        raise AssertionError("no external FX request expected for empty portfolio")

    monkeypatch.setattr("portfolio.pricing.yahoo_finance.urlopen", fail_urlopen)
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.run(timeout=20)

    refresh_buttons = [button for button in at.button if getattr(button, "label", "") == "가격·환율 갱신"]
    assert len(refresh_buttons) == 1
    refresh_buttons[0].click().run(timeout=20)

    assert not at.exception
    assert "조회할 보유종목 또는 달러 현금이 없습니다." in _app_text(at)


def test_public_header_shows_only_compact_refresh_timestamp():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["last_price_refresh_at"] = "2026-07-05T00:51:00+00:00"
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "갱신 2026-07-05 09:51 KST" in text
    assert "정상 0" not in text
    assert "캐시 0" not in text
    assert "이전 0" not in text
    assert "실패 0" not in text
    assert "미조회 0" not in text
    assert "저장됨" not in text


def test_public_header_refresh_failure_keeps_app_shell(monkeypatch):
    def fail_refresh(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.portfolio_dashboard.refresh_holding_quotes", fail_refresh)
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["holdings_rows"] = [
        {
            "market": "US",
            "ticker": "QURE",
            "display_name": "QURE",
            "currency": "USD",
            "quantity": 1,
            "avg_price": 10,
            "current_price": None,
            "quote_status": "missing",
        }
    ]
    at.run(timeout=20)

    refresh_buttons = [button for button in at.button if getattr(button, "label", "") == "가격·환율 갱신"]
    assert len(refresh_buttons) == 1
    refresh_buttons[0].click().run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "포트폴리오" in text
    assert "가격·환율 갱신 실패" in text
    assert at.session_state["price_refresh_in_progress"] is False


def test_stale_price_refresh_state_is_cleared_on_next_run():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["price_refresh_in_progress"] = True
    at.session_state["price_refresh_started_at"] = 1.0
    at.run(timeout=20)

    assert not at.exception
    assert at.session_state["price_refresh_in_progress"] is False
    assert "price_refresh_started_at" not in at.session_state
    assert "가격·환율 갱신 상태를 자동으로 복구" in _app_text(at)


def test_public_auth_session_refresh_is_throttled_and_token_only():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "PUBLIC_AUTH_SESSION_REFRESH_INTERVAL_SECONDS = 45 * 60" in source
    assert "def _refresh_public_auth_session_if_due(storage_config)" in source
    assert "_authenticate_public_account(account, reset_portfolio_state=False)" in source
    assert "authenticated_session_refresh_last_attempt_at" in source
    assert "storage_config = _read_storage_config(public_auth_enabled=True)" in source
    assert "reset_portfolio_state: bool = True" in source


def test_public_auto_load_success_messages_are_not_shown_as_top_alerts():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "포트폴리오를 자동으로 불러왔습니다" not in source
    assert "최근 가격을 자동 갱신했습니다" not in source
    assert "최근 가격과 USD/KRW 환율을 자동 갱신했습니다" not in source


def test_public_app_hides_manual_storage_management_ui():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["portfolio_name"] = "legacy-name"
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    for hidden in ("관리", "포트폴리오 저장", "저장된 포트폴리오", "선택 포트폴리오 불러오기"):
        assert hidden not in text
    assert at.session_state["portfolio_name"] == "main"


def test_public_journal_renders_krw_cash_events_without_section_fallback():
    at = AppTest.from_file("app/public_portfolio_dashboard.py")
    at.session_state["is_authenticated"] = True
    at.session_state["authenticated_account_id"] = "demo@example.com"
    at.session_state["authenticated_owner_id"] = "user-demo-id"
    at.session_state["authenticated_default_portfolio"] = "main"
    at.session_state["public_dashboard_section"] = "journal"
    at.session_state["cash_ledger_entries"] = [
        {
            "event_date": "2026-07-01",
            "currency": "KRW",
            "event_type": "deposit",
            "amount": "1000000",
            "memo": "원화 입금",
        }
    ]
    at.run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    assert "매매일지" in text
    assert "입금" in text
    assert "이 영역을 불러오는 중 문제가 발생했습니다." not in text
