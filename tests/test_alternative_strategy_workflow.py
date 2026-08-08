from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alternative_workflow_is_scheduled_and_persists_to_separate_branch():
    source = (
        ROOT / ".github" / "workflows" / "alternative-strategy-daily.yml"
    ).read_text(encoding="utf-8")

    assert 'cron: "47 7 * * *"' in source
    assert 'cron: "7 8 * * *"' in source
    assert 'timezone: "Asia/Seoul"' in source
    assert "alternative-strategy-data" in source
    assert "meta-strategy-data" not in source
    assert "scripts/update_alternative_strategy.py" in source
    assert "scripts/render_alternative_strategy_notification.py" in source
    assert "Alternative shadow v3.0 strategy daily signal" in source
    assert "N1/A1/V4" in source
    assert "issues/130/comments" in source
    assert "gh issue comment 130" in source
    assert "TIINGO_API_TOKEN" in source


def test_official_workflow_remains_on_official_branch_issue_and_schedule():
    source = (ROOT / ".github" / "workflows" / "meta-strategy-daily.yml").read_text(
        encoding="utf-8"
    )

    assert 'cron: "37 7 * * *"' in source
    assert 'cron: "57 7 * * *"' in source
    assert "meta-strategy-data" in source
    assert "alternative-strategy-data" not in source
    assert "issues/127/comments" in source
    assert "gh issue comment 127" in source
