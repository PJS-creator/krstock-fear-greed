from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from portfolio.external_strategy_scheduler import (
    STRATEGIES,
    kst_date,
    notification_marker,
    run_external_strategy_watchdog,
    watchdog_marker,
)
from portfolio.meta_strategy_notification import should_publish_notification


ROOT = Path(__file__).resolve().parents[1]


class FakeSchedulerClient:
    def __init__(self, comments_by_issue=None):
        self.comments_by_issue = comments_by_issue or {}
        self.dispatches = []
        self.posts = []

    def list_issue_comments(self, issue_number, notification_date):
        return list(self.comments_by_issue.get(issue_number, []))

    def dispatch_workflow(self, workflow, *, ref, run_slot):
        self.dispatches.append({"workflow": workflow, "ref": ref, "run_slot": run_slot})

    def post_issue_comment(self, issue_number, body):
        self.posts.append({"issue_number": issue_number, "body": body})


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


def test_kst_date_uses_the_date_seen_by_the_external_cron_jobs():
    assert kst_date(datetime(2026, 8, 28, 22, 50, tzinfo=timezone.utc)) == date(2026, 8, 29)
    assert kst_date(datetime(2026, 8, 28, 23, 20, tzinfo=timezone.utc)) == date(2026, 8, 29)


def test_ensure_dispatches_only_a_strategy_without_its_daily_notification():
    notification_date = date(2026, 8, 29)
    official = next(item for item in STRATEGIES if item.key == "official")
    client = FakeSchedulerClient(
        {official.issue_number: [{"body": f"{notification_marker(official, notification_date)}VALIDATED -->"}]}
    )

    results = run_external_strategy_watchdog(
        client=client,
        mode="ensure",
        repository="PJS-creator/krstock-fear-greed",
        target_ref="main",
        recipient="PJS-creator",
        notification_date=notification_date,
    )

    assert results == [
        {"strategy": "official", "received": True, "dispatched": False, "alerted": False},
        {"strategy": "alternative", "received": False, "dispatched": True, "alerted": False},
    ]
    assert client.dispatches == [
        {
            "workflow": "alternative-strategy-daily.yml",
            "ref": "main",
            "run_slot": "external-0750-kst",
        }
    ]
    assert client.posts == []


def test_watchdog_redispatches_and_posts_one_direct_github_alert():
    notification_date = date(2026, 8, 29)
    alternative = next(item for item in STRATEGIES if item.key == "alternative")
    client = FakeSchedulerClient(
        {
            alternative.issue_number: [
                {"body": f"{notification_marker(alternative, notification_date)}VALIDATED -->"}
            ]
        }
    )

    results = run_external_strategy_watchdog(
        client=client,
        mode="watchdog",
        repository="PJS-creator/krstock-fear-greed",
        target_ref="main",
        recipient="PJS-creator",
        notification_date=notification_date,
    )

    assert results[0] == {
        "strategy": "official",
        "received": False,
        "dispatched": True,
        "alerted": True,
    }
    assert results[1]["received"] is True
    assert client.dispatches[0]["run_slot"] == "external-watchdog-0820-kst"
    assert len(client.posts) == 1
    assert client.posts[0]["issue_number"] == 127
    assert "08:20 KST까지" in client.posts[0]["body"]
    assert "@PJS-creator" in client.posts[0]["body"]
    assert "strategy-schedule-watchdog:2026-08-29:official" in client.posts[0]["body"]


def test_watchdog_marker_prevents_duplicate_alert_but_keeps_recovery_dispatch():
    notification_date = date(2026, 8, 29)
    official = next(item for item in STRATEGIES if item.key == "official")
    alternative = next(item for item in STRATEGIES if item.key == "alternative")
    client = FakeSchedulerClient(
        {
            official.issue_number: [{"body": watchdog_marker(official, notification_date)}],
            alternative.issue_number: [
                {"body": f"{notification_marker(alternative, notification_date)}VALIDATED -->"}
            ],
        }
    )

    results = run_external_strategy_watchdog(
        client=client,
        mode="watchdog",
        repository="PJS-creator/krstock-fear-greed",
        target_ref="main",
        recipient="PJS-creator",
        notification_date=notification_date,
    )

    assert results[0]["dispatched"] is True
    assert results[0]["alerted"] is False
    assert client.posts == []


def test_unknown_external_mode_is_rejected():
    with pytest.raises(ValueError, match="Unsupported watchdog mode"):
        run_external_strategy_watchdog(
            client=FakeSchedulerClient(),
            mode="unknown",
            repository="PJS-creator/krstock-fear-greed",
            target_ref="main",
            recipient="PJS-creator",
            notification_date=date(2026, 8, 29),
        )


def test_daily_workflows_keep_internal_schedules_and_accept_documented_external_slots():
    expected_schedules = {
        "meta-strategy-daily.yml": ("37 7 * * *", "57 7 * * *"),
        "alternative-strategy-daily.yml": ("47 7 * * *", "7 8 * * *"),
    }
    for filename, schedules in expected_schedules.items():
        source = (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        assert all(schedule in source for schedule in schedules)
        assert "run_slot:" in source
        assert "external-0750-kst" in source
        assert "external-watchdog-0820-kst" in source
        assert "Unsupported workflow_dispatch run slot" in source


def test_cron_job_entry_workflow_has_minimal_recovery_permissions():
    source = (ROOT / ".github" / "workflows" / "external-strategy-watchdog.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in source
    assert "- ensure" in source
    assert "- watchdog" in source
    assert "actions: write" in source
    assert "contents: read" in source
    assert "issues: write" in source
    assert "run_external_strategy_watchdog.py" in source
    assert not (ROOT / "external-scheduler" / "wrangler.toml").exists()
    assert not (ROOT / "external-scheduler" / "src" / "index.js").exists()
    assert not (ROOT / ".github" / "workflows" / "deploy-external-strategy-scheduler.yml").exists()
