from types import SimpleNamespace

from portfolio.diagnostics import DiagnosticItem

from app.ui.status import (
    aggregate_price_statuses,
    build_price_log_rows,
    dirty_signature,
    infer_market_from_ticker,
    parse_bulk_input,
    prepare_quick_input_records,
    present_diagnostic,
    split_diagnostics,
)


def test_price_status_aggregation_and_log_rows():
    statuses = [
        SimpleNamespace(symbol="MU", market="US", status="updated", fetched_at="2026-06-23T03:00:00+00:00", message="ok"),
        SimpleNamespace(symbol="GOOG", market="US", status="stale", fetched_at=None, message="last price kept"),
        SimpleNamespace(symbol="005930", market="KR", status="cached", fetched_at="2026-06-23T02:59:00+00:00", message="cache"),
    ]
    summary = aggregate_price_statuses(statuses)

    assert summary.success == 2
    assert summary.stale == 1
    assert summary.failed == 0
    assert summary.has_issues

    rows = build_price_log_rows(
        statuses,
        [
            {"ticker": "MU", "display_name": "Micron", "provider": "alpha_vantage"},
            {"ticker": "GOOG", "display_name": "Alphabet", "provider": "alpha_vantage"},
            {"ticker": "005930", "display_name": "삼성전자", "provider": "finance_datareader"},
        ],
    )

    assert rows[0]["종목명"] == "Micron"
    assert rows[0]["조회 시각"] == "06-23 12:00 KST"
    assert rows[1]["상태"] == "이전 가격"
    assert rows[2]["provider"] == "finance_datareader"


def test_market_inference_and_quick_record_preparation_preserves_korea_code():
    assert infer_market_from_ticker("005930") == "KR"
    assert infer_market_from_ticker("KR:005930") == "KR"
    assert infer_market_from_ticker("005930.KS") == "KR"
    assert infer_market_from_ticker("mu") == "US"

    records = prepare_quick_input_records([{"ticker": " 005930 ", "quantity": 10}, {"ticker": " mu ", "quantity": 20}])

    assert records == [
        {"market": "KR", "ticker": "005930", "quantity": 10},
        {"market": "US", "ticker": "MU", "quantity": 20},
    ]


def test_bulk_input_parsing_validation_and_duplicate_policy():
    result = parse_bulk_input("005930,10\nMU,20\nmu,25\nBAD LINE EXTRA\n")

    assert {tuple(row[key] for key in ("market", "ticker")) for row in result.rows} == {("KR", "005930"), ("US", "MU")}
    assert next(row for row in result.rows if row["ticker"] == "MU")["quantity"] == 25
    assert result.errors == ["4행: ticker와 quantity를 입력하세요"]


def test_dirty_signature_is_stable_and_sensitive_to_portfolio_changes():
    base = {"portfolio_name": "main", "holdings_rows": [{"ticker": "MU", "quantity": 1}], "cash_krw": 0}
    same = {"cash_krw": 0, "holdings_rows": [{"quantity": 1, "ticker": "MU"}], "portfolio_name": "main"}
    changed = {"portfolio_name": "main", "holdings_rows": [{"ticker": "MU", "quantity": 2}], "cash_krw": 0}

    assert dirty_signature(base) == dirty_signature(same)
    assert dirty_signature(base) != dirty_signature(changed)


def test_diagnostic_presentation_keeps_quote_status_short_and_splits_details():
    quote_item = DiagnosticItem(
        key="quote_freshness",
        label="가격 상태",
        value="정상 5 / stale 0 / 실패 0",
        level="ok",
        message="세부 가격 상태입니다.",
    )
    detail_item = DiagnosticItem(
        key="gain_contributors",
        label="오늘 상승 기여 상위",
        value="MU",
        level="info",
        message="상승 기여 종목입니다.",
    )

    quote_presentation = present_diagnostic(quote_item, priced_count=5, holdings_count=5)
    detail_presentation = present_diagnostic(detail_item)
    primary, details = split_diagnostics([quote_presentation, detail_presentation])

    assert quote_presentation.value == "5/5 정상"
    assert quote_presentation.severity_label == "양호"
    assert "정상 5 / stale 0 / 실패 0" in quote_presentation.help_text
    assert [item.key for item in primary] == ["quote_freshness"]
    assert [item.key for item in details] == ["gain_contributors"]
