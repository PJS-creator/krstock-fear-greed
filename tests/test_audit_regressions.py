from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app.ui.chart_analysis import can_continue_batch, deferred_payload, merge_analysis_batch
from app.ui.native_theme import native_theme_config
from app.ui.status import select_price_refresh_rows
from app.ui.theme import get_theme_tokens
from portfolio.chart_analysis import AnalysisInstrument, ChartAnalysisResult
from portfolio.chart_analysis_data import yahoo_symbol_candidates
from portfolio.pricing.yahoo_finance import normalize_yfinance_symbol, YFinanceQuoteProvider
from portfolio.risk_metrics import (
    ValuePoint, external_flow_dates, matched_interval_returns, value_series_from_history_records,
)


@pytest.mark.parametrize("raw, expected", [
    ("BRK.B", "BRK-B"), ("brk.a", "BRK-A"), ("BRK-B", "BRK-B"),
    ("005930.KS", "005930.KS"), ("VOD.L", "VOD.L"), ("^KS200", "^KS200"),
])
def test_yahoo_share_class_conversion_preserves_exchange_suffixes(raw, expected):
    assert normalize_yfinance_symbol(raw) == expected
    instrument = AnalysisInstrument("US", raw, raw)
    assert yahoo_symbol_candidates(instrument) == (expected,)
    assert instrument.symbol == raw


def test_current_quote_uses_yahoo_class_share_symbol():
    calls = []
    def loader(symbol, **kwargs):
        calls.append(symbol)
        return pd.DataFrame({"Close": [400, 405]}, index=pd.date_range("2026-10-01", periods=2))
    provider = YFinanceQuoteProvider(history_loader=loader)
    assert provider.get_quote("BRK.B").price == 405
    assert provider.get_quote("BRK.B").symbol == "BRK.B"
    assert calls == ["BRK-B", "BRK-B"]


def test_beta_compares_identical_sparse_intervals_not_last_day_return():
    portfolio = [ValuePoint(date(2026, 10, 1), 100), ValuePoint(date(2026, 10, 6), 110)]
    benchmark = [ValuePoint(date(2026, 10, day), value) for day, value in [(1, 100), (2, 101), (5, 102), (6, 103)]]
    p, b, skipped = matched_interval_returns(portfolio, benchmark)
    assert p[date(2026, 10, 6)] == pytest.approx(.1)
    assert b[date(2026, 10, 6)] == pytest.approx(.03)
    assert skipped == 0


def test_beta_excludes_flow_intervals_including_boundary_and_ignores_trade_settlement():
    points = [ValuePoint(date(2026, 10, day), 100 + day) for day in range(1, 6)]
    ledger = [
        {"event_date": "2026-10-03", "event_type": "deposit", "amount": "50", "currency": "USD"},
        {"event_date": "2026-10-05", "event_type": "buy_settlement", "amount": "-50"},
    ]
    p, b, skipped = matched_interval_returns(points, points, excluded_dates=external_flow_dates(ledger))
    assert list(p) == list(b) == [date(2026, 10, 2), date(2026, 10, 5)]
    assert skipped == 2


def test_beta_missing_benchmark_boundary_never_forward_fills():
    portfolio = [ValuePoint(date(2026, 10, day), 100 + day) for day in (1, 3, 6)]
    p, b, _ = matched_interval_returns(portfolio, [portfolio[0], portfolio[-1]])
    assert list(p) == list(b) == [date(2026, 10, 6)]


def test_history_latest_snapshot_uses_kst_and_not_input_order():
    records = [
        SimpleNamespace(captured_at="2026-10-01T18:00:00+00:00", total_value_krw=120),
        SimpleNamespace(captured_at="2026-10-01T15:30:00+00:00", total_value_krw=100),
    ]
    assert value_series_from_history_records(records) == [ValuePoint(date(2026, 10, 2), 120)]


def test_history_orders_mixed_offsets_and_accepts_datetime_records():
    records = [
        SimpleNamespace(captured_at="2026-10-02T02:30:00+09:00", total_value_krw=100),
        SimpleNamespace(captured_at=datetime.fromisoformat("2026-10-01T18:00:00+00:00"), total_value_krw=120),
    ]
    assert value_series_from_history_records(records) == [ValuePoint(date(2026, 10, 2), 120)]


def test_price_retry_includes_new_holding_without_status():
    rows = [{"ticker": "BRK.B", "market": "US"}]
    assert select_price_refresh_rows(rows, "실패 종목만") == rows


def test_native_theme_carries_canvas_tokens_without_global_config_changes():
    for mode in ("light", "dark"):
        config = native_theme_config(mode)
        tokens = get_theme_tokens(mode)
        assert config["backgroundColor"] == tokens["surface"]
        assert config["textColor"] == tokens["text"]
        assert config["dataframeHeaderBackgroundColor"] == tokens["table_header_bg"]
    assert native_theme_config("light")["base"] == 0
    assert native_theme_config("dark")["base"] == 1


def test_automatic_batches_only_query_deferred_work_and_stop_without_progress():
    payload = tuple(("US", symbol, symbol) for symbol in ("A", "B", "C"))
    pending = tuple(ChartAnalysisResult(AnalysisInstrument(*item), readiness="PENDING") for item in payload)
    failed = ChartAnalysisResult(AnalysisInstrument(*payload[0]), readiness="FAILED")
    first = merge_analysis_batch(payload, pending, (failed,))
    assert deferred_payload(payload, first) == payload[1:]
    assert can_continue_batch(payload, pending, first, batches=1)
    assert not can_continue_batch(payload, first, first, batches=2)
    assert not can_continue_batch(payload, pending, first, batches=len(payload))
    complete = tuple(ChartAnalysisResult(AnalysisInstrument(*item), readiness="FAILED") for item in payload)
    assert deferred_payload(payload, complete) == ()
    assert not can_continue_batch(payload, first, complete, batches=2)
