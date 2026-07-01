from portfolio.holdings import build_portfolio_metrics

from app.ui.investment_summary_card import _allocation_rows, _heatmap_tiles, _holding_table_rows


def _metrics():
    return build_portfolio_metrics(
        [
            {
                "market": "KR",
                "ticker": "005930",
                "display_name": "삼성전자",
                "quantity": 10,
                "avg_price": 72300,
                "current_price": 80000,
                "previous_close": 79000,
            },
            {
                "market": "US",
                "ticker": "MU",
                "display_name": "Micron",
                "quantity": 2,
                "avg_price": 100,
                "current_price": 120,
                "previous_close": 125,
            },
        ],
        cash_krw=1_000_000,
        cash_usd=100,
        usd_krw=1400,
    )


def test_summary_allocation_includes_cash_and_prefers_korean_company_name():
    rows = _allocation_rows(_metrics())

    assert any(row["label"] == "삼성전자" for row in rows)
    assert any(row["label"] == "현금" for row in rows)
    assert round(sum(row["weight"] for row in rows), 6) == 1


def test_summary_holding_table_contains_average_price_and_return_rate():
    html_rows = "\n".join(
        _holding_table_rows(
            _metrics(),
            transactions=[
                {"transaction_type": "buy", "ticker": "005930", "market": "KR", "currency": "KRW", "display_name": "삼성전자", "unit_price": 72300, "quantity": 10, "occurred_at": "2025-01-01"},
                {"transaction_type": "buy", "ticker": "MU", "market": "US", "currency": "USD", "display_name": "Micron", "unit_price": 100, "quantity": 2, "occurred_at": "2025-01-01"},
            ],
        )
    )

    assert "삼성전자" in html_rows
    assert "₩72,300" in html_rows
    assert "₩723,000" in html_rows
    assert "$100.00" in html_rows
    assert "$120.00" in html_rows
    assert "-$5.00 (-4.0%)" in html_rows
    assert "%" in html_rows
    assert "IRR" not in html_rows
    assert "합계 (주식 평가금액 + 현금)" in html_rows


def test_summary_heatmap_tiles_fill_rectangular_area_with_change_labels():
    tiles = _heatmap_tiles(_allocation_rows(_metrics()))

    assert "summary-heatmap-tile" in tiles
    assert "width:" in tiles
    assert "height:" in tiles
    assert "삼성전자" in tiles
    assert "+1.3%" in tiles
