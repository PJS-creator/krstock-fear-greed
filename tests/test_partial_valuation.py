from datetime import date
import pytest

from portfolio.holdings import build_portfolio_metrics
from app.ui.investment_summary_card import _holding_table_rows, _portfolio_irr


def test_missing_price_keeps_purchase_cost_but_not_zero_valuation():
    metrics = build_portfolio_metrics([
        {"ticker": "MSFT", "market": "US", "quantity": 2, "avg_price": 100, "current_price": 110},
        {"ticker": "AAPL", "market": "US", "quantity": 3, "avg_price": 50, "current_price": None},
    ], usd_krw=1300, cash_krw=1000)
    assert not metrics.valuation_complete
    assert metrics.unpriced_count == 1
    assert metrics.rows[1].market_value_krw is None
    assert metrics.rows[1].cost_basis_krw == 150 * 1300
    assert metrics.total_cost_krw == 350 * 1300
    assert metrics.total_pnl_krw == 20 * 1300
    assert metrics.total_pnl_pct == pytest.approx(0.1)
    html = "".join(_holding_table_rows(metrics))
    assert "미산정" in html and "부분 평가" in html
    assert _portfolio_irr(metrics, [{"currency": "USD"}], as_of_date=date.today()) is None


def test_cash_only_portfolio_is_fully_valued():
    assert build_portfolio_metrics([], usd_krw=1300, cash_krw=1000).valuation_complete
