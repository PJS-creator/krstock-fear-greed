import re

from streamlit.testing.v1 import AppTest

RAW_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _element_texts(elements):
    texts = []
    for element in elements:
        for attr in ("label", "value", "text"):
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
    ]
    chunks = []
    for name in names:
        chunks.extend(_element_texts(getattr(at, name, [])))
    return "\n".join(chunks)


def test_dashboard_app_smoke_has_tabs_kpis_and_no_raw_iso():
    at = AppTest.from_file("app/portfolio_dashboard.py").run(timeout=20)

    assert not at.exception
    text = _app_text(at)
    for label in ("투자 총괄 카드", "개요", "보유자산", "자산추이", "관리"):
        assert label in text
    for label in ("현금 및 환율", "현금/환율 적용", "USD/KRW 환율 갱신", "자산 입력", "거래 1건 입력", "매입/매도 기준 자산 증감"):
        assert label in text
    metric_labels = _element_texts(at.metric)
    for label in ("총자산", "오늘 변동", "총현금", "USD 노출도"):
        assert label in metric_labels
    assert RAW_ISO_RE.search(text) is None


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
