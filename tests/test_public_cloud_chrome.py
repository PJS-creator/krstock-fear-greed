from pathlib import Path


def test_streamlit_toolbar_is_viewer_mode_for_public_cloud():
    config = Path(".streamlit/config.toml").read_text(encoding="utf-8")

    assert "[client]" in config
    assert 'toolbarMode = "viewer"' in config


def test_public_cloud_chrome_guard_hides_streamlit_controls():
    source = Path("app/ui/styles.py").read_text(encoding="utf-8")

    assert "def inject_public_cloud_chrome_guard" in source
    for selector in (
        '#MainMenu',
        'data-testid="stToolbar"',
        'title*="Share"',
        'title*="Edit"',
        'title*="GitHub"',
        'title*="Manage"',
        'title*="Manage app"',
        'aria-label*="Manage"',
        'aria-label*="Manage app"',
        'data-testid*="manage-app"',
        'href*="streamlit.io/cloud"',
        'data-testid="appCreatorAvatar"',
        'class*="viewerBadge"',
        'class*="profileContainer"',
    ):
        assert selector in source


def test_public_cloud_chrome_guard_reaches_streamlit_cloud_wrapper_best_effort():
    source = Path("app/ui/styles.py").read_text(encoding="utf-8")

    assert "import streamlit.components.v1 as components" in source
    assert "reachableDocuments" in source
    assert "hideLabelledCloudControls" in source
    assert "CLOUD_CONTROL_LABEL" in source
    assert "Manage app" in source
    assert "Reboot app" in source
    assert "Delete app" in source
    assert "Settings" in source
    assert "win.parent" in source
    assert "MutationObserver" in source
    assert "Best-effort UI cleanup only" in source


def test_public_dashboard_applies_chrome_guard_only_in_public_mode():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "from app.ui.styles import inject_public_cloud_chrome_guard, inject_styles" in source
    assert "if public_auth_enabled:\n    inject_public_cloud_chrome_guard()" in source
