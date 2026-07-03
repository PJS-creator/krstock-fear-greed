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
        'aria-label*="Manage"',
        'data-testid*="manage-app"',
        'href*="streamlit.io/cloud"',
        'data-testid="appCreatorAvatar"',
        'class*="viewerBadge"',
        'class*="profileContainer"',
    ):
        assert selector in source


def test_public_cloud_chrome_guard_does_not_mutate_cloud_wrapper_documents():
    source = Path("app/ui/styles.py").read_text(encoding="utf-8")

    assert "streamlit.components.v1" not in source
    assert "reachableDocuments" not in source
    assert "hideLabelledCloudControls" not in source
    assert "MutationObserver" not in source
    assert "win.parent" not in source


def test_public_dashboard_applies_chrome_guard_only_in_public_mode():
    source = Path("app/portfolio_dashboard.py").read_text(encoding="utf-8")

    assert "from app.ui.styles import inject_public_cloud_chrome_guard, inject_styles" in source
    assert "if public_auth_enabled:\n    inject_public_cloud_chrome_guard()" in source
