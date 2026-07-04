from datetime import date

from portfolio.dashboard_view import build_profit_summary_view
from portfolio.holdings import build_portfolio_metrics


def _metrics():
    return build_portfolio_metrics(
        [
            {
                "market": "US",
                "ticker": "QURE",
                "display_name": "QURE",
                "currency": "USD",
                "quantity": 10,
                "avg_price": 40,
                "current_price": 45,
                "previous_close": 44,
            }
        ],
        cash_krw=0,
        cash_usd=0,
        usd_krw=1300,
    )


def test_profit_summary_with_evaluation_profit_only():
    summary = build_profit_summary_view(metrics=_metrics(), transactions=[], cash_ledger=[], period="총")

    assert summary.evaluation_profit_krw == 65_000
    assert summary.realized_profit_krw == 0
    assert summary.dividend_interest_krw == 0
    assert summary.total_profit_krw == 65_000


def test_profit_summary_includes_dividend_and_fees_taxes():
    summary = build_profit_summary_view(
        metrics=_metrics(),
        transactions=[
            {
                "transaction_type": "buy",
                "ticker": "QURE",
                "market": "US",
                "currency": "USD",
                "display_name": "QURE",
                "unit_price": 40,
                "quantity": 10,
                "fee": 1,
                "tax": 2,
                "occurred_at": "2026-01-05",
            }
        ],
        cash_ledger=[{"event_date": "2026-02-01", "currency": "USD", "event_type": "dividend", "amount": "10"}],
        period="총",
    )

    assert summary.dividend_interest_krw == 13_000
    assert summary.fees_taxes_krw == 3_900
    assert summary.total_profit_krw == 74_100


def test_profit_summary_period_filter_uses_available_period_data():
    summary = build_profit_summary_view(
        metrics=_metrics(),
        transactions=[
            {"transaction_type": "buy", "ticker": "QURE", "market": "US", "currency": "USD", "display_name": "QURE", "unit_price": 40, "quantity": 1, "fee": 1, "tax": 0, "occurred_at": "2026-06-01"},
            {"transaction_type": "buy", "ticker": "QURE", "market": "US", "currency": "USD", "display_name": "QURE", "unit_price": 40, "quantity": 1, "fee": 2, "tax": 0, "occurred_at": "2026-07-05"},
        ],
        cash_ledger=[
            {"event_date": "2026-06-01", "currency": "USD", "event_type": "dividend", "amount": "5"},
            {"event_date": "2026-07-05", "currency": "USD", "event_type": "dividend", "amount": "7"},
        ],
        period="오늘",
        today=date(2026, 7, 5),
    )

    assert summary.dividend_interest_krw == 9_100
    assert summary.fees_taxes_krw == 2_600
    assert summary.insufficient_reasons
