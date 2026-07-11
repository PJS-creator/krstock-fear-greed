import pytest

from portfolio.transactions import (
    build_transaction_preview,
    normalize_trade_input,
    parse_transaction_lines,
    preview_rows_to_transactions,
    transaction_cashflow_rows,
    transactions_to_holdings,
    validate_trade_input,
)


KRX_RECORDS = [
    {"ticker": "005930", "display_name": "삼성전자"},
    {"ticker": "000660", "display_name": "SK하이닉스"},
]


def test_transactions_aggregate_to_current_holdings_with_weighted_average_cost():
    transactions = [
        {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 100, "quantity": 10, "occurred_at": "2026-01-01"},
        {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 140, "quantity": 10, "occurred_at": "2026-02-01"},
        {"transaction_type": "매도", "ticker_or_name": "MU", "unit_price": 150, "quantity": 5, "occurred_at": "2026-03-01"},
    ]

    holdings = transactions_to_holdings(transactions)

    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "MU"
    assert holdings[0]["quantity"] == 15.0
    assert holdings[0]["avg_price"] == 120.0


def test_sell_more_than_current_holdings_is_rejected():
    transactions = [
        {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 100, "quantity": 1, "occurred_at": "2026-01-01"},
        {"transaction_type": "매도", "ticker_or_name": "MU", "unit_price": 120, "quantity": 2, "occurred_at": "2026-01-02"},
    ]

    with pytest.raises(ValueError, match="sell quantity exceeds"):
        transactions_to_holdings(transactions)


def test_transaction_preview_resolves_korean_names_and_preserves_required_fields():
    preview = build_transaction_preview(
        [{"transaction_type": "매입", "ticker_or_name": "삼성전자", "unit_price": "72300", "quantity": "200", "fee": "100", "tax": "50", "occurred_at": "2026-04-13"}],
        korea_listing_records=KRX_RECORDS,
    )
    transactions = preview_rows_to_transactions(preview.rows)

    assert preview.summary == {"total": 1, "ok": 1, "candidate_required": 0, "error": 0}
    assert transactions[0]["transaction_type"] == "buy"
    assert transactions[0]["ticker"] == "005930"
    assert transactions[0]["unit_price"] == 72300.0
    assert transactions[0]["quantity"] == 200.0
    assert transactions[0]["fee"] == 100.0
    assert transactions[0]["tax"] == 50.0
    assert transactions[0]["occurred_at"] == "2026-04-13"


def test_transaction_preview_prefers_explicit_ticker_and_preserves_display_name():
    preview = build_transaction_preview(
        [
            {
                "transaction_type": "매입",
                "ticker_or_name": "삼성전자우선주",
                "ticker": "005935",
                "market": "KR",
                "currency": "KRW",
                "display_name": "삼성전자우선주",
                "unit_price": "160904",
                "quantity": "200",
                "occurred_at": "2026-04-28",
            }
        ],
        korea_listing_records=[],
    )

    assert preview.summary == {"total": 1, "ok": 1, "candidate_required": 0, "error": 0}
    assert preview.rows[0]["ticker"] == "005935"
    assert preview.rows[0]["display_name"] == "삼성전자우선주"


def test_standard_trade_form_input_normalizes_to_legacy_transaction_shape():
    row = normalize_trade_input(
        {
            "transaction_type": "매입",
            "market": "US",
            "currency": "시장 기준 자동",
            "ticker_or_name": "googl",
            "unit_price": 120,
            "quantity": 2,
            "fee": 1.25,
            "tax": 0,
            "occurred_at": "2026-04-13",
            "note": "first buy",
        }
    )

    assert row["transaction_type"] == "buy"
    assert row["ticker"] == "googl"
    assert row["market"] == "US"
    assert row["currency"] == "USD"
    assert "ticker_or_name" not in row
    assert row["unit_price"] == 120.0
    assert row["quantity"] == 2.0
    assert row["fee"] == 1.25
    assert row["tax"] == 0.0
    assert row["occurred_at"] == "2026-04-13"
    assert row["note"] == "first buy"


