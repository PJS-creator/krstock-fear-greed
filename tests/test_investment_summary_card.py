from portfolio.holdings import build_portfolio_metrics
from app.ui.investment_summary_card import (
    _allocation_rows,
    _cash_allocation_row,
    _heatmap_tiles,
    _holding_allocation_rows,
    _holding_table_rows,
    _market_index_strip,
    _market_warning_strip,
    _mobile_holding_summary_table,
    _sparkline_html,
    render_investment_summary_card,
)
from app.ui.theme import get_active_theme, get_app_theme


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
                "intraday_prices": [79000, 79300, 79200, 79800, 80000],
            },
            {
                "market": "US",
                "ticker": "MU",
                "display_name": "Micron",
                "quantity": 2,
                "avg_price": 100,
                "current_price": 120,
                "previous_close": 125,
                "intraday_prices": [125, 124, 122, 121, 120],
            },
        ],
        cash_krw=1_000_000,
        cash_usd=100,
        usd_krw=1400,
    )


def _many_holding_metrics():
    return build_portfolio_metrics(
        [
            {"market": "KR", "ticker": "000001", "display_name": "Alpha", "quantity": 1, "avg_price": 80, "current_price": 100, "previous_close": 95},
            {"market": "KR", "ticker": "000002", "display_name": "Bravo", "quantity": 1, "avg_price": 70, "current_price": 80, "previous_close": 82},
            {"market": "KR", "ticker": "000003", "display_name": "Charlie", "quantity": 1, "avg_price": 55, "current_price": 60, "previous_close": 60},
            {"market": "KR", "ticker": "000004", "display_name": "Delta", "quantity": 1, "avg_price": 35, "current_price": 40, "previous_close": 38},
            {"market": "KR", "ticker": "000005", "display_name": "Echo", "quantity": 1, "avg_price": 15, "current_price": 20, "previous_close": 21},
        ],
        cash_krw=0,
        cash_usd=0,
        usd_krw=1400,
    )


def test_summary_allocation_separates_cash_and_prefers_korean_company_name():
    rows = _allocation_rows(_metrics())
    cash_row = _cash_allocation_row(_metrics())

    assert any(row["label"] == "삼성전자" for row in rows)
    assert all(row["label"] != "현금" for row in rows)
    assert cash_row is not None
    assert cash_row["label"] == "현금"
    assert round(sum(row["weight"] for row in rows) + cash_row["weight"], 6) == 1


def test_summary_allocation_detail_removes_currency_badge_text_and_shows_usd_conversion():
    rows = {row["label"]: row for row in _allocation_rows(_metrics())}

    assert rows["삼성전자"]["allocation_detail"] == "평가액 800,000원"
    assert rows["MU · Micron"]["allocation_detail"] == "달러 240$ • 환산 336,000원"


def test_summary_asset_dots_use_daily_movement_colors():
    tokens = get_active_theme().tokens()
    rows = {row["label"]: row for row in _allocation_rows(_metrics())}

    assert rows["삼성전자"]["color"] == tokens["profit"]
    assert rows["MU · Micron"]["color"] == tokens["loss"]


def test_summary_allocation_collapses_more_than_three_holdings_with_count_label():
    rows = _allocation_rows(_many_holding_metrics())

    assert [row["label"] for row in rows] == ["Alpha", "Bravo", "Charlie", "그 외 2종목"]
    assert rows[-1]["detail"] == "2개 종목 합산"
    assert rows[-1]["kind"] == "other"
    assert round(rows[-1]["weight"], 6) == round((40 + 20) / (100 + 80 + 60 + 40 + 20), 6)


def test_summary_heatmap_rows_keep_every_holding_unaggregated():
    rows = _holding_allocation_rows(_many_holding_metrics())
    tiles = _heatmap_tiles(rows)

    assert [row["label"] for row in rows] == ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    assert "Delta" in tiles
    assert "Echo" in tiles
    assert "그 외" not in tiles
    assert "기타" not in tiles


