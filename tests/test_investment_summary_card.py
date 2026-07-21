from portfolio.holdings import build_portfolio_metrics
from app.ui.investment_summary_card import (
    _allocation_rows,
    _cash_allocation_row,
    _desktop_sector_partition,
    _desktop_sector_rows,
    _display_sector_groups,
    _heatmap_tiles,
    _holding_allocation_rows,
    _holding_sector,
    _holding_table_rows,
    _market_index_strip,
    _meta_strategy_panel,
    _market_warning_strip,
    _mobile_heatmap,
    _mobile_other_row,
    _mobile_heatmap_partition,
    _mobile_holding_summary_table,
    _sector_group_layout,
    _sector_group_html,
    _sector_heatmap,
    _sector_member_layout,
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


def test_summary_heatmap_rows_include_market_and_sector_metadata():
    rows = {row["label"]: row for row in _holding_allocation_rows(_metrics())}

    assert rows["삼성전자"]["market_code"] == "KR"
    assert rows["삼성전자"]["sector"] == "반도체·전자"
    assert rows["MU · Micron"]["market_code"] == "US"
    assert rows["MU · Micron"]["sector"] == "기타"


def test_desktop_heatmap_groups_sectors_and_keeps_market_codes():
    html = _sector_heatmap(_holding_allocation_rows(_metrics()))

    assert "summary-sector-heatmap" in html
    assert "summary-heatmap-desktop" in html
    assert "반도체·전자" in html
    assert "기타" in html
    assert "삼성전자" in html
    assert "(KR)" in html
    assert "(US)" in html
    assert "면적 표시 원칙" not in html
    assert "summary-sector-group-major" in html


def test_desktop_sector_groups_use_value_weighted_nested_areas():
    groups = [
        {"label": "A", "rows": [], "value_krw": 50, "weight": 0.50},
        {"label": "B", "rows": [], "value_krw": 35, "weight": 0.35},
        {"label": "그 외", "rows": [], "value_krw": 15, "weight": 0.15},
    ]

    layout = _sector_group_layout(groups)
    areas = [float(group["width"]) * float(group["height"]) for group in layout]
    total_area = sum(areas)

    assert [round(area / total_area, 2) for area in areas] == [0.50, 0.35, 0.15]
    assert round(float(layout[0]["height"]), 6) == 100.0
    assert round(float(layout[1]["width"]), 6) == round(float(layout[2]["width"]), 6)
    assert round(float(layout[1]["height"]) + float(layout[2]["height"]), 6) == 100.0


def test_desktop_sector_layout_preserves_minimum_area_for_readable_other_group():
    groups = [
        {"label": "A", "rows": [], "value_krw": 60, "weight": 0.60},
        {"label": "B", "rows": [], "value_krw": 37, "weight": 0.37},
        {"label": "그 외", "rows": [], "value_krw": 3, "weight": 0.03},
    ]

    layout = _sector_group_layout(groups)
    areas = [float(group["width"]) * float(group["height"]) for group in layout]
    total_area = sum(areas)

    assert round(areas[2] / total_area, 2) == 0.12
    assert [group["value_krw"] for group in layout] == [60, 37, 3]
    assert all("actual_value_krw" not in group for group in layout)


def test_short_desktop_sector_uses_inline_compact_member_layout():
    heat_color = get_active_theme().tokens()["profit"]
    group = {
        "label": "그 외",
        "rows": [
            {"label": "HD한국조선해양", "compact_label": "009540", "value_krw": 2, "weight": 0.02, "day_change_pct": 0.01, "market_code": "KR", "heat_color": heat_color},
            {"label": "한국금융지주", "compact_label": "071050", "value_krw": 1, "weight": 0.01, "day_change_pct": -0.01, "market_code": "KR", "heat_color": heat_color},
        ],
        "value_krw": 3,
        "weight": 0.03,
        "x": 45,
        "y": 78,
        "width": 55,
        "height": 22,
    }

    html = _sector_group_html(group)

    assert "summary-sector-group-compact" in html
    assert "HD한국조선해양" in html
    assert "한국금융지주" in html
    assert "+1.0%" in html
    assert "-1.0%" in html


def test_minor_sectors_merge_into_other_but_keep_individual_holdings():
    heat_color = get_active_theme().tokens()["profit"]
    rows = [
        {
            "label": label,
            "compact_label": label,
            "sector": sector,
            "value_krw": value,
            "weight": weight,
            "market_code": "US",
            "day_change_pct": 0.01,
            "heat_color": heat_color,
        }
        for label, sector, value, weight in [
            ("BIO", "바이오", 50, 0.50),
            ("CHIP", "반도체", 35, 0.35),
            ("GOLD", "귀금속", 8, 0.08),
            ("SHIP", "조선", 4, 0.04),
            ("FIN", "금융", 3, 0.03),
        ]
    ]

    groups = _display_sector_groups(rows)
    html = _sector_heatmap(rows)

    assert [group["label"] for group in groups] == ["바이오", "반도체", "그 외"]
    assert [row["label"] for row in groups[2]["rows"]] == ["GOLD", "SHIP", "FIN"]
    assert groups[2]["value_krw"] == 15
    assert round(groups[2]["weight"], 6) == 0.15
    assert "<strong>그 외</strong>" in html
    assert all(label in html for label in ("GOLD", "SHIP", "FIN"))


def test_independent_sectors_reorder_when_values_change():
    rows = [
        {"label": "A1", "sector": "A", "value_krw": 30, "weight": 0.30},
        {"label": "B1", "sector": "B", "value_krw": 10, "weight": 0.10},
        {"label": "C1", "sector": "C", "value_krw": 55, "weight": 0.55},
        {"label": "D1", "sector": "D", "value_krw": 5, "weight": 0.05},
    ]

    groups = _display_sector_groups(rows)

    assert [group["label"] for group in groups] == ["C", "A", "그 외"]
    assert [row["label"] for row in groups[2]["rows"]] == ["B1", "D1"]


def test_three_member_sector_uses_value_proportional_non_uniform_tiles():
    rows = [
        {"label": "삼성전자", "value_krw": 50},
        {"label": "삼성전자우", "value_krw": 30},
        {"label": "SK하이닉스", "value_krw": 20},
    ]

    layout = _sector_member_layout(rows, group_width=48.0, group_height=100.0)
    areas = [float(row["width"]) * float(row["height"]) for row in layout]
    total_area = sum(areas)

    assert round(float(layout[0]["height"]), 6) == 100.0
    assert round(float(layout[1]["x"]), 6) == round(float(layout[2]["x"]), 6)
    assert round(float(layout[1]["height"]) + float(layout[2]["height"]), 6) == 100.0
    assert [round(area / total_area, 2) for area in areas] == [0.50, 0.30, 0.20]


def test_desktop_sector_groups_small_members_into_weighted_other_tile():
    rows = [
        {
            "label": f"Holding {index}",
            "compact_label": f"T{index:02d}",
            "sector": "바이오·헬스케어",
            "value_krw": value,
            "weight": weight,
            "day_change_pct": 0.01 if index % 2 else -0.01,
            "market_code": "US",
            "heat_color": get_active_theme().tokens()["profit" if index % 2 else "loss"],
        }
        for index, (value, weight) in enumerate(
            [(36, 0.36), (24, 0.24), (14, 0.14), (9, 0.09), (6, 0.06), (4, 0.04), (2, 0.02), (1, 0.01)],
            start=1,
        )
    ]
    group = {
        "label": "바이오·헬스케어",
        "rows": rows,
        "value_krw": 96,
        "weight": 0.96,
    }

    individual, grouped = _desktop_sector_partition(rows)
    display_rows = _desktop_sector_rows(group)
    html = _sector_heatmap(rows)

    assert [row["compact_label"] for row in individual] == ["T01", "T02", "T03", "T04", "T05", "T06"]
    assert [row["compact_label"] for row in grouped] == ["T07", "T08"]
    assert display_rows[-1]["label"] == "기타 2종목"
    assert display_rows[-1]["value_krw"] == 3
    assert round(display_rows[-1]["weight"], 6) == 0.03
    assert display_rows[-1]["market_code"] == "US"
    assert "summary-sector-tile-aggregate" in html
    assert "기타 2종목" in html
    assert "포함 종목: T07, T08" in html
    assert "8종목" in html


def test_dense_healthcare_sector_uses_readable_squarified_tiles():
    values = [36, 24, 14, 9, 6, 4, 3]
    rows = [
        {"label": f"BIO{index}", "value_krw": value}
        for index, value in enumerate(values, start=1)
    ]
    group_width = 55.0
    group_height = 100.0

    layout = _sector_member_layout(rows, group_width=group_width, group_height=group_height)
    virtual_width = group_width * 10.0
    virtual_height = group_height * 2.56 - 30.0
    aspect_ratios = []
    for tile in layout:
        tile_width = float(tile["width"]) / 100.0 * virtual_width
        tile_height = float(tile["height"]) / 100.0 * virtual_height
        aspect_ratios.append(max(tile_width / tile_height, tile_height / tile_width))

    areas = [float(tile["width"]) * float(tile["height"]) for tile in layout]
    total_area = sum(areas)
    assert all(
        abs(area / total_area - value / sum(values)) < 1e-9
        for area, value in zip(areas, values, strict=True)
    )
    assert max(aspect_ratios) < 2.0


def test_mobile_heatmap_groups_small_positions_into_one_weighted_other_tile():
    rows = [
        {
            "label": f"Holding {index}",
            "compact_label": f"T{index:02d}",
            "value_krw": value,
            "weight": weight,
            "day_change_pct": 0.01 if index % 2 else -0.01,
            "market_code": "US",
            "heat_color": get_active_theme().tokens()["profit" if index % 2 else "loss"],
        }
        for index, (value, weight) in enumerate(
            [(40, 0.40), (25, 0.25), (15, 0.15), (8, 0.08), (3, 0.03), (2, 0.02), (1, 0.01)],
            start=1,
        )
    ]

    individual, grouped = _mobile_heatmap_partition(rows)
    other = _mobile_other_row(grouped)
    html = _mobile_heatmap(rows)

    assert [row["compact_label"] for row in individual] == ["T01", "T02", "T03", "T04"]
    assert [row["compact_label"] for row in grouped] == ["T05", "T06", "T07"]
    assert other is not None
    assert other["label"] == "그 외 3종목"
    assert other["value_krw"] == 6
    assert round(other["weight"], 6) == 0.06
    assert "summary-mobile-heatmap-major" in html
    assert "summary-mobile-compact-grid" not in html
    assert html.count("summary-heatmap-tile") == 5
    assert "그 외 3종목" in html
    assert "포함 종목: T05, T06, T07" in html


def test_mobile_heatmap_limits_total_tiles_even_when_many_positions_exceed_threshold():
    rows = [
        {
            "label": f"Holding {index}",
            "compact_label": f"T{index:02d}",
            "value_krw": 5,
            "weight": 0.05,
            "day_change_pct": 0.01,
            "market_code": "US",
            "heat_color": get_active_theme().tokens()["profit"],
        }
        for index in range(1, 13)
    ]

    individual, grouped = _mobile_heatmap_partition(rows)
    html = _mobile_heatmap(rows)

    assert len(individual) == 7
    assert len(grouped) == 5
    assert html.count("summary-heatmap-tile") == 8
    assert "그 외 5종목" in html


def test_current_portfolio_tickers_cover_six_requested_sector_groups():
    expected = {
        "QURE": "바이오·헬스케어",
        "CGEM": "바이오·헬스케어",
        "CMPS": "바이오·헬스케어",
        "AVR": "바이오·헬스케어",
        "CCCC": "바이오·헬스케어",
        "GHRS": "바이오·헬스케어",
        "CTMX": "바이오·헬스케어",
        "VOR": "바이오·헬스케어",
        "PSNL": "바이오·헬스케어",
        "005930": "반도체·전자",
        "005935": "반도체·전자",
        "000660": "반도체·전자",
        "AYA": "귀금속·광업",
        "EXK": "귀금속·광업",
        "MAKO": "귀금속·광업",
        "009540": "조선·산업재",
        "071050": "금융",
        "239890": "디스플레이 소재",
    }

    assert {ticker: _holding_sector({"ticker": ticker}) for ticker in expected} == expected


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
    assert ".summary-heatmap-card {\n            padding: 18px;\n            min-height: 0;" in html
    assert "summary-sector-heatmap" in html
    assert "summary-heatmap-mobile" in html
    assert "height: clamp(276px, 22vw, 310px);" in html
    assert "summary-mobile-compact-grid" not in html
    assert "aspect-ratio: 4 / 3;" in html
    assert ".summary-sector-heatmap { display: none; }" in html
    assert ".summary-heatmap-mobile { display: block; }" in html
    assert "면적 표시 원칙" not in html
    assert ".summary-heatmap-tile:hover" in html
    assert "filter: brightness(1.15) saturate(1.08);" in html
    assert "transform: translateZ(0) scale(1.1);" in html
    assert "summary-heatmap-small:hover" in html
    assert "summary-index-strip" in html
    assert "주요 지수변동" in html
    assert "summary-warning-strip" in html
    assert "summary-meta-strategy" in html
    assert "시장구간" in html
    assert "활성화 전략" in html
    assert "적용티커" in html
    assert "매수&매도 경고" not in html
    assert "Bollinger Band(180, 2.0)" not in html
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in html
    assert "overflow-x: hidden;" in html
    assert '<span class="flat">보합</span>' in html
    assert ".summary-sector-tile-aggregate" in html
    assert "box-shadow: inset 0 0 0 1px var(--summary-heatmap-tile-border);" in html
    assert ".summary-warning-card {\n            min-width: 0;\n            min-height: 41px;" in html
    assert "border: 1px solid var(--app-border);" in html
    assert "font-size: clamp(0.68rem, 2.7vw, 0.74rem);" in html
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
    assert html.count("class='summary-index-cell'") == 2
    assert "summary-index-cell-gold" not in html
    assert "신규" not in html


def test_market_warning_strip_renders_only_index_names_and_status_badges():
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
            "source": "korea_investment",
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
            "source": "yahoo-chart",
        },
    ]
    html = _market_warning_strip(rows)

    assert "summary-warning-strip" in html
    assert "KOSPI 200 선물" in html
    assert "NASDAQ 100 선물" in html
    assert "매수 금지" in html
    assert "매도 금지" in html
    assert html.count("class='summary-warning-card ") == 2
    for removed_text in (
        "매수&매도 경고",
        "상단 이탈",
        "하단 이탈",
        "KIS 60분봉",
        "Yahoo 60분봉",
        "NQ=F",
        "385.2",
        "19120",
    ):
        assert removed_text not in html
    assert "summary-warning-mini" not in html
    assert "summary-warning-trigger" not in html
    assert "summary-warning-detail" not in html


