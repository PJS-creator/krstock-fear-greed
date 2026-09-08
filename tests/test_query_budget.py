import pandas as pd
import pytest

from app.ui import chart_analysis as ui
from portfolio.chart_analysis import AnalysisInstrument, ChartAnalysisResult
from portfolio.chart_analysis_data import fetch_daily_histories
from portfolio.pricing.base import PriceProviderError
from portfolio.pricing.kis import KoreaInvestmentQuoteProvider


def test_chart_batch_stops_starting_requests_after_budget(monkeypatch):
    clock = [0.0]
    calls = []
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock[0])
    def load(item, *args, **kwargs):
        calls.append(item)
        clock[0] = 25.0
        return ChartAnalysisResult(AnalysisInstrument(*item), readiness="READY_ELIGIBLE", latest=object())
    monkeypatch.setattr(ui, "_load_single_chart_analysis", load)
    results = ui._load_chart_analysis((("US", "QQQ", "QQQ"), ("US", "MSFT", "MSFT")), False)
    assert len(calls) == 1
    assert results[1].readiness == "PENDING"


@pytest.mark.parametrize("market,symbol", [("KR", "005930"), ("US", "MSFT")])
def test_kis_does_not_start_pagination_after_deadline(market, symbol):
    def unexpected(*args, **kwargs):
        raise AssertionError("network request after budget expired")
    provider = KoreaInvestmentQuoteProvider(app_key="test", app_secret="test", response_loader=unexpected)
    with pytest.raises(PriceProviderError, match="시간 한도"):
        provider.get_daily_history_rows(market, symbol, max_runtime_seconds=0)


def test_interactive_chart_mode_skips_unbounded_fdr_fallback():
    def unexpected(*args, **kwargs):
        raise AssertionError("unbounded fallback must not run in interactive mode")
    results = fetch_daily_histories(
        [AnalysisInstrument("KR", "005930", "Samsung")], loader=lambda **kwargs: pd.DataFrame(),
        korea_fallback_reader=unexpected, allow_korea_fallback=False,
    )
    assert results[0].error


def test_unattempted_instruments_are_not_starved_by_repeated_slow_failures():
    failed = ChartAnalysisResult(AnalysisInstrument("US", "BAD", "BAD"), readiness="FAILED")
    pending = ChartAnalysisResult(AnalysisInstrument("US", "QQQ", "QQQ"), readiness="PENDING")
    assert ui.retry_payload((("US", "BAD", "BAD"), ("US", "QQQ", "QQQ")), [failed, pending])[0][1] == "QQQ"


def test_unexpected_single_symbol_error_does_not_abort_other_symbols(monkeypatch):
    def load(item, *args, **kwargs):
        if item[1] == "BAD":
            raise ValueError("malformed data")
        return ChartAnalysisResult(AnalysisInstrument(*item), readiness="READY_ELIGIBLE", latest=object())
    load.clear = lambda *args, **kwargs: None
    monkeypatch.setattr(ui, "_load_single_chart_analysis", load)
    result = ui._load_chart_analysis((("US", "BAD", "BAD"), ("US", "QQQ", "QQQ")), False)
    assert result[0].error
    assert result[1].latest is not None
