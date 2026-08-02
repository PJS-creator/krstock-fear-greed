from datetime import date
import json

from portfolio.alternative_strategy_notification import render_alternative_strategy_notification
from scripts.render_alternative_strategy_notification import main


def _run(*, status="VALIDATED", run_slot="primary-0747-kst"):
    return {
        "status": status,
        "run_slot": run_slot,
        "decision_session": "2026-07-31",
        "message": "대안 판정을 갱신했습니다.",
    }


def _signal():
    return {
        "signal_hash": "shadow123",
        "decision_session": "2026-07-31",
        "planned_execution_session": "2026-08-03",
        "market_regime_label": "강세장",
        "base_execution_target": "QLD",
        "resolved_execution_target": "QQQ",
        "n1_overlay": {"applied": True},
        "entry_filter_v4": {
            "triggered": True,
            "mode": "SPLIT_50_50",
            "immediate_weight_pct": 50.0,
            "immediate_target": "QQQ",
            "cash_weight_pct": 50.0,
            "deferred_due_session": "2026-10-27",
            "qqq_sma50_upper_distance_pct": 5.25,
        },
        "liquidity": {"percentile": 83.8461538462},
        "qqq": {"close": 700.25, "sma50": 665.32},
        "rsi_reference": {"latest_rsi14": 62.1, "warning": True, "trend_label": "상승 지속"},
    }


def test_alternative_notification_has_separate_marker_targets_and_branch():
    body = render_alternative_strategy_notification(
        latest_run=_run(),
        signal=_signal(),
        notification_date=date(2026, 8, 2),
        recipient="PJS-creator",
        repository="PJS-creator/krstock-fear-greed",
        run_url="https://example.test/run",
    )

    assert body.startswith(
        "<!-- alternative-strategy-notification:2026-08-02:VALIDATED:2026-07-31:shadow123 -->"
    )
    assert "N1 전 기준 목표: **QLD**" in body
    assert "N1 오버레이: **적용**" in body
    assert "대안 resolved target: **QQQ**" in body
    assert "신규진입 V4: **발동**" in body
    assert "alternative-strategy-data/signals/latest_validated.md" in body
    assert "공식 메타전략 판정은 변경하지 않습니다" in body


def test_alternative_notification_script_writes_and_skips_duplicate_retry(tmp_path):
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
    common = [
        "--data-root",
        str(data_root),
        "--repository",
        "PJS-creator/krstock-fear-greed",
        "--run-url",
        "https://example.test/run",
        "--output",
        str(output),
    ]

    assert main(
        [
            *common,
            "--run-slot",
            "primary-0747-kst",
            "--update-exit-code",
            "0",
        ]
    ) == 0
    assert output.exists()

    assert main(
        [
            *common,
            "--run-slot",
            "retry-0807-kst",
            "--update-exit-code",
            "0",
        ]
    ) == 0
    assert not output.exists()
