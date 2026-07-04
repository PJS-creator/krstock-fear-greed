from portfolio.allocation_view import build_allocation_view_model
from portfolio.dashboard_view import build_dashboard_view_model, build_profit_summary_view
from portfolio.holdings import build_portfolio_metrics
from portfolio.journal import build_journal_events


def test_empty_dashboard_view_model_uses_empty_state_flag():
    metrics = build_portfolio_metrics([], cash_krw=0, cash_usd=0, usd_krw=1300)

    assert build_dashboard_view_model(metrics).is_empty


def test_empty_profit_summary_has_no_fake_nonzero_values():
    metrics = build_portfolio_metrics([], cash_krw=0, cash_usd=0, usd_krw=1300)
    summary = build_profit_summary_view(metrics=metrics, transactions=[], cash_ledger=[])

    assert not summary.has_data
    assert summary.total_profit_krw == 0


def test_empty_allocation_has_no_chart_data():
    metrics = build_portfolio_metrics([], cash_krw=0, cash_usd=0, usd_krw=1300)
    view = build_allocation_view_model(metrics)

    assert not view.has_data
    assert view.rows == ()


def test_empty_journal_has_no_events():
    assert build_journal_events(transactions=[], cash_ledger=[], journal_notes=[]) == []
