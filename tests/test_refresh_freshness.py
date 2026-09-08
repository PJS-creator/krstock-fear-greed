from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from types import SimpleNamespace

from app.ui.freshness import mark_checked, refresh_due
from app.ui.chart_analysis import retain_previous_analysis, _data_status
from app.ui.investment_summary_card import _meta_strategy_panel, _shadow_strategy_panel
from portfolio.snapshot_freshness import publication_note, with_publication_health
from portfolio.chart_analysis import AnalysisInstrument, ChartAnalysisResult


def test_session_refresh_expires_even_when_holdings_are_unchanged():
    state = {}
    assert refresh_due(state, "checked", ttl_seconds=600, now=1000)
    mark_checked(state, "checked", now=1000)
    assert not refresh_due(state, "checked", ttl_seconds=600, now=1599)
    assert refresh_due(state, "checked", ttl_seconds=600, now=1600)
    assert refresh_due(state, "checked", ttl_seconds=600, now=0)


def test_weekend_no_new_session_is_not_reported_as_stale_signal():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    signal = {"decision_session": "2026-09-04", "generated_at_utc": "2026-09-04T22:00:00Z"}
    run = {"decision_session": "2026-09-04", "generated_at_utc": now.isoformat(), "status": "NO_NEW_SESSION"}
    assert publication_note(signal, run, now=now) == ""
    assert "36시간" in publication_note(signal, run, now=now + timedelta(hours=37))
    run["status"] = "SOURCE_FAILED"
    assert "SOURCE_FAILED" in publication_note(signal, run, now=now)


def test_publication_race_is_visible_without_recomputing_strategy():
    now = datetime.now(timezone.utc)
    assert "배포 대기" in publication_note(
        {"decision_session": "2026-09-03"},
        {"decision_session": "2026-09-04", "status": "VALIDATED", "generated_at_utc": now.isoformat()}, now=now,
    )


def test_failed_health_request_keeps_validated_signal():
    def fail(*args, **kwargs):
        assert kwargs["timeout"] == 3.0
        raise TimeoutError()
    signal = {"status": "VALIDATED", "router_target": "QQQ"}
    result = with_publication_health(signal, url="https://example.com/signals/latest_validated.json", opener=fail)
    assert result["router_target"] == "QQQ"
    assert "조회 실패" in result["freshness_note"]
    assert "freshness_note" not in signal


def test_strategy_panels_do_not_hide_refresh_failures():
    assert "이전 검증값" in _meta_strategy_panel({"data_mode": "official", "status": "updated", "freshness_note": "최근 실행 실패"})
    assert "최근 실행 실패" in _shadow_strategy_panel({"status": "VALIDATED", "strategy_kind": "ALTERNATIVE_SHADOW", "refresh_error": "최근 실행 실패"})


def test_failed_or_older_chart_results_do_not_erase_previous_scores():
    instrument = AnalysisInstrument(market="US", symbol="QQQ", display_name="QQQ")
    good = ChartAnalysisResult(instrument=instrument, readiness="READY_ELIGIBLE", latest=SimpleNamespace(as_of_session=date(2026, 9, 4)), quality_status="PASS")
    failed = ChartAnalysisResult(instrument=instrument, readiness="FAILED", error="timeout")
    retained = retain_previous_analysis([good], [failed])[0]
    assert retained.latest is good.latest
    assert retained.error == "timeout"
    assert "이전 정상값" in _data_status(retained)
    older = replace(good, latest=SimpleNamespace(as_of_session=date(2026, 9, 3)))
    assert retain_previous_analysis([good], [older])[0].latest is good.latest
    assert retain_previous_analysis([good], [good])[0].warnings == ()
