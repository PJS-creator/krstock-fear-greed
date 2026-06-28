from portfolio.historical_holdings import reconstruct_historical_holdings
from portfolio.history.models import PortfolioHistoryRecord
from portfolio.holdings import build_portfolio_metrics

from app.ui.charts import (
    plot_allocation,
    plot_contribution,
    plot_currency_exposure,
    plot_reconstructed_holdings_area,
    plot_reconstructed_total_value,
    plot_total_value_history,
)
from app.ui.theme import SEMANTIC_COLORS, deterministic_color


def _metrics(rows=None):
    return build_portfolio_metrics(
        rows
        or [
            {"market": "KR", "ticker": "005930", "display_name": "삼성전자", "quantity": 10, "current_price": 72000, "previous_close": 71000},
            {"market": "US", "ticker": "MU", "display_name": "Micron", "quantity": 20, "current_price": 120, "previous_close": 125},
            {"market": "US", "ticker": "GOOG", "display_name": "Alphabet", "quantity": 2, "current_price": 180, "previous_close": 170},
        ],
        cash_krw=100_000,
        cash_usd=10,
        usd_krw=1400,
    )


def _history_record(captured_at: str, total: float) -> PortfolioHistoryRecord:
    return PortfolioHistoryRecord(
        owner_id="test-owner",
        portfolio_name="main",
        captured_at=captured_at,
        event_type="manual_capture",
        total_value_krw=total,
        total_position_value_krw=total - 100_000,
        cash_krw=100_000,
        cash_usd=0,
        cash_total_krw=100_000,
        usd_krw=1400,
        day_change_krw=10_000,
        day_change_pct=0.01,
        holdings_count=2,
        stale_quote_count=0,
        payload_json={},
        fingerprint=captured_at,
    )


def _reconstruction_result():
    from datetime import date

    class Provider:
        def get_close_prices(self, *, market, ticker, start_date, end_date):
            del market, start_date, end_date
            if ticker == "005930":
                return {date(2026, 6, 1): 80000, date(2026, 6, 2): 81000}
            return {date(2026, 6, 2): 280000}

        def get_usd_krw_rates(self, *, start_date, end_date):
            del start_date, end_date
            return {}

    return reconstruct_historical_holdings(
        [
            {"as_of_date": "2026-06-01", "ticker": "005930", "quantity": 10},
            {"as_of_date": "2026-06-02", "ticker": "005930", "quantity": 5},
            {"as_of_date": "2026-06-02", "ticker": "000660", "quantity": 1},
        ],
        [{"as_of_date": "2026-06-01", "cash_krw": 100000}],
        Provider(),
        end_date="2026-06-02",
    )


def test_deterministic_color_mapping_is_stable():
    assert deterministic_color("005930") == deterministic_color("005930")
    assert deterministic_color("005930") == deterministic_color("005930".lower())


def test_allocation_donut_has_labels_hover_and_percent():
    fig = plot_allocation(_metrics())

    assert fig is not None
    text = " ".join(str(item) for item in fig.data[0].text)
    assert "005930" in text
    assert "%" in text
    hover = fig.data[0].hovertemplate
    assert "평가액" in hover
    assert "비중" in hover
    assert "오늘 변동" in hover


def test_allocation_donut_collapses_small_or_extra_slices_to_other():
    rows = [
        {"market": "US", "ticker": f"T{i}", "display_name": f"Name {i}", "quantity": 1, "current_price": 10 + i, "previous_close": 10}
        for i in range(10)
    ]

    fig = plot_allocation(_metrics(rows), max_slices=3, min_label_weight=0.0)

    assert fig is not None
    assert any("기타" in str(row[0]) for row in fig.data[0].customdata)


def test_contribution_chart_uses_semantic_colors_labels_and_zero_line():
    fig = plot_contribution(_metrics())

    assert fig is not None
    colors = list(fig.data[0].marker.color)
    assert SEMANTIC_COLORS["positive"] in colors
    assert SEMANTIC_COLORS["negative"] in colors
    assert any(str(label).startswith(("+", "-")) for label in fig.data[0].text)
    assert fig.layout.shapes and fig.layout.shapes[0].x0 == 0


def test_contribution_chart_is_sorted_by_change_amount():
    fig = plot_contribution(_metrics())

    x_values = list(fig.data[0].x)
    assert x_values == sorted(x_values)


def test_currency_exposure_chart_uses_percent_labels():
    fig = plot_currency_exposure(_metrics())

    assert fig is not None
    assert len(fig.data) == 2
    assert round(sum(trace.x[0] for trace in fig.data), 6) == 100
    assert all("%" in trace.text[0] for trace in fig.data)


def test_history_chart_uses_kst_hover_data():
    fig = plot_total_value_history(
        [
            _history_record("2026-06-23T00:00:00+00:00", 1_000_000),
            _history_record("2026-06-23T03:00:00+00:00", 1_100_000),
        ],
        period="all",
    )

    assert fig is not None
    assert fig.layout.hovermode == "x unified"
    assert fig.data[0].customdata[0][0] == "2026-06-23 09:00 KST"
    assert "USD/KRW" in fig.data[0].hovertemplate


def test_reconstructed_total_chart_has_snapshot_markers_and_hover_context():
    fig = plot_reconstructed_total_value(_reconstruction_result())

    assert fig is not None
    assert fig.layout.hovermode == "x unified"
    assert fig.layout.shapes
    assert "적용 스냅샷" in fig.data[0].hovertemplate


def test_reconstructed_holdings_area_uses_ticker_series():
    fig = plot_reconstructed_holdings_area(_reconstruction_result())

    assert fig is not None
    assert {trace.name.split(" · ")[0] for trace in fig.data} == {"000660", "005930"}
