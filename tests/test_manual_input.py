import csv
from io import StringIO

import pytest

from portfolio.analytics import build_portfolio_snapshot
from portfolio.manual_input import (
    PORTFOLIO_CSV_COLUMNS,
    csv_template,
    normalize_portfolio_rows,
    row_to_position_quote,
    rows_to_csv,
    rows_to_positions_quotes,
)


def _row(**overrides):
    row = {
        "market": "US",
        "symbol": "AAPL",
        "name": "Apple",
        "currency": "USD",
        "quantity": "2",
        "avg_price": "100",
        "current_price": "125",
        "previous_close": "120",
        "target_weight": "0.5",
        "strategy_tag": "Core",
    }
    row.update(overrides)
    return row


def test_csv_row_to_position_quote_conversion():
    position, quote = row_to_position_quote(_row(symbol="msft", strategy_tag=""))

    assert position.market == "US"
    assert position.symbol == "MSFT"
    assert position.name == "Apple"
    assert position.currency == "USD"
    assert position.quantity == 2
    assert position.avg_price == 100
    assert position.target_weight == 0.5
    assert position.strategy_tag == "Manual"
    assert quote.price == 125
    assert quote.previous_close == 120
    assert quote.provider == "manual"


def test_user_input_portfolio_calculation():
    rows = [
        _row(market="KR", symbol="005930", name="Samsung", currency="KRW", quantity="3", avg_price="70000", current_price="80000", previous_close="79000", target_weight="0.4", strategy_tag="Core"),
        _row(symbol="AAPL", name="Apple", quantity="2", avg_price="100", current_price="125", previous_close="120", target_weight="0.4", strategy_tag="Global"),
        _row(symbol="CASHLIKE", name="Zero Qty", quantity="0", avg_price="10", current_price="20", previous_close="15", target_weight="0", strategy_tag="Watch"),
    ]

    positions, quotes = rows_to_positions_quotes(rows)
    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=1_300, cash_krw=100_000)

    assert snapshot.total_position_value_krw == pytest.approx(565_000)
    assert snapshot.total_value_krw == pytest.approx(665_000)
    assert snapshot.total_cost_krw == pytest.approx(470_000)
    assert snapshot.day_pnl_krw == pytest.approx(16_000)
    assert snapshot.total_pnl_krw == pytest.approx(95_000)
    assert snapshot.total_pnl_pct == pytest.approx(95_000 / 470_000)
    assert snapshot.positions[0].market_value_krw == pytest.approx(240_000)
    assert snapshot.positions[0].weight == pytest.approx(240_000 / 665_000)
    assert snapshot.positions[0].target_gap == pytest.approx(240_000 / 665_000 - 0.4)
    assert snapshot.positions[2].market_value_krw == 0
    assert snapshot.positions[2].total_pnl_pct == 0


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"currency": "EUR"}, "Unsupported currency"),
        ({"quantity": "-1"}, "quantity"),
        ({"avg_price": "-1"}, "avg_price"),
        ({"current_price": "-1"}, "current_price"),
        ({"previous_close": "-1"}, "previous_close"),
        ({"target_weight": "-0.1"}, "target_weight"),
        ({"quantity": "not-a-number"}, "quantity must be a number"),
    ],
)
def test_invalid_currency_and_negative_inputs_are_rejected(overrides, match):
    with pytest.raises(ValueError, match=match):
        row_to_position_quote(_row(**overrides))


def test_duplicate_market_symbol_rows_are_rejected():
    with pytest.raises(ValueError, match="duplicate market/symbol"):
        rows_to_positions_quotes([_row(symbol="AAPL"), _row(symbol="aapl")])


def test_csv_template_and_export_use_expected_columns():
    template = csv_template()
    assert template == ",".join(PORTFOLIO_CSV_COLUMNS) + "\n"

    exported = rows_to_csv([_row(symbol="005930", market="KR", currency="KRW")])
    parsed_rows = list(csv.DictReader(StringIO(exported)))

    assert parsed_rows[0]["symbol"] == "005930"
    assert parsed_rows[0]["currency"] == "KRW"
    assert set(parsed_rows[0]) == set(PORTFOLIO_CSV_COLUMNS)


def test_normalize_portfolio_rows_reports_row_number_for_bad_csv_data():
    with pytest.raises(ValueError, match="Row 2: Unsupported currency"):
        normalize_portfolio_rows([_row(symbol="AAPL"), _row(symbol="SAP", currency="EUR")])
