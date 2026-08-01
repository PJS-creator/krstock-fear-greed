from datetime import date
import json

from portfolio.meta_strategy_notification import (
    render_meta_strategy_notification,
    should_publish_notification,
)
from scripts.render_meta_strategy_notification import main


def _run(*, status: str = "VALIDATED", run_slot: str = "primary-0737-kst") -> dict[str, object]:
    return {
        "status": status,
        "run_slot": run_slot,
        "decision_session": "2026-07-31",
        "message": "공식 판정을 갱신했습니다.",
    }


def _signal() -> dict[str, object]:
    return {
        "signal_hash": "abc123",
        "decision_session": "2026-07-31",
        "planned_execution_session": "2026-08-03",
        "market_regime_label": "강세장",
        "active_strategy_label": "비교3 · RSI 전환",
        "overall_execution_target": "QLD",
        "router_target": None,
        "liquidity": {"percentile": 81.9230769231},
        "qqq": {"close": 700.25, "sma50": 680.5},
        "entry_advice": {"mode": "IMMEDIATE_100"},
        "rsi_reference": {"latest_rsi14": 61.2, "warning": True, "trend_label": "상승 둔화"},
    }


def test_primary_success_publishes_but_primary_failure_waits_for_retry():
    assert should_publish_notification(
        run_slot="primary-0737-kst",
        update_exit_code=0,
        latest_run=_run(),
    )
    assert not should_publish_notification(
        run_slot="primary-0737-kst",
        update_exit_code=2,
        latest_run=_run(status="SOURCE_FAILED"),
    )


def test_retry_only_publishes_when_retry_produced_latest_run():
    assert should_publish_notification(
        run_slot="retry-0757-kst",
        update_exit_code=0,
        latest_run=_run(run_slot="retry-0757-kst"),
    )
    assert not should_publish_notification(
        run_slot="retry-0757-kst",
        update_exit_code=0,
        latest_run=_run(run_slot="primary-0737-kst"),
    )


def test_manual_run_publishes_even_when_update_failed():
    assert should_publish_notification(
        run_slot="manual",
        update_exit_code=3,
        latest_run=_run(status="VALIDATION_FAILED", run_slot="manual"),
    )


def test_notification_contains_summary_mention_marker_and_links():
    body = render_meta_strategy_notification(
        latest_run=_run(),
        signal=_signal(),
        notification_date=date(2026, 8, 1),
        recipient="PJS-creator",
        repository="PJS-creator/krstock-fear-greed",
        run_url="https://github.com/PJS-creator/krstock-fear-greed/actions/runs/123",
    )

    assert body.startswith("<!-- meta-strategy-notification:2026-08-01:VALIDATED:2026-07-31:abc123 -->")
    assert "@PJS-creator" in body
    assert "시장구간: **강세장**" in body
    assert "최종 실행 목표자산: **QLD**" in body
    assert "적용 P: 81.9231" in body
    assert "RSI14 참고: 61.20 · 경고 · 상승 둔화" in body
    assert "signals/latest_validated.md" in body
    assert "actions/runs/123" in body


def test_failure_notification_labels_signal_as_previous_validated_result():
    body = render_meta_strategy_notification(
        latest_run=_run(status="SOURCE_FAILED", run_slot="retry-0757-kst"),
        signal=_signal(),
        notification_date="2026-08-01",
        recipient="PJS-creator",
        repository="PJS-creator/krstock-fear-greed",
        run_url="https://example.test/run",
    )

    assert "오늘 공식 갱신에 실패" in body
    assert "원자료 조회 실패" in body


def test_notification_script_writes_primary_output_and_removes_skipped_retry_output(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "runs").mkdir(parents=True)
    (data_root / "signals").mkdir(parents=True)
    (data_root / "runs" / "latest_run.json").write_text(
        json.dumps(_run(), ensure_ascii=False),
        encoding="utf-8",
    )
    (data_root / "signals" / "latest_validated.json").write_text(
        json.dumps(_signal(), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "notification.md"

    assert main(
        [
            "--data-root",
            str(data_root),
            "--run-slot",
            "primary-0737-kst",
            "--update-exit-code",
            "0",
            "--repository",
            "PJS-creator/krstock-fear-greed",
            "--run-url",
            "https://example.test/run",
            "--output",
            str(output),
        ]
    ) == 0
    assert output.exists()
    assert "@PJS-creator" in output.read_text(encoding="utf-8")

    assert main(
        [
            "--data-root",
            str(data_root),
            "--run-slot",
            "retry-0757-kst",
            "--update-exit-code",
            "0",
            "--repository",
            "PJS-creator/krstock-fear-greed",
            "--run-url",
            "https://example.test/run",
            "--output",
            str(output),
        ]
    ) == 0
    assert not output.exists()
