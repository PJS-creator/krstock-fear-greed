from __future__ import annotations

import pandas as pd
import streamlit as st

from .charts import plot_allocation, plot_contribution, plot_currency_exposure, plot_total_value_history
from .formatters import compact_krw, full_krw, percentage
from .theme import SEMANTIC_COLORS

PALETTE = SEMANTIC_COLORS
pct = percentage


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable.css");
        :root {
            --app-font-family: "Pretendard Variable", Pretendard, "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        html, body, .stApp, [data-testid="stAppViewContainer"], button, input, textarea, select {
            font-family: var(--app-font-family);
        }
        .stApp {
            font-size: 17px;
            color: #111827;
        }
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
        .block-container h1 { font-size: 3rem; line-height: 1.08; word-break: keep-all; letter-spacing: 0; }
        .block-container h2, .block-container h3 { letter-spacing: 0; }
        .section-gap { margin-top: 1.25rem; }
        .small-muted { color: var(--text-color); opacity: 0.72; font-size: 0.95rem; }
        div[data-testid="stMetricLabel"] p { font-size: 0.98rem; }
        div[data-testid="stMetricValue"] { font-size: 1.55rem; font-weight: 760; letter-spacing: 0; }
        div[data-testid="stMetricDelta"] { font-size: 0.98rem; }
        div[data-testid="stDataFrame"] { font-size: 0.98rem; }
        div[data-testid="stButton"] button {
            border-radius: 8px;
            font-weight: 720;
            letter-spacing: 0;
        }
        div[data-testid="stButton"] button[kind="primary"] {
            background: linear-gradient(135deg, #2563EB, #1D4ED8);
            border: 1px solid #3B82F6;
            color: #FFFFFF;
            box-shadow: 0 10px 24px rgba(37, 99, 235, 0.22);
        }
        div[data-testid="stButton"] button[kind="secondary"] {
            border-color: rgba(100, 116, 139, 0.38);
        }
        @media (max-width: 480px) {
            .block-container h1 { font-size: 2rem; line-height: 1.15; }
            .stApp { font-size: 16px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_dataframe(frame: pd.DataFrame) -> None:
    st.dataframe(frame, width="stretch", hide_index=True)
