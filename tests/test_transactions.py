import pytest

from portfolio.transactions import (
    build_transaction_preview,
    parse_transaction_lines,
    preview_rows_to_transactions,
    transaction_cashflow_rows,
    transactions_to_holdings,
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
        [{"transaction_type": "매입", "ticker_or_name": "삼성전자", "unit_price": "72300", "quantity": "200", "occurred_at": "2026-04-13"}],
        korea_listing_records=KRX_RECORDS,
    )
    transactions = preview_rows_to_transactions(preview.rows)

    assert preview.summary == {"total": 1, "ok": 1, "candidate_required": 0, "error": 0}
    assert transactions[0]["transaction_type"] == "buy"
    assert transactions[0]["ticker"] == "005930"
    assert transactions[0]["unit_price"] == 72300.0
    assert transactions[0]["quantity"] == 200.0
    assert transactions[0]["occurred_at"] == "2026-04-13"


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
