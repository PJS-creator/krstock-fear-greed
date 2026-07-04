from portfolio.dashboard_view import build_dashboard_view_model
from portfolio.holdings import build_portfolio_metrics


def _metrics():
    return build_portfolio_metrics(
        [
            {
                "market": "KR",
                "ticker": "005930",
                "display_name": "삼성전자",
                "currency": "KRW",
                "quantity": 10,
                "avg_price": 70000,
                "current_price": 80000,
                "previous_close": 79000,
            },
            {
                "market": "US",
                "ticker": "QURE",
                "display_name": "QURE",
                "currency": "USD",
                "quantity": 10,
                "avg_price": 40,
                "current_price": 45,
                "previous_close": 44,
            },
        ],
        cash_krw=1_000_000,
        cash_usd=100,
        usd_krw=1300,
    )


def test_dashboard_view_model_separates_investments_and_cash():
    metrics = _metrics()
    model = build_dashboard_view_model(metrics)

    assert [row.ticker for row in model.asset_rows] == ["005930", "QURE"]
    assert [row.currency for row in model.cash_rows] == ["KRW", "USD"]
    assert model.cash_value_krw == 1_130_000
    assert model.total_asset_krw == metrics.total_value_krw


def test_dashboard_view_model_total_asset_is_investment_plus_cash():
    model = build_dashboard_view_model(_metrics())

    assert model.total_asset_krw == model.investment_value_krw + model.cash_value_krw


def test_dashboard_view_model_top_n_limits_asset_rows_without_mixing_cash():
    model = build_dashboard_view_model(_metrics(), max_assets=1)

    assert len(model.asset_rows) == 1
    assert len(model.cash_rows) == 2


def test_dashboard_view_model_empty_state():
    metrics = build_portfolio_metrics([], cash_krw=0, cash_usd=0, usd_krw=1300)

    model = build_dashboard_view_model(metrics)

    assert model.is_empty
    assert model.asset_rows == ()
    assert model.cash_rows == ()
