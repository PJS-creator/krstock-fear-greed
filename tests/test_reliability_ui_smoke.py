import pytest
from streamlit.testing.v1 import AppTest
from app.portfolio_dashboard import PUBLIC_SECTION_KEY


@pytest.mark.parametrize("scenario", ["ready", "partial", "empty", "login"])
@pytest.mark.parametrize("mode", ["light", "dark"])
def test_public_fixture_states_render_without_exceptions(scenario, mode):
    app = AppTest.from_file("tests/browser/fixture_app.py")
    app.query_params["scenario"] = scenario
    app.query_params["theme"] = mode
    app.run(timeout=20)
    assert not app.exception
    assert app.session_state["app_theme_mode"] == mode
    first_revision = app.session_state["qa_render_id"]
    assert first_revision > 0
    assert any(f'data-qa-theme="{mode}"' in item.value for item in app.markdown)
    if scenario == "partial":
        assert any("부분 평가:" in item.value for item in app.warning)
    if scenario == "ready":
        summary_html = next(item.value for item in app.markdown if 'class="summary-card"' in item.value)
        assert all(not line.startswith("    ") for line in summary_html.splitlines())
        app.radio(key=PUBLIC_SECTION_KEY).set_value("chart_analysis").run(timeout=20)
        assert not app.exception
        app.radio(key="app_theme_choice").set_value("다크" if mode == "light" else "라이트").run(timeout=20)
        assert not app.exception
        assert app.session_state[PUBLIC_SECTION_KEY] == "chart_analysis"
        assert app.session_state["qa_render_id"] > first_revision
        expected_theme = "dark" if mode == "light" else "light"
        assert any(
            f'data-qa-theme="{expected_theme}"' in item.value and 'data-qa-section="chart_analysis"' in item.value
            for item in app.markdown
        )