def test_market_warning_strip_shows_kis_configuration_required_without_failed_copy():
    rows = [
        {
            "label": "KOSPI 200 선물",
            "symbol": "KOS",
            "status": "configuration_required",
            "trigger": "KIS 설정 필요",
            "value": None,
            "moving_average": None,
            "upper_band": None,
            "lower_band": None,
            "source": "korea_investment",
            "error_message": "KIS_KOSPI200_FUTURES_SYMBOL 설정이 필요합니다.",
        },
    ]
    html = _market_warning_strip(rows)

    assert "KOSPI 200 선물" in html
    assert "설정 필요" in html
    assert "KIS 60분봉" not in html
    assert "KIS 선물 종목코드를 설정하세요" not in html
    assert "KIS_KOSPI200_FUTURES_SYMBOL" not in html


def test_market_warning_strip_keeps_required_kis_failure_on_kis_source():
    rows = [
        {
            "label": "KOSPI 200 선물",
            "symbol": "KOS",
            "status": "failed",
            "trigger": "KIS 조회 실패",
            "value": None,
            "moving_average": None,
            "upper_band": None,
            "lower_band": None,
            "source": "korea_investment",
            "error_message": "KIS temporary failure",
        },
    ]
    html = _market_warning_strip(rows)

    assert "KOSPI 200 선물" in html
    assert "조회 실패" in html
    assert "KIS 60분봉" not in html
    assert "KIS 조회 실패" not in html
    assert "KIS temporary failure" not in html
    assert "Yahoo 60분봉" not in html


def test_meta_strategy_panel_shows_requested_three_results_and_diagnostics():
    html = _meta_strategy_panel(
        {
            "status": "updated",
            "market_regime": "mixed",
            "market_regime_label": "혼재장",
            "active_strategy": "comparison3",
            "active_strategy_label": "비교3 · RSI 전환",
            "applied_ticker": "QLD",
            "qqq_as_of_date": "2026-07-20",
            "liquidity_as_of_date": "2026-07-17",
            "liquidity_percentile": 61.25,
            "trend200": "UP",
            "recovery": False,
        }
    )

    assert "summary-meta-strategy" in html
    assert "시장구간" in html
    assert "혼재장" in html
    assert "활성화 전략" in html
    assert "비교3 · RSI 전환" in html
    assert "적용티커" in html
    assert "QLD" in html
    assert "P 61.2" in html
    assert "추세 UP" in html
    assert "자동 매매가 아닙니다" in html


def test_meta_strategy_panel_has_safe_pending_state_before_refresh():
    html = _meta_strategy_panel(None)

    assert "갱신 대기" in html
    assert "가격·환율 갱신 시" in html
    assert "<strong>-</strong>" in html


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
