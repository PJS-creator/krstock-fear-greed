import pytest

from portfolio.performance import calculate_performance_metrics


def test_average_cost_realized_pnl_and_remaining_cost_basis():
    analysis = calculate_performance_metrics(
        transactions=[
            {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 100, "quantity": 10, "occurred_at": "2026-01-01"},
            {"transaction_type": "매도", "ticker_or_name": "MU", "unit_price": 150, "quantity": 4, "occurred_at": "2026-01-02"},
        ],
        holdings=[
            {"market": "US", "ticker": "MU", "currency": "USD", "display_name": "Micron", "quantity": 6, "avg_price": 100, "current_price": 160}
        ],
        cash_ledger=[],
        usd_krw=1000,
    )

    row = analysis.rows[0]
    assert row.quantity == pytest.approx(6)
    assert row.avg_price == pytest.approx(100)
    assert row.realized_pnl_krw == pytest.approx(200_000)
    assert row.unrealized_pnl_krw == pytest.approx(360_000)
    assert analysis.total_profit_krw == pytest.approx(560_000)


def test_buy_only_has_unrealized_pnl_without_realized_pnl():
    analysis = calculate_performance_metrics(
        transactions=[
            {"transaction_type": "매입", "ticker_or_name": "005930", "market": "KR", "currency": "KRW", "unit_price": 70_000, "quantity": 10, "occurred_at": "2026-01-01"}
        ],
        holdings=[
            {"market": "KR", "ticker": "005930", "currency": "KRW", "display_name": "삼성전자", "quantity": 10, "avg_price": 70_000, "current_price": 80_000}
        ],
        cash_ledger=[],
        usd_krw=1300,
    )

    assert analysis.realized_pnl_krw == 0
    assert analysis.unrealized_pnl_krw == pytest.approx(100_000)
    assert analysis.total_profit_krw == pytest.approx(100_000)


def test_dividend_cash_ledger_is_included_in_total_profit():
    analysis = calculate_performance_metrics(
        transactions=[],
        holdings=[],
        cash_ledger=[
            {"event_date": "2026-01-10", "currency": "KRW", "event_type": "dividend", "amount": "50000"}
        ],
        usd_krw=1300,
        current_total_value_krw=50_000,
    )

    assert analysis.dividend_interest_krw == pytest.approx(50_000)
    assert analysis.total_profit_krw == pytest.approx(50_000)


def test_symbol_tagged_dividend_is_allocated_to_symbol_row():
    analysis = calculate_performance_metrics(
        transactions=[
            {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 100, "quantity": 1, "occurred_at": "2026-01-01"}
        ],
        holdings=[
            {"market": "US", "ticker": "MU", "currency": "USD", "display_name": "Micron", "quantity": 1, "avg_price": 100, "current_price": 100}
        ],
        cash_ledger=[
            {"event_date": "2026-01-10", "currency": "USD", "event_type": "dividend", "amount": "10", "market": "US", "ticker": "MU", "fx_rate_to_krw": 1300}
        ],
        usd_krw=1300,
        current_total_value_krw=13_000,
    )

    assert analysis.dividend_interest_krw == pytest.approx(13_000)
    assert analysis.rows[0].dividend_interest_krw == pytest.approx(13_000)
    assert analysis.total_profit_krw == pytest.approx(13_000)


def test_fees_and_taxes_are_subtracted_from_total_profit():
    analysis = calculate_performance_metrics(
        transactions=[
            {"transaction_type": "매입", "ticker_or_name": "005930", "market": "KR", "currency": "KRW", "unit_price": 10_000, "quantity": 10, "fee": 100, "tax": 20, "occurred_at": "2026-01-01"},
            {"transaction_type": "매도", "ticker_or_name": "005930", "market": "KR", "currency": "KRW", "unit_price": 12_000, "quantity": 10, "fee": 100, "tax": 30, "occurred_at": "2026-01-02"},
        ],
        holdings=[],
        cash_ledger=[],
        usd_krw=1300,
    )

    assert analysis.realized_pnl_krw == pytest.approx(20_000)
    assert analysis.fees_taxes_krw == pytest.approx(250)
    assert analysis.total_profit_krw == pytest.approx(19_750)


def test_usd_fx_change_is_separated_from_price_effect():
    analysis = calculate_performance_metrics(
        transactions=[
            {"transaction_type": "매입", "ticker_or_name": "MU", "unit_price": 100, "quantity": 10, "occurred_at": "2026-01-01", "fx_rate_to_krw": 1000}
        ],
        holdings=[
            {"market": "US", "ticker": "MU", "currency": "USD", "display_name": "Micron", "quantity": 10, "avg_price": 100, "current_price": 100}
        ],
        cash_ledger=[],
        usd_krw=1200,
    )

    assert analysis.price_effect_krw == pytest.approx(0)
    assert analysis.fx_effect_krw == pytest.approx(200_000)
    assert analysis.unrealized_pnl_krw == pytest.approx(200_000)
    assert analysis.total_profit_krw == pytest.approx(200_000)
