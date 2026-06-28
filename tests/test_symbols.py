from portfolio.historical_holdings import normalize_holding_snapshots
from portfolio.symbols import (
    SIMPLE_HISTORICAL_COLUMNS,
    SIMPLE_PORTFOLIO_COLUMNS,
    build_input_preview,
    copy_previous_snapshot,
    csv_to_rows,
    event_rows_to_snapshots,
    parse_symbol_quantity_lines,
    preview_rows_to_historical_snapshots,
    preview_rows_to_holdings,
    resolve_symbol,
    rows_to_csv,
    snapshot_diff,
)


KRX_RECORDS = [
    {"ticker": "005930", "display_name": "삼성전자"},
    {"ticker": "000660", "display_name": "SK하이닉스"},
    {"ticker": "066570", "display_name": "LG전자"},
    {"ticker": "032830", "display_name": "삼성생명"},
]


def test_resolver_maps_korean_name_numeric_code_and_us_ticker():
    samsung = resolve_symbol("삼성전자", KRX_RECORDS)
    numeric = resolve_symbol("005930")
    prefixed = resolve_symbol("KR:005930")
    suffixed = resolve_symbol("005930.KS")
    us = resolve_symbol(" mu ")

    assert samsung.status == "resolved"
    assert samsung.ticker == "005930"
    assert samsung.display_name == "삼성전자"
    assert numeric.market == prefixed.market == suffixed.market == "KR"
    assert numeric.ticker == prefixed.ticker == suffixed.ticker == "005930"
    assert us.market == "US"
    assert us.currency == "USD"
    assert us.ticker == "MU"


def test_resolver_keeps_ambiguous_partial_matches_unresolved():
    ambiguous = resolve_symbol("삼성", KRX_RECORDS)
    missing = resolve_symbol("없는종목", KRX_RECORDS)

    assert ambiguous.status == "ambiguous"
    assert [candidate.ticker for candidate in ambiguous.candidates] == ["005930", "032830"]
    assert missing.status == "not_found"


def test_bulk_paste_and_simple_csv_preview_preserve_leading_zero():
    pasted = parse_symbol_quantity_lines("삼성전자 10\n005930,5\nMU 20\n")
    preview = build_input_preview(pasted, korea_listing_records=KRX_RECORDS)
    holdings = preview_rows_to_holdings(preview.rows)
    csv_rows = csv_to_rows(rows_to_csv([{"ticker_or_name": "005930", "quantity": "3"}], SIMPLE_PORTFOLIO_COLUMNS))

    assert preview.summary == {"total": 3, "ok": 3, "candidate_required": 0, "error": 0}
    assert [(row["market"], row["ticker"], row["quantity"]) for row in holdings] == [
        ("KR", "005930", 10.0),
        ("KR", "005930", 5.0),
        ("US", "MU", 20.0),
    ]
    assert csv_rows[0]["ticker_or_name"] == "005930"


def test_preview_reports_row_number_and_column_errors():
    preview = build_input_preview(
        [{"row_number": "7", "ticker_or_name": "MU", "quantity": "bad"}],
        korea_listing_records=KRX_RECORDS,
    )

    assert preview.summary["error"] == 1
    assert preview.errors == ["7행: quantity must be a number"]
    assert preview.rows[0]["row_number"] == 7


def test_simple_historical_csv_and_snapshot_helpers():
    rows = csv_to_rows(
        rows_to_csv(
            [
                {"as_of_date": "2026-06-01", "ticker_or_name": "삼성전자", "quantity": "100"},
                {"as_of_date": "2026-06-10", "ticker_or_name": "SK하이닉스", "quantity": "10"},
            ],
            SIMPLE_HISTORICAL_COLUMNS,
        )
    )
    preview = build_input_preview(rows, korea_listing_records=KRX_RECORDS, require_date=True)
    snapshots = preview_rows_to_historical_snapshots(preview.rows)

    normalized = normalize_holding_snapshots(snapshots)
    copied = copy_previous_snapshot(snapshots, "2026-06-20")
    diff = snapshot_diff([snapshots[0]], snapshots[1:])

    assert [row.ticker for row in normalized] == ["005930", "000660"]
    assert copied[0]["as_of_date"] == "2026-06-20"
    assert copied[0]["ticker"] == "000660"
    assert diff["removed"] == ["KR/005930"]
    assert diff["new"] == ["KR/000660"]


def test_event_rows_convert_to_snapshot_schedule_and_zero_ends_holding():
    event_text = "\n".join(
        [
            "2026-06-01 삼성전자 100",
            "2026-06-07 삼성전자 200",
            "2026-06-16 삼성전자 100",
            "2026-06-16 SK하이닉스 10",
            "2026-06-20 삼성전자 0",
        ]
    )
    raw_rows = parse_symbol_quantity_lines(event_text, with_date=True, quantity_name="quantity_after")
    preview = build_input_preview(raw_rows, korea_listing_records=KRX_RECORDS, require_date=True, quantity_field="quantity_after")
    snapshots = event_rows_to_snapshots(preview.rows)

    by_date = {}
    for row in snapshots:
        by_date.setdefault(row["as_of_date"], []).append(row["ticker"])

    assert by_date["2026-06-01"] == ["005930"]
    assert by_date["2026-06-16"] == ["000660", "005930"]
    assert by_date["2026-06-20"] == ["000660"]
    assert all(row["ticker"] != "005930" for row in snapshots if row["as_of_date"] == "2026-06-20")
