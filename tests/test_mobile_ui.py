import pandas as pd

from app.ui.holdings import _mobile_holdings_cards_html


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
