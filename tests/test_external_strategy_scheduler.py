from pathlib import Path

from portfolio.meta_strategy_notification import should_publish_notification


ROOT = Path(__file__).resolve().parents[1]


def test_external_dispatch_slots_publish_notifications():
    latest_run = {"run_slot": "external-0750-kst"}

    assert should_publish_notification(
        run_slot="external-0750-kst",
        update_exit_code=0,
        latest_run=latest_run,
    )
    assert should_publish_notification(
        run_slot="external-watchdog-0820-kst",
        update_exit_code=1,
        latest_run=latest_run,
    )


def test_daily_workflows_accept_only_documented_external_slots():
    for filename in ("meta-strategy-daily.yml", "alternative-strategy-daily.yml"):
        source = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert "run_slot:" in source
        assert "external-0750-kst" in source
        assert "external-watchdog-0820-kst" in source
        assert "Unsupported workflow_dispatch run slot" in source


def test_external_worker_keeps_internal_schedules_and_direct_watchdog_alerts():
    source = (ROOT / "external-scheduler" / "src" / "index.js").read_text(encoding="utf-8")
    config = (ROOT / "external-scheduler" / "wrangler.toml").read_text(encoding="utf-8")

    assert 'crons = ["50 22 * * *", "20 23 * * *"]' in config
    assert "meta-strategy-daily.yml" in source
    assert "alternative-strategy-daily.yml" in source
    assert "08:20 KST까지" in source
    assert "strategy-schedule-watchdog" in source
    assert "/issues/${strategy.issueNumber}/comments" in source
