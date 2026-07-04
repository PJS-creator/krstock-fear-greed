import math

import pandas as pd

from app.ui.charts import format_krw_axis, format_pct_axis, has_chart_data, is_all_zero_series, sanitize_chart_df


def test_sanitize_chart_df_removes_all_nan_rows_and_inf():
    frame = pd.DataFrame({"value": [1.0, math.inf, None], "label": ["ok", "bad", None]})
    clean = sanitize_chart_df(frame)

    assert len(clean) == 2
    assert pd.isna(clean.iloc[1]["value"])


def test_all_zero_series_detection_ignores_invalid_values():
    assert is_all_zero_series([0, 0.0, None, "bad"])
    assert not is_all_zero_series([0, 1])


def test_has_chart_data_rejects_empty_all_zero_and_missing_columns():
    assert not has_chart_data(pd.DataFrame({"value": [0, 0]}), required_columns=["value"])
    assert not has_chart_data(pd.DataFrame({"other": [1]}), required_columns=["value"])
    assert has_chart_data(pd.DataFrame({"value": [0, 10]}), required_columns=["value"])


def test_axis_formatters_are_stable():
    assert format_krw_axis(100_000_000) == "1.0억"
    assert format_krw_axis(35_000) == "4만"
    assert format_pct_axis(12.345) == "12.3%"