def test_standard_trade_form_validation_rejects_invalid_values_before_preview():
    errors = validate_trade_input(
        {
            "transaction_type": "매입",
            "market": "자동감지",
            "currency": "시장 기준 자동",
            "ticker_or_name": "",
            "unit_price": 0,
            "quantity": 0,
            "fee": -1,
            "tax": 0,
            "occurred_at": "2026-04-13",
        }
    )

    assert errors == ["종목명 또는 티커를 입력하세요."]

    assert validate_trade_input(
        {
            "transaction_type": "매입",
            "market": "US",
            "currency": "USD",
            "ticker_or_name": "MU",
            "unit_price": 0,
            "quantity": 1,
            "occurred_at": "2026-04-13",
        }
    ) == ["unit_price must be positive"]

    assert validate_trade_input(
        {
            "transaction_type": "매입",
            "market": "US",
            "currency": "USD",
            "ticker_or_name": "MU",
            "unit_price": 10,
            "quantity": 0,
            "occurred_at": "2026-04-13",
        }
    ) == ["quantity must be positive"]

    assert validate_trade_input(
        {
            "transaction_type": "매입",
            "market": "US",
            "currency": "USD",
            "ticker_or_name": "MU",
            "unit_price": 10,
            "quantity": 1,
            "fee": -1,
            "occurred_at": "2026-04-13",
        }
    ) == ["fee must be non-negative"]


def test_standard_trade_form_validation_rejects_sell_above_current_holding():
    errors = validate_trade_input(
        {
            "transaction_type": "매도",
            "market": "US",
            "currency": "USD",
            "ticker_or_name": "MU",
            "unit_price": 120,
            "quantity": 3,
            "occurred_at": "2026-04-13",
        },
        existing_holdings=[{"market": "US", "ticker": "MU", "currency": "USD", "display_name": "MU", "quantity": 2}],
    )

    assert errors == ["현재 보유 수량 2주를 초과해 매도할 수 없습니다."]


def test_standard_trade_form_validation_reports_auto_detection_failure():
    errors = validate_trade_input(
        {
            "transaction_type": "매입",
            "market": "자동감지",
            "currency": "시장 기준 자동",
            "ticker_or_name": "unknown value",
            "unit_price": 10,
            "quantity": 1,
            "occurred_at": "2026-04-13",
        }
    )

    assert errors == ["종목명 또는 ticker 형식을 확인하세요."]


def test_transaction_line_parser_supports_multi_word_names_and_datetime():
    rows = parse_transaction_lines("매입 삼성전자 보통주 72300 200 2026-04-13 09:30\n매도 MU 120.5 3 2026-06-01\n")

    assert rows[0]["transaction_type"] == "매입"
    assert rows[0]["ticker_or_name"] == "삼성전자 보통주"
    assert rows[0]["unit_price"] == "72300"
    assert rows[0]["quantity"] == "200"
    assert rows[0]["occurred_at"] == "2026-04-13T09:30"
    assert rows[1]["transaction_type"] == "매도"
    assert rows[1]["ticker_or_name"] == "MU"


def test_transaction_cashflow_rows_calculate_daily_and_cumulative_net_invested():
    rows = transaction_cashflow_rows(
        [
            {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 100, "quantity": 2, "occurred_at": "2026-01-01"},
            {"transaction_type": "매도", "ticker_or_name": "MU", "unit_price": 120, "quantity": 1, "occurred_at": "2026-01-02"},
        ],
        usd_krw=1300,
    )

    assert rows[0]["net_delta_krw"] == 260000.0
    assert rows[0]["cumulative_net_invested_krw"] == 260000.0
    assert rows[1]["net_delta_krw"] == -156000.0
    assert rows[1]["cumulative_net_invested_krw"] == 104000.0
