from __future__ import annotations

import pandas as pd
import streamlit as st

from .formatters import compact_krw, full_krw, percentage
from .theme import DEFAULT_THEME_MODE, SEMANTIC_COLORS, get_app_theme

PALETTE = SEMANTIC_COLORS
pct = percentage


def inject_styles(theme_mode: str = DEFAULT_THEME_MODE) -> None:
    theme = get_app_theme(theme_mode)
    css_vars = "\n".join(f"            --{name}: {value};" for name, value in theme.css_variables().items())
    st.markdown(
        """
        <style>
        @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/variable/pretendardvariable.css");
        :root {
            --app-font-family: "Pretendard Variable", Pretendard, "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
__CSS_VARS__
        }
        html, body, .stApp, [data-testid="stAppViewContainer"], button, input, textarea, select {
            font-family: var(--app-font-family);
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: var(--app-bg);
        }
        .stApp {
            font-size: 17px;
            color: var(--app-text);
            background: var(--app-bg-accent);
        }
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2rem;
        }
        .block-container h1 {
            color: var(--app-heading);
            font-size: 2.45rem;
            line-height: 1.08;
            word-break: keep-all;
            letter-spacing: 0;
        }
        .block-container h2,
        .block-container h3 {
            color: var(--app-heading);
            letter-spacing: 0;
        }
        .block-container p,
        .block-container li,
        .block-container label,
        .block-container span {
            letter-spacing: 0;
        }
        .section-gap { margin-top: 1.25rem; }
        .small-muted,
        div[data-testid="stCaptionContainer"],
        div[data-testid="stMarkdownContainer"] small {
            color: var(--app-muted);
        }
        div[data-testid="stMetric"] {
            background: var(--summary-panel-bg);
            border-color: var(--app-border) !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] * {
            color: var(--app-muted) !important;
            font-size: 0.98rem;
            opacity: 1 !important;
        }
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] * {
            color: var(--app-heading) !important;
            font-size: 1.55rem;
            font-weight: 760;
            letter-spacing: 0;
        }
        div[data-testid="stMetricDelta"] {
            color: var(--app-muted);
            font-size: 0.98rem;
            opacity: 1 !important;
        }
        div[data-testid="stMetricDelta"] * {
            opacity: 1 !important;
        }
        div[data-testid="stDataFrame"] { font-size: 0.98rem; }
        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border: 1px solid var(--app-border);
            border-radius: 8px;
            background: var(--app-panel);
            overflow: hidden;
        }
        div[data-testid="stExpander"] details {
            background: var(--summary-panel-bg);
            border: 1px solid var(--app-border);
            border-radius: 8px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        div[data-testid="stExpander"] summary {
            color: var(--app-heading);
            font-weight: 760;
        }
        section[data-testid="stSidebar"] {
            background: var(--app-surface);
            border-right: 1px solid var(--app-border);
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            color: var(--app-text);
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="select"] > div,
        div[data-baseweb="base-input"] {
            background: var(--app-input-bg) !important;
            border-color: var(--app-border) !important;
            color: var(--app-text) !important;
        }
        div[data-baseweb="input"],
        div[data-baseweb="textarea"],
        div[data-baseweb="select"] {
            color: var(--app-text);
        }
        div[data-testid="stButton"] button {
            border-radius: 8px;
            font-weight: 720;
            letter-spacing: 0;
        }
        div[data-testid="stButton"] button[kind="primary"] {
            background: linear-gradient(135deg, var(--app-primary), var(--app-primary-hover));
            border: 1px solid var(--app-primary-hover);
            color: #FFFFFF;
            box-shadow: 0 10px 24px rgba(37, 99, 235, 0.22);
        }
        div[data-testid="stButton"] button[kind="secondary"] {
            background: var(--app-panel);
            border-color: var(--app-border);
            color: var(--app-text);
        }
        div[data-testid="stButton"] button:hover {
            border-color: var(--app-primary-hover);
            color: var(--app-heading);
        }
        div[role="radiogroup"] {
            gap: 0.45rem;
        }
        div[role="radiogroup"] label {
            min-height: 2.45rem;
            padding: 0.45rem 0.74rem;
            border-radius: 8px;
            border: 1px solid var(--app-border);
            background: var(--app-panel);
            color: var(--app-text);
            font-weight: 760;
        }
        div[role="radiogroup"] label > div:first-child {
            display: none !important;
        }
        div[role="radiogroup"] label * {
            color: inherit !important;
        }
        div[role="radiogroup"] label p {
            margin: 0;
        }
        div[role="radiogroup"] label:hover {
            border-color: var(--app-primary-hover);
            background: var(--app-primary-soft);
        }
        div[role="radiogroup"] label:has(input:checked) {
            border-color: var(--app-primary-hover);
            background: var(--app-primary);
            color: #FFFFFF;
        }
        div[data-testid="stTabs"] [role="tablist"] {
            gap: 0.45rem;
            border-bottom: 1px solid var(--app-border);
        }
        div[data-testid="stTabs"] [role="tab"] {
            min-height: 2.55rem;
            padding: 0 0.9rem;
            border-radius: 8px 8px 0 0;
            color: var(--app-muted);
            font-weight: 760;
        }
        div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
            color: var(--app-heading);
            background: var(--app-primary-soft);
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
            border: 1px solid var(--app-border);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        }
        .app-theme-toggle-label {
            color: var(--app-muted);
            font-size: 0.82rem;
            font-weight: 760;
            margin-bottom: 0.25rem;
        }
        .app-header-panel {
            border: 1px solid var(--app-border);
            border-radius: 8px;
            padding: 0.85rem;
            background: var(--summary-panel-bg);
            box-shadow: var(--app-shadow);
        }
        @media (max-width: 720px) {
            .stApp { font-size: 16px; }
            .block-container {
                padding: 0.75rem 0.75rem 5.5rem;
                max-width: 100%;
            }
            .block-container h1 {
                font-size: 1.62rem;
                line-height: 1.16;
                margin-bottom: 0.25rem;
            }
            .block-container h2 { font-size: 1.35rem; }
            .block-container h3 { font-size: 1.08rem; }
            section[data-testid="stSidebar"] { display: none; }
            div[data-testid="stHorizontalBlock"] {
                gap: 0.65rem;
                flex-wrap: wrap;
            }
            div[data-testid="stHorizontalBlock"] > div {
                flex: 1 1 13rem !important;
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
                display: flex;
                flex-wrap: nowrap;
                overflow-x: auto;
                gap: 0.35rem;
                padding: 0.35rem 0;
                background: var(--app-surface);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid var(--app-border);
            }
            div[data-testid="stTabs"] [role="tab"] {
                flex: 0 0 auto;
                min-width: 5.8rem;
                min-height: 2.45rem;
                justify-content: center;
                border-radius: 8px;
                background: var(--app-panel);
                color: var(--app-text);
                font-weight: 760;
                padding: 0 0.35rem;
            }
            div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
                background: var(--app-primary);
                color: #FFFFFF;
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
                border: 1px solid var(--app-border);
                border-radius: 8px;
                padding: 0.9rem;
                background: var(--summary-panel-bg);
                box-shadow: var(--app-shadow);
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
                color: var(--app-heading);
                font-size: 1rem;
                font-weight: 850;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .mobile-holding-weight {
                flex: 0 0 auto;
                color: var(--app-primary);
                font-weight: 820;
                font-variant-numeric: tabular-nums;
            }
            .mobile-holding-value {
                color: var(--app-heading);
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
                background: var(--app-surface-alt);
                padding: 0.58rem 0.65rem;
            }
            .mobile-holding-cell span,
            .mobile-holding-line span {
                display: block;
                color: var(--app-muted);
                font-size: 0.76rem;
                font-weight: 760;
            }
            .mobile-holding-cell strong,
            .mobile-holding-line strong {
                color: var(--app-heading);
                font-size: 0.91rem;
                font-variant-numeric: tabular-nums;
                overflow-wrap: anywhere;
            }
            .mobile-holding-line {
                margin-top: 0.5rem;
            }
            .mobile-holding-up { color: var(--summary-up-text) !important; }
            .mobile-holding-down { color: var(--summary-down-text) !important; }
            .mobile-holding-neutral { color: var(--app-muted) !important; }
        }
        @media (min-width: 721px) {
            .mobile-holdings-cards { display: none; }
        }
        </style>
        """.replace("__CSS_VARS__", css_vars),
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
