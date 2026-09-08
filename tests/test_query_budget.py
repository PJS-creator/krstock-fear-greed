import pandas as pd
import pytest
from datetime import date
from types import SimpleNamespace

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


def test_retry_does_not_request_the_five_completed_symbols_again():
    payload = tuple(("US", f"S{i}", f"S{i}") for i in range(43))
    previous = tuple(
        ChartAnalysisResult(
            AnalysisInstrument(*item),
            readiness="READY_ELIGIBLE" if index < 5 else "PENDING",
            latest=SimpleNamespace(as_of_session=date(2026, 9, 7)) if index < 5 else None,
            quality_status="PASS" if index < 5 else "FAIL",
        )
        for index, item in enumerate(payload)
    )
    assert ui.retry_payload(payload, previous) == payload[5:]


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


def test_all_43_symbols_finish_without_demoting_or_refetching_completed_rows(monkeypatch):
    clock = [0.0]
    calls = []
    payload = tuple(("US", f"S{i}", f"S{i}") for i in range(43))
    monkeypatch.setattr(ui.time, "monotonic", lambda: clock[0])

    def load(item, *args, **kwargs):
        calls.append(item)
        clock[0] += 5.0
        return ChartAnalysisResult(
            AnalysisInstrument(*item), readiness="READY_ELIGIBLE", quality_status="PASS",
            latest=SimpleNamespace(as_of_session=date(2026, 9, 7)),
        )

    monkeypatch.setattr(ui, "_load_single_chart_analysis", load)
    previous = ()
    completed_counts = []
    for _ in range(9):
        requested = ui.retry_payload(payload, previous)
        completed = {row.instrument.key: row for row in previous if row.latest is not None}
        previous = ui.merge_analysis_batch(payload, previous, ui._load_chart_analysis(requested, False))
        for row in previous:
            if row.instrument.key in completed:
                assert row is completed[row.instrument.key]
        counts = ui.chart_query_counts(previous)
        assert counts["failed"] == counts["retained"] == 0
        completed_counts.append(counts["ready"])
    assert completed_counts == [5, 10, 15, 20, 25, 30, 35, 40, 43]
    assert calls == list(payload)
    assert ui.retry_payload(payload, previous) == ()
    assert ui.chart_query_counts(previous)["pending"] == 0


@pytest.mark.parametrize("readiness", ["WARMUP", "READY_INELIGIBLE"])
def test_insufficient_history_is_not_an_unattempted_query(monkeypatch, readiness):
    item = ("US", "NEW", "NEW")
    terminal = ChartAnalysisResult(AnalysisInstrument(*item), readiness=readiness)

    def load(*args, **kwargs):
        return terminal

    def unexpected_clear(*args, **kwargs):
        raise AssertionError("valid history must remain cached even when scores cannot be calculated")

    load.clear = unexpected_clear
    monkeypatch.setattr(ui, "_load_single_chart_analysis", load)
    assert ui._load_chart_analysis((item,), False) == (terminal,)
    assert ui.retry_payload((item,), (terminal,)) == ()
    assert ui.chart_query_counts((terminal,)) == dict(ready=0, pending=0, failed=0, insufficient=1, retained=0)


def test_deferred_previous_scores_and_api_failure_have_different_statuses():
    instrument = AnalysisInstrument("US", "QQQ", "QQQ")
    previous = ChartAnalysisResult(
        instrument, readiness="READY_ELIGIBLE", quality_status="PASS",
        latest=SimpleNamespace(as_of_session=date(2026, 9, 7)),
    )
    pending = ui.retain_previous_analysis((previous,), (ChartAnalysisResult(instrument, readiness="PENDING"),))[0]
    failed = ui.retain_previous_analysis((previous,), (ChartAnalysisResult(instrument, readiness="ERROR"),))[0]
    assert ui.chart_query_counts((pending,)) == dict(ready=0, pending=1, failed=0, insufficient=0, retained=1)
    assert ui.chart_query_counts((failed,)) == dict(ready=0, pending=0, failed=1, insufficient=0, retained=1)
    assert ui._data_status(pending) == "조회 대기 · 이전값 표시"
    assert ui._data_status(failed) == "이전 정상값 · 재조회 필요"