def test_summary_holding_table_restores_detailed_columns():
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
    assert "summary-section-investment" in html_rows
    assert "summary-section-cash" in html_rows
    assert "<tr class='summary-section-row summary-section-investment'><td colspan='8'><span>투자</span></td></tr>" in html_rows
    assert "<tr class='summary-section-row summary-section-cash'><td colspan='8'><span>현금</span></td></tr>" in html_rows
    assert "summary-currency-krw" in html_rows
    assert "summary-currency-usd" in html_rows
    assert "summary-name-inner" in html_rows
    assert "원화 현금" in html_rows
    assert "달러 현금" in html_rows
    assert "summary-price-group" in html_rows
    assert "summary-price-cell" in html_rows
    assert "₩72,300" in html_rows
    assert "723,000원" in html_rows
    assert "$100.00" in html_rows
    assert "$120.00" in html_rows
    assert "280,000원" in html_rows
    assert "800,000" in html_rows
    assert "-$5.00 (-4.0%)" in html_rows
    assert "summary-current-price summary-down" in html_rows
    assert "summary-pnl-stack" in html_rows
    assert "%" in html_rows
    assert "합계 (주식 평가금액 + 현금)" in html_rows
    assert "당일 흐름" not in html_rows
    assert "summary-sparkline" in html_rows
    assert "IRR" not in html_rows


def test_mobile_holding_summary_table_includes_requested_compact_columns():
    table = _mobile_holding_summary_table(_metrics())

    assert "summary-mobile-holdings" in table
    assert "summary-mobile-holding-table" in table
    for label in ("종목명", "수량", "평균단가", "현재가", "자산비중"):
        assert f"<th>{label}</th>" in table
    assert "삼성전자" in table
    assert "Micron" in table
    assert "summary-currency-badge" not in table
    assert "summary-currency-usd" not in table
    assert "summary-currency-krw" not in table
    assert "USD" not in table
    assert "KRW" not in table
    assert "$120" in table
    assert "$120.00" not in table
    assert "35.1%" in table
    assert "35.15%" not in table
    assert "summary-mobile-holding-list" not in table
    assert "summary-mobile-holding-cell" not in table
    assert "매입금액" not in table
    assert "평가금액" not in table


def test_investment_summary_keeps_detailed_holding_table_below_mobile_summary(monkeypatch):
    rendered: list[str] = []

    def capture_markdown(body, **_kwargs):
        rendered.append(str(body))

    monkeypatch.setattr("app.ui.investment_summary_card.st.markdown", capture_markdown)

    render_investment_summary_card(_metrics(), portfolio_name="main")
    html = "\n".join(rendered)

    assert "summary-mobile-holding-table" in html
    assert '<div class="summary-table-wrap">' in html
    assert "<h3>보유 종목</h3>" in html
    assert "<div class=\"summary-asset-group-head\"><span>투자</span>" in html
    assert "<div class=\"summary-asset-group-head\"><span>현금</span>" in html
    assert "summary-asset-currency-split" not in html
    assert "summary-dot-rule" in html
    assert "summary-dot-rule-up" in html
    assert "summary-dot-rule-down" in html
    assert "summary-dot-rule-flat" in html
    assert "보합·미산정" in html
    assert ".summary-name-inner" in html
    assert "width: 100%;" in html
    assert ".summary-name {\n            min-width: 0;\n            display: flex;" not in html
    assert "display: table-cell !important;" in html
    assert ".summary-section-row td {\n            display: flex;" not in html
    assert "KRW" in html
    assert "USD" in html
    assert "원화 현금" in html
    assert "달러 현금" in html
    assert "main · 총자산 기준" not in html
    assert "summary-price-heading" in html
    assert "<strong>평균단가</strong><span>(매입금액)</span>" in html
    assert "<strong>현재가</strong><span>(평가금액)</span>" in html
    assert "<th class=\"summary-sparkline-th\">당일 흐름</th>" in html
    assert "summary-pnl-heading" in html
    assert "<strong>누적수익률</strong>" in html
    assert "<span>(평가손익)</span>" in html
    assert "<th>IRR</th>" in html
    assert "table-layout: fixed;" in html
    assert "font-size: clamp(0.68rem, 0.63vw, 0.79rem);" in html
    assert "border: 0;" in html
    assert ".summary-current-price.summary-up" in html
    assert ".summary-pnl-delta" in html
    assert ".summary-heatmap-card {\n            padding: 18px;\n            min-height: 360px;" in html
    assert ".summary-heatmap-tile:hover" in html
    assert "filter: brightness(1.15) saturate(1.08);" in html
    assert "transform: translateZ(0) scale(1.1);" in html
    assert "summary-heatmap-small:hover" in html
    assert "summary-index-strip" in html
    assert "주요 지수변동" in html
    assert "summary-warning-strip" in html
    assert "매수&매도 경고" in html
    assert "Bollinger Band(180, 2.0)" in html
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in html
    assert "overflow-x: hidden;" in html
    assert "color-mix(in srgb, var(--token-overlay) 36%, transparent)" in html
    for col_class in (
        "summary-col-name",
        "summary-col-qty",
        "summary-col-price-group",
        "summary-col-spark",
        "summary-col-day",
        "summary-col-pnl",
        "summary-col-irr",
        "summary-col-weight",
    ):
        assert col_class in html
    assert ".summary-table-wrap {\n                display: none;" not in html


