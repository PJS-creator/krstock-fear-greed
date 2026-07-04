import logging

from app.ui.components import safe_render_section


def test_safe_render_section_returns_true_on_success():
    called = {"value": False}

    def render():
        called["value"] = True

    assert safe_render_section("ok", render) is True
    assert called["value"] is True


def test_safe_render_section_catches_exception_and_logs(caplog):
    def render():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        assert safe_render_section("broken", render, show_debug=False) is False

    assert "ui_section_error" in caplog.text
    assert "broken" in caplog.text
