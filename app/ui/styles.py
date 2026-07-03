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
        @media (max-width: 720px) {
            .stApp { font-size: 16px; background: #F8FAFC; }
            .block-container {
                padding: 0.75rem 0.75rem 5.5rem;
                max-width: 100%;
            }
            .block-container h1 {
                font-size: 1.85rem;
                line-height: 1.16;
                margin-bottom: 0.25rem;
            }
            .block-container h2 { font-size: 1.35rem; }
            .block-container h3 { font-size: 1.08rem; }
            section[data-testid="stSidebar"] { display: none; }
            div[data-testid="stHorizontalBlock"] {
                gap: 0.65rem;
                flex-direction: column;
            }
            div[data-testid="stHorizontalBlock"] > div {
                width: 100% !important;
                flex: 1 1 auto !important;
                min-width: 0 !important;
            }
            div[data-testid="stMetric"] {
                border-radius: 8px;
                padding: 0.78rem;
            }
            div[data-testid="stMetricValue"] {
                font-size: 1.28rem;
                line-height: 1.2;
                overflow-wrap: anywhere;
            }
            div[data-testid="stMetricDelta"] { font-size: 0.88rem; }
            div[data-testid="stButton"] button {
                min-height: 2.75rem;
                width: 100%;
            }
            div[data-testid="stTabs"] [role="tablist"] {
                position: sticky;
                top: 0;
                z-index: 20;
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.35rem;
                padding: 0.35rem 0;
                background: rgba(248, 250, 252, 0.96);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid rgba(148, 163, 184, 0.25);
            }
            div[data-testid="stTabs"] [role="tab"] {
                min-width: 0;
                min-height: 2.45rem;
                justify-content: center;
                border-radius: 8px;
                background: #EEF2F7;
                color: #334155;
                font-weight: 760;
                padding: 0 0.35rem;
            }
            div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
                background: #1D4ED8;
                color: #FFFFFF;
            }
            div[data-testid="stTabs"] [role="tab"]:nth-of-type(n+4) {
                display: none;
            }
            div[data-testid="stTabs"] [role="tab"]:nth-of-type(3) p {
                font-size: 0;
            }
            div[data-testid="stTabs"] [role="tab"]:nth-of-type(3) p::after {
                content: "보유자산 입력";
                font-size: 0.86rem;
            }
            div[data-testid="stDataFrame"],
            div[data-testid="stDataEditor"] {
                overflow-x: auto;
            }
            .mobile-holdings-cards {
                display: grid;
                grid-template-columns: 1fr;
                gap: 0.65rem;
                margin: 0.8rem 0;
            }
            .mobile-holding-card {
                border: 1px solid rgba(148, 163, 184, 0.22);
                border-radius: 8px;
                padding: 0.9rem;
                background: #FFFFFF;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
            }
            .mobile-holding-head,
            .mobile-holding-line {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.75rem;
            }
            .mobile-holding-name {
                min-width: 0;
                color: #0F172A;
                font-size: 1rem;
                font-weight: 850;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .mobile-holding-weight {
                flex: 0 0 auto;
                color: #1D4ED8;
                font-weight: 820;
                font-variant-numeric: tabular-nums;
            }
            .mobile-holding-value {
                color: #0F172A;
                font-size: 1.18rem;
                font-weight: 900;
                margin-top: 0.45rem;
                font-variant-numeric: tabular-nums;
            }
            .mobile-holding-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.5rem;
                margin-top: 0.7rem;
            }
            .mobile-holding-cell,
            .mobile-holding-line {
                border-radius: 7px;
                background: #F8FAFC;
                padding: 0.58rem 0.65rem;
            }
            .mobile-holding-cell span,
            .mobile-holding-line span {
                display: block;
                color: #64748B;
                font-size: 0.76rem;
                font-weight: 760;
            }
            .mobile-holding-cell strong,
            .mobile-holding-line strong {
                color: #0F172A;
                font-size: 0.91rem;
                font-variant-numeric: tabular-nums;
                overflow-wrap: anywhere;
            }
            .mobile-holding-line {
                margin-top: 0.5rem;
            }
            .mobile-holding-up { color: #DC2626 !important; }
            .mobile-holding-down { color: #2563EB !important; }
            .mobile-holding-neutral { color: #475569 !important; }
        }
        @media (min-width: 721px) {
            .mobile-holdings-cards { display: none; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_public_cloud_chrome_guard() -> None:
    st.markdown(
        """
        <style>
        #MainMenu,
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        div[data-testid="collapsedControl"],
        a[href*="share.streamlit.io"],
        a[href*="share.streamlit.io/user"],
        a[href*="streamlit.io/cloud"],
        a[href*="github.com"][href*="krstock-fear-greed"],
        a[href*="github.com/PJS-creator/krstock-fear-greed"],
        iframe[title="Streamlit Cloud Status"],
        button[title*="Deploy"],
        button[title*="Share"],
        button[title*="Edit"],
        button[title*="GitHub"],
        button[title*="Manage"],
        button[aria-label*="Deploy"],
        button[aria-label*="Share"],
        button[aria-label*="Edit"],
        button[aria-label*="GitHub"],
        button[aria-label*="Manage"],
        a[title*="Manage"],
        a[aria-label*="Manage"],
        [data-testid="appCreatorAvatar"],
        [data-testid*="manage-app"],
        [data-testid*="ManageApp"],
        [data-testid*="stDeployButton"],
        [class*="viewerBadge"],
        [class*="profileContainer"],
        [class*="profilePreview"],
        [data-testid*="stToolbarActionButton"] {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
        .block-container {
            padding-top: 1.25rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_dataframe(frame: pd.DataFrame) -> None:
    st.dataframe(frame, width="stretch", hide_index=True)