def test_market_index_strip_renders_requested_compact_row():
    rows = [
        {
            "label": "코스피",
            "symbol": "^KS11",
            "value": 7200.0,
            "change_pct": 0.008,
            "status": "updated",
        },
        {
            "label": "금 지수",
            "symbol": "XAU/USD",
            "value": 2365.4,
            "change_pct": 0.006,
            "status": "updated",
        },
    ]
    html = _market_index_strip(rows)

    assert "summary-index-strip" in html
    assert "summary-index-quote" in html
    assert "코스피" in html
    assert "7,200" in html
    assert "(+0.8%)" in html
    assert "금 지수" in html
    assert "XAU/USD" in html
    assert "summary-index-cell-gold" in html
    assert "신규" in html


def test_market_warning_strip_renders_buy_and_sell_block_cards_without_rule_box():
    rows = [
        {
            "label": "KOSPI 200 선물",
            "symbol": "KOS",
            "status": "buy_blocked",
            "trigger": "상단 이탈",
            "value": 385.2,
            "moving_average": 380.0,
            "upper_band": 384.0,
            "lower_band": 360.0,
        },
        {
            "label": "NASDAQ 100 선물",
            "symbol": "NQ=F",
            "status": "sell_blocked",
            "trigger": "하단 이탈",
            "value": 19120.0,
            "moving_average": 19300.0,
            "upper_band": 19600.0,
            "lower_band": 19200.0,
        },
    ]
    html = _market_warning_strip(rows)

    assert "summary-warning-strip" in html
    assert "매수&매도 경고" in html
    assert "KOSPI 200 선물" in html
    assert "NASDAQ 100 선물" in html
    assert "매수 금지" in html
    assert "매도 금지" in html
    assert "상단 이탈" in html
    assert "하단 이탈" in html
    assert "판정 방식" not in html


def test_summary_heatmap_tiles_fill_rectangular_area_with_change_labels_and_exclude_cash():
    tiles = _heatmap_tiles(_allocation_rows(_metrics()))

    assert "summary-heatmap-tile" in tiles
    assert "width:" in tiles
    assert "height:" in tiles
    assert "삼성전자" in tiles
    assert "+1.3%" in tiles
    assert "현금" not in tiles


def test_summary_heatmap_small_tiles_keep_labels_and_hover_affordance():
    tiles = _heatmap_tiles(
        [
            {
                "label": "Large",
                "value_krw": 999,
                "weight": 0.999,
                "heat_color": "#E11D48",
                "day_change_pct": 0.01,
            },
            {
                "label": "Tiny",
                "value_krw": 1,
                "weight": 0.001,
                "heat_color": "#0284C7",
                "day_change_pct": -0.012,
            },
        ]
    )

    assert "Tiny" in tiles
    assert "-1.2%" in tiles
    assert "summary-heatmap-small" in tiles
    assert "비중 0.10%" in tiles


def test_summary_heatmap_empty_state_is_safe():
    tiles = _heatmap_tiles([])

    assert "summary-heatmap-empty" in tiles
    assert "보유자산 없음" in tiles


def test_light_theme_separates_heatmap_tile_borders_from_outer_border():
    variables = get_app_theme("light").css_variables()

    assert variables["summary-heatmap-border"] != variables["summary-heatmap-tile-border"]
    assert "255, 255, 255" in variables["summary-heatmap-tile-border"]


def test_dark_theme_heatmap_border_is_not_pure_black():
    variables = get_app_theme("dark").css_variables()

    assert variables["summary-heatmap-bg"] == "#0F172A"
    assert variables["summary-heatmap-border"] == "#263244"
    assert variables["summary-heatmap-tile-border"] == "#1E293B"


def test_summary_sparkline_uses_intraday_prices_and_handles_missing_data():
    chart = _sparkline_html({"intraday_prices": [10, 12, 11, 13]})
    empty = _sparkline_html({})

    assert "summary-sparkline-up" in chart
    assert "<polyline" in chart
    assert "당일 분봉 4개" in chart
    assert "summary-sparkline-empty" in empty
