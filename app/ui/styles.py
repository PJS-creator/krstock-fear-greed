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
        .block-container { padding-top: 1.25rem; padding-bottom: 2rem; }
        .section-gap { margin-top: 1.25rem; }
        .small-muted { color: var(--text-color); opacity: 0.72; font-size: 0.88rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_dataframe(frame: pd.DataFrame) -> None:
    st.dataframe(frame, width="stretch", hide_index=True)
