from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_daily_workflow_has_kst_primary_retry_and_data_branch():
    source = (ROOT / ".github" / "workflows" / "meta-strategy-daily.yml").read_text(encoding="utf-8")

    assert 'cron: "37 7 * * *"' in source
    assert 'cron: "57 7 * * *"' in source
    assert 'timezone: "Asia/Seoul"' in source
    assert "meta-strategy-data" in source
    assert "TIINGO_API_TOKEN" in source
    assert "upload-artifact@v4" in source
    assert "retention-days: 90" in source
    assert "switch --orphan meta-strategy-data" in source
    assert "git -C meta-strategy-data rm -rf ." not in source
    assert "issues: write" in source
    assert "render_meta_strategy_notification.py" in source
    assert "gh issue comment 127" in source
    assert "meta-strategy-notification" in source
    assert "meta-strategy-existing-comments.txt" in source


def test_public_app_keeps_preview_and_loads_official_snapshot():
    source = (ROOT / "app" / "portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "fetch_meta_strategy()" in source
    assert "fetch_official_snapshot" in source
    assert "official_snapshot_to_app_view" in source
