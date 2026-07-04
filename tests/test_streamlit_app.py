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
    for label in ("총괄현황", "세부내역", "사용자 입력", "자산추이", "저장 관리"):
        assert label in text
    for label in ("다크", "라이트"):
        assert label in text
    assert at.session_state["app_theme_mode"] == "dark"
    for label in ("현금 및 환율", "현금/환율 적용", "USD/KRW 환율 갱신", "자산 입력", "표준 거래 입력", "매입/매도 기준 자산 증감"):
        assert label in text
    assert "가격·환율 갱신" in text
    metric_labels = _element_texts(at.metric)
    for label in ("총자산", "오늘 변동", "총현금", "USD 노출도"):
        assert label in metric_labels
    assert RAW_ISO_RE.search(text) is None


def test_dashboard_theme_toggle_accepts_light_mode():
    at = AppTest.from_file("app/portfolio_dashboard.py")
    at.session_state["app_theme_choice"] = "라이트"
    at.run(timeout=20)

    assert not at.exception
    assert at.session_state["app_theme_mode"] == "light"
    assert "라이트" in _app_text(at)


def test_theme_css_keeps_metric_and_radio_text_readable():
    source = Path("app/ui/styles.py").read_text(encoding="utf-8")

    assert 'div[data-testid="stMetricLabel"] *' in source
    assert 'div[data-testid="stMetricValue"] *' in source
    assert 'div[role="radiogroup"] label > div:first-child' in source
    assert "justify-content: center !important;" in source
    assert ".st-key-app_theme_topbar" in source
    assert ".st-key-public_section_tabs" in source
    assert ".st-key-public_input_tabs" in source
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in source
    assert "border-bottom: 1px solid var(--app-border);" in source
    assert "label:has(input:checked)::after" in source


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
    at = AppTest.from_file("app/portfolio_dashboard.py").run(timeout=20)

    sample_buttons = [button for button in at.button if getattr(button, "label", "") == "샘플 불러오기"]
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

    assert 'st.button("가격·환율 갱신"' in source
    assert 'mode: str = "전체 강제 재조회"' in source
    assert "refresh_fx: bool = True" in source
    assert "cache = TTLFxCache() if force_refresh else None" in source
    assert "_fetch_fx_rate(public_auth_enabled=public_auth_enabled, force_refresh=True)" in source
    assert "_refresh_prices(config, owner_id, history_store, public_auth_enabled=public_auth_enabled)" in source
    assert 'mode="실패 종목만", refresh_fx=False' in source
    assert '"가격 새로고침 대상"' not in source


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
