from datetime import datetime, timezone
from time import sleep

import pytest

from portfolio.analytics import build_portfolio_snapshot
from portfolio.models import Position, Quote
from portfolio.sample_data import sample_portfolio


def _quotes(*quotes: Quote) -> dict[tuple[str, str], Quote]:
    return {(quote.market, quote.symbol): quote for quote in quotes}


def test_sample_portfolio_totals_are_correct():
    positions, quotes, usd_krw, cash_krw = sample_portfolio()

    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)

    assert snapshot.total_position_value_krw == pytest.approx(5_266_200)
    assert snapshot.total_value_krw == pytest.approx(6_266_200)
    assert snapshot.total_cost_krw == pytest.approx(4_827_600)
    assert snapshot.total_pnl_krw == pytest.approx(438_600)
    assert snapshot.day_pnl_krw == pytest.approx(69_160)
    assert snapshot.total_pnl_pct == pytest.approx(438_600 / 4_827_600)


def test_sample_portfolio_weights_include_cash_in_denominator():
    positions, quotes, usd_krw, cash_krw = sample_portfolio()

    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)

    assert sum(item.weight for item in snapshot.positions) == pytest.approx(
        snapshot.total_position_value_krw / snapshot.total_value_krw
    )
    samsung = next(item for item in snapshot.positions if item.position.symbol == "005930")
    assert samsung.market_value_krw == pytest.approx(780_000)
    assert samsung.weight == pytest.approx(780_000 / 6_266_200)


def test_krw_only_portfolio_calculation():
    positions = [Position("KR", "005930", "삼성전자", 2, 70_000, "KRW", 0.5)]
    quotes = _quotes(Quote("KR", "005930", 80_000, 75_000, "KRW"))

    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=1_300, cash_krw=40_000)

    assert snapshot.total_position_value_krw == pytest.approx(160_000)
    assert snapshot.total_value_krw == pytest.approx(200_000)
    assert snapshot.total_cost_krw == pytest.approx(140_000)
    assert snapshot.total_pnl_krw == pytest.approx(20_000)
    assert snapshot.day_pnl_krw == pytest.approx(10_000)
    assert snapshot.positions[0].weight == pytest.approx(0.8)


def test_usd_only_portfolio_calculation():
    positions = [Position("US", "AAPL", "Apple", 3, 100, "USD", 1.0)]
    quotes = _quotes(Quote("US", "AAPL", 120, 115, "USD"))

    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=1_400, cash_krw=0)

    assert snapshot.total_position_value_krw == pytest.approx(504_000)
    assert snapshot.total_value_krw == pytest.approx(504_000)
    assert snapshot.total_cost_krw == pytest.approx(420_000)
    assert snapshot.total_pnl_krw == pytest.approx(84_000)
    assert snapshot.day_pnl_krw == pytest.approx(21_000)
    assert snapshot.positions[0].weight == pytest.approx(1.0)


def test_zero_cash_uses_positions_as_total_value_denominator():
    positions = [
        Position("KR", "AAA", "AAA", 1, 50, "KRW", 0.5),
        Position("KR", "BBB", "BBB", 3, 50, "KRW", 0.5),
    ]
    quotes = _quotes(
        Quote("KR", "AAA", 100, 100, "KRW"),
        Quote("KR", "BBB", 100, 100, "KRW"),
    )

    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=1_300, cash_krw=0)

    assert snapshot.total_value_krw == pytest.approx(400)
    assert snapshot.positions[0].weight == pytest.approx(0.25)
    assert snapshot.positions[1].weight == pytest.approx(0.75)


def test_usd_valuation_changes_when_fx_rate_changes():
    positions = [Position("US", "AAPL", "Apple", 1, 100, "USD", 1.0)]
    quotes = _quotes(Quote("US", "AAPL", 110, 100, "USD"))

    low_fx = build_portfolio_snapshot(positions, quotes, usd_krw=1_000)
    high_fx = build_portfolio_snapshot(positions, quotes, usd_krw=1_500)

    assert low_fx.total_position_value_krw == pytest.approx(110_000)
    assert high_fx.total_position_value_krw == pytest.approx(165_000)


def test_position_and_quote_currency_mismatch_raises_value_error():
    positions = [Position("US", "AAPL", "Apple", 1, 100, "USD")]
    quotes = _quotes(Quote("US", "AAPL", 110, 100, "KRW"))

    with pytest.raises(ValueError, match="currency"):
        build_portfolio_snapshot(positions, quotes, usd_krw=1_300)


def test_unsupported_currency_raises_value_error():
    positions = [Position("US", "SAP", "SAP", 1, 100, "EUR")]
    quotes = _quotes(Quote("US", "SAP", 110, 100, "EUR"))

    with pytest.raises(ValueError, match="Unsupported currency"):
        build_portfolio_snapshot(positions, quotes, usd_krw=1_300)


def test_zero_cost_basis_keeps_return_at_zero():
    positions = [Position("KR", "FREE", "Free Shares", 10, 0, "KRW")]
    quotes = _quotes(Quote("KR", "FREE", 1_000, 900, "KRW"))

    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=1_300)

    assert snapshot.total_cost_krw == 0
    assert snapshot.total_pnl_krw == pytest.approx(10_000)
    assert snapshot.total_pnl_pct == 0.0
    assert snapshot.positions[0].total_pnl_pct == 0.0


@pytest.mark.parametrize(
    ("positions", "quotes", "usd_krw", "cash_krw", "match"),
    [
        ([Position("KR", "NEGQ", "Negative Quantity", -1, 100, "KRW")], _quotes(Quote("KR", "NEGQ", 100, 100, "KRW")), 1_300, 0, "quantity"),
        ([Position("KR", "NEGA", "Negative Average", 1, -100, "KRW")], _quotes(Quote("KR", "NEGA", 100, 100, "KRW")), 1_300, 0, "avg_price"),
        ([Position("KR", "NEGP", "Negative Price", 1, 100, "KRW")], _quotes(Quote("KR", "NEGP", -100, 100, "KRW")), 1_300, 0, "quote.price"),
        ([Position("KR", "NEGC", "Negative Previous Close", 1, 100, "KRW")], _quotes(Quote("KR", "NEGC", 100, -100, "KRW")), 1_300, 0, "previous_close"),
        ([Position("KR", "BADFX", "Bad FX", 1, 100, "KRW")], _quotes(Quote("KR", "BADFX", 100, 100, "KRW")), 0, 0, "usd_krw"),
        ([Position("KR", "CASH", "Cash", 1, 100, "KRW")], _quotes(Quote("KR", "CASH", 100, 100, "KRW")), 1_300, -1, "cash_krw"),
    ],
)
def test_invalid_numeric_inputs_raise_value_error(positions, quotes, usd_krw, cash_krw, match):
    with pytest.raises(ValueError, match=match):
        build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)


def test_quote_fetched_at_default_factory_uses_instance_creation_time():
    before_first = datetime.now(timezone.utc)
    first = Quote("KR", "AAA", 1, 1, "KRW")
    sleep(0.001)
    second = Quote("KR", "AAA", 1, 1, "KRW")
    after_second = datetime.now(timezone.utc)

    assert before_first <= first.fetched_at <= after_second
    assert before_first <= second.fetched_at <= after_second
    assert second.fetched_at > first.fetched_at
