from portfolio.allocation_view import build_allocation_view_model
from portfolio.holdings import build_portfolio_metrics


def _metrics():
    return build_portfolio_metrics(
        [
            {"market": "KR", "ticker": "005930", "display_name": "삼성전자", "currency": "KRW", "quantity": 10, "current_price": 100_000},
            {"market": "US", "ticker": "QURE", "display_name": "QURE", "currency": "USD", "quantity": 10, "current_price": 100},
        ],
        cash_krw=1_000_000,
        cash_usd=100,
        usd_krw=1000,
    )


def test_symbol_allocation_weights_sum_to_100_with_cash():
    view = build_allocation_view_model(_metrics(), perspective="종목별")

    assert view.has_data
    assert round(sum(row.weight for row in view.rows), 10) == 1.0
    assert any(row.label == "원화 현금" for row in view.rows)
    assert any(row.label == "달러 현금" for row in view.rows)


def test_type_allocation_groups_stock_and_cash():
    view = build_allocation_view_model(_metrics(), perspective="유형별")

    rows = {row.label: row for row in view.rows}
    assert rows["주식"].value_krw == 2_000_000
    assert rows["현금"].value_krw == 1_100_000


def test_currency_allocation_groups_krw_and_usd_exposure():
    view = build_allocation_view_model(_metrics(), perspective="통화별")

    rows = {row.label: row for row in view.rows}
    assert rows["KRW 자산"].value_krw == 2_000_000
    assert rows["USD 자산"].value_krw == 1_100_000


def test_zero_total_asset_returns_empty_state():
    metrics = build_portfolio_metrics([], cash_krw=0, cash_usd=0, usd_krw=1000)

    view = build_allocation_view_model(metrics)

    assert not view.has_data
    assert view.empty_message


def test_small_allocations_can_collapse_to_other():
    holdings = [
        {"market": "KR", "ticker": f"{i:06d}", "display_name": f"종목{i}", "currency": "KRW", "quantity": 1, "current_price": 1000 + i}
        for i in range(1, 12)
    ]
    metrics = build_portfolio_metrics(holdings, cash_krw=100_000, cash_usd=0, usd_krw=1000)

    view = build_allocation_view_model(metrics, perspective="종목별", max_rows=3, min_weight=0.01)

    assert len(view.rows) <= 4
    assert any(row.label == "기타" for row in view.rows)
