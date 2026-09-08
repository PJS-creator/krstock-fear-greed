from streamlit.testing.v1 import AppTest


def test_refresh_button_continues_only_remaining_symbols_on_the_first_click():
    app = AppTest.from_string('''
from datetime import date
from unittest.mock import patch
import streamlit as st
from app.ui import chart_analysis as ui
from portfolio.chart_analysis import AnalysisInstrument, ChartAnalysisResult, ChartScoreSnapshot

st.session_state.setdefault("query_calls", [])
snapshot = ChartScoreSnapshot(
    as_of_session=date(2026, 9, 7), top_score=20, bottom_score=30,
    top_components={}, bottom_components={}, top_flow_break=False,
    top_damage_observed=False, bottom_watch=False, direction_conflict=False,
    verdict="ordinary",
)

def batch(payload, *args, **kwargs):
    st.session_state.query_calls.append(tuple(item[1] for item in payload))
    return tuple(ChartAnalysisResult(
        AnalysisInstrument(*item),
        readiness="READY_ELIGIBLE" if i == 0 else "PENDING",
        quality_status="PASS" if i == 0 else "FAIL",
        latest=snapshot if i == 0 else None,
    ) for i, item in enumerate(payload))

holdings = [{"market": "US", "ticker": symbol, "quantity": 1} for symbol in ("A", "B", "C")]
with patch.object(ui, "_load_chart_analysis", batch):
    ui.render_chart_analysis(holdings, auto_load=True)
''')
    app.run(timeout=20)
    assert not app.exception
    assert app.session_state["query_calls"] == [("A", "B", "C")]
    assert app.button(key="chart_analysis_refresh").label == "남은 2개 이어서 조회"
    assert any("조회 대기 2개" in item.value and "조회 실패 0개" in item.value for item in app.info)
    app.button(key="chart_analysis_refresh").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["query_calls"] == [("A", "B", "C"), ("B", "C")]
    assert app.button(key="chart_analysis_refresh").label == "남은 1개 이어서 조회"
    app.button(key="chart_analysis_refresh").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["query_calls"] == [("A", "B", "C"), ("B", "C"), ("C",)]
    assert all(row.latest is not None and not row.warnings for row in app.session_state["chart_analysis_results"])
    assert app.button(key="chart_analysis_refresh").label == "일봉 데이터 새로고침"
