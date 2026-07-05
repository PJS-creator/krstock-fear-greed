import pandas as pd

from app.ui.holdings import _holdings_table_html, _mobile_holdings_cards_html


def test_mobile_holdings_cards_render_compact_holding_summary():
    frame = pd.DataFrame(
        [
            {
                "종목": "삼성전자",
                "시장": "KR",
                "수량 표시": "200",
                "최근 제공 가격 표시": "₩80,000",
                "평가액 표시": "16,000,000원",
                "오늘 변동액": "+100,000원",
                "오늘 변동률": "+0.6%",
                "비중": 24.5,
                "가격 상태": "최신",
            }
        ]
    )

    html = _mobile_holdings_cards_html(frame)

    assert "mobile-holdings-cards" in html
    assert "삼성전자" in html
    assert "24.50%" in html
    assert "오늘 변동" in html
    assert "+100,000원 (+0.6%)" in html
    assert "mobile-holding-up" in html


def test_holdings_table_html_uses_theme_table_markup_and_progress_bar():
    frame = pd.DataFrame(
        [
            {
                "종목": "QURE",
                "시장": "US",
                "수량 표시": "1,000",
                "최근 제공 가격 표시": "$41.81",
                "평가액 표시": "63,975,575원",
                "오늘 변동액": "-514만 원",
                "비중": 25.7,
                "가격 상태": "최근종가",
                "조회 시각": "07-05 19:08 KST",
            }
        ]
    )

    html = _holdings_table_html(
        frame,
        ["종목", "시장", "수량 표시", "최근 제공 가격 표시", "평가액 표시", "오늘 변동액", "비중", "가격 상태", "조회 시각"],
    )

    assert "app-data-table-wrap holdings-data-table-wrap" in html
    assert "app-data-table holdings-data-table" in html
    assert "app-table-progress-fill" in html
    assert "style='width:25.70%'" in html
    assert "mobile-holding-down" in html
    assert "QURE" in html
