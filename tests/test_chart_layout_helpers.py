import plotly.graph_objects as go

from app.ui.charts import apply_chart_layout, is_all_zero_series
from app.ui.theme import DIMENSIONS, chart_config


def test_apply_chart_layout_sets_stable_margin_and_height():
    fig = apply_chart_layout(go.Figure(go.Scatter(x=[1, 2], y=[3, 4])), height=DIMENSIONS.tall_height)

    assert fig.layout.height == DIMENSIONS.tall_height
    assert fig.layout.margin.l >= 56
    assert fig.layout.margin.r >= 40
    assert fig.layout.margin.b >= 44
    assert fig.layout.xaxis.automargin is True
    assert fig.layout.yaxis.automargin is True


def test_chart_config_keeps_toolbar_minimal_and_responsive():
    config = chart_config()

    assert config["responsive"] is True
    assert config["displaylogo"] is False
    assert "lasso2d" in config["modeBarButtonsToRemove"]


def test_all_zero_chart_detection_ignores_invalid_values():
    assert is_all_zero_series([0, 0.0, None, "bad"])
    assert not is_all_zero_series([0, 1])
