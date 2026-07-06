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
        html {
            scroll-padding-bottom: calc(var(--token-space-12) + 96px);
        }
        html, body, [data-testid="stAppViewContainer"] {
            background: var(--app-bg);
        }
        .stApp {
            font-size: var(--token-font-md);
            color: var(--app-text);
            background: var(--app-bg-accent);
        }
        .block-container {
            max-width: var(--token-page-max-width);
            padding-top: var(--token-space-8);
            padding-left: var(--token-page-padding-x-desktop);
            padding-right: var(--token-page-padding-x-desktop);
            padding-bottom: calc(var(--token-space-12) + 72px);
            position: relative;
        }
        .block-container h1 {
            color: var(--app-heading);
            font-size: clamp(var(--token-font-2xl), 3.4vw, var(--token-font-3xl));
            line-height: var(--token-line-height-tight);
            word-break: keep-all;
            letter-spacing: 0;
        }
        .block-container h2,
        .block-container h3 {
            color: var(--app-heading);
            letter-spacing: 0;
            line-height: var(--token-line-height-tight);
        }
        .block-container h2 { font-size: clamp(var(--token-font-xl), 2.1vw, var(--token-font-2xl)); }
        .block-container h3 { font-size: clamp(var(--token-font-lg), 1.6vw, var(--token-font-xl)); }
        .block-container p,
        .block-container li,
        .block-container label,
        .block-container span {
            letter-spacing: 0;
        }
        .section-gap { margin-top: var(--token-section-gap); }
        .small-muted,
        div[data-testid="stCaptionContainer"],
        div[data-testid="stMarkdownContainer"] small {
            color: var(--app-muted);
        }
        div[data-testid="stMetric"] {
            background: var(--summary-panel-bg);
            border-color: var(--app-border) !important;
            box-shadow: var(--app-shadow-sm);
            min-height: 118px;
            height: 100%;
            padding: var(--token-card-padding-compact) var(--token-card-padding) !important;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
            align-items: stretch;
            gap: var(--token-space-1);
        }
        div[data-testid="stMetric"] > div {
            width: 100%;
        }
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] *,
        div[data-testid="stMetricLabel"] svg,
        div[data-testid="stMetricLabel"] path {
            color: var(--app-heading) !important;
            fill: var(--app-heading) !important;
            stroke: var(--app-heading) !important;
            font-size: 0.98rem;
            font-weight: 760;
            line-height: var(--token-line-height-normal);
            opacity: 1 !important;
        }
        div[data-testid="stMetricLabel"] p,
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] label *,
        div[data-testid="stMetric"] [data-testid="stMetricDelta"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] * {
            opacity: 1 !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {
            display: none !important;
        }
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] * {
            color: var(--app-heading) !important;
            font-size: 1.55rem;
            font-weight: 760;
            letter-spacing: 0;
        }
        div[data-testid="stMetricDelta"] {
            color: var(--app-primary);
            font-size: 0.98rem;
            opacity: 1 !important;
        }
        div[data-testid="stMetricDelta"] * {
            opacity: 1 !important;
        }
        [data-testid="stTooltipIcon"],
        [data-testid="stTooltipIcon"] *,
        [data-testid="stTooltipHoverTarget"],
        [data-testid="stTooltipHoverTarget"] *,
        button[data-testid="stTooltipIcon"],
        button[data-testid="stTooltipIcon"] * {
            color: var(--app-primary) !important;
            fill: var(--app-primary) !important;
            stroke: var(--app-primary) !important;
            opacity: 1 !important;
        }
        .st-key-public_login_remember_me,
        .st-key-public_signup_remember_me {
            margin: var(--token-space-3) 0 var(--token-space-2);
        }
        .st-key-public_login_remember_me label,
        .st-key-public_signup_remember_me label {
            min-height: var(--token-control-height-md);
            align-items: center !important;
            gap: var(--token-space-2) !important;
        }
        .st-key-public_login_remember_me label p,
        .st-key-public_signup_remember_me label p,
        .st-key-public_login_remember_me div[data-testid="stWidgetLabel"] *,
        .st-key-public_signup_remember_me div[data-testid="stWidgetLabel"] * {
            color: var(--app-heading) !important;
            font-size: var(--token-font-base) !important;
            font-weight: 720 !important;
            line-height: var(--token-line-height-normal) !important;
        }
        .st-key-public_login_remember_me [data-testid="stTooltipIcon"],
        .st-key-public_signup_remember_me [data-testid="stTooltipIcon"],
        .st-key-public_login_remember_me [data-testid="stTooltipHoverTarget"],
        .st-key-public_signup_remember_me [data-testid="stTooltipHoverTarget"] {
            width: var(--token-font-lg) !important;
            height: var(--token-font-lg) !important;
            min-width: var(--token-font-lg) !important;
            min-height: var(--token-font-lg) !important;
            display: inline-grid !important;
            place-items: center !important;
            border-radius: var(--token-radius-pill) !important;
            background: var(--app-primary-soft) !important;
            color: var(--app-primary) !important;
            font-size: var(--token-font-sm) !important;
            font-weight: 850 !important;
            line-height: 1 !important;
            vertical-align: middle !important;
        }
        .st-key-public_login_remember_me [data-testid="stTooltipIcon"] svg,
        .st-key-public_signup_remember_me [data-testid="stTooltipIcon"] svg,
        .st-key-public_login_remember_me [data-testid="stTooltipHoverTarget"] svg,
        .st-key-public_signup_remember_me [data-testid="stTooltipHoverTarget"] svg {
            display: none !important;
        }
        .st-key-public_login_remember_me [data-testid="stTooltipIcon"]::after,
        .st-key-public_signup_remember_me [data-testid="stTooltipIcon"]::after,
        .st-key-public_login_remember_me [data-testid="stTooltipHoverTarget"]::after,
        .st-key-public_signup_remember_me [data-testid="stTooltipHoverTarget"]::after {
            content: "?";
        }
        .journal-event {
            margin: var(--token-space-3) 0 var(--token-space-2);
            padding: var(--token-card-padding-compact) var(--token-card-padding);
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-md);
            background: var(--app-panel);
            box-shadow: var(--app-shadow-sm);
        }
        .journal-event-head,
        .journal-event-meta {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: var(--token-space-2);
            color: var(--app-muted);
            font-size: var(--token-font-sm);
            font-weight: 720;
        }
        .journal-event-head strong {
            color: var(--app-primary);
        }
        .journal-event-title {
            margin-top: var(--token-space-2);
            color: var(--app-heading);
            font-size: var(--token-font-base);
            font-weight: 820;
            word-break: keep-all;
        }
        .journal-event-subtitle {
            margin-top: var(--token-space-1);
            color: var(--app-text);
            font-size: var(--token-font-sm);
            overflow-wrap: anywhere;
        }
        .journal-event-meta {
            margin-top: var(--token-space-2);
        }
        div[data-testid="stDataFrame"] { font-size: var(--token-font-sm); }
        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-md);
            background: var(--app-panel);
            overflow: hidden;
            margin-bottom: var(--token-space-4);
        }
        div[data-testid="stDataFrame"] *,
        div[data-testid="stDataEditor"] *,
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataEditor"] [role="gridcell"],
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataEditor"] [role="columnheader"] {
            color: var(--app-text) !important;
            border-color: var(--app-border) !important;
        }
        div[data-testid="stDataFrame"] [role="grid"],
        div[data-testid="stDataEditor"] [role="grid"],
        div[data-testid="stDataFrame"] [role="rowgroup"],
        div[data-testid="stDataEditor"] [role="rowgroup"],
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataEditor"] [role="gridcell"],
        div[data-testid="stDataFrame"] canvas,
        div[data-testid="stDataEditor"] canvas {
            background: var(--app-panel) !important;
        }
        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataEditor"] [role="columnheader"] {
            background: var(--app-table-header) !important;
            color: var(--app-heading) !important;
            font-weight: 780 !important;
            min-height: var(--token-table-min-row-height) !important;
            white-space: nowrap !important;
        }
        div[data-testid="stDataFrame"] [role="row"],
        div[data-testid="stDataEditor"] [role="row"] {
            background: var(--app-panel) !important;
            min-height: var(--token-table-min-row-height) !important;
        }
        div[data-testid="stDataFrame"] [role="row"]:hover,
        div[data-testid="stDataEditor"] [role="row"]:hover {
            background: var(--app-table-hover) !important;
        }
        .app-data-table-wrap {
            width: 100%;
            overflow-x: auto;
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-md);
            background: var(--app-panel);
            box-shadow: var(--app-shadow-sm);
            margin-bottom: var(--token-space-4);
        }
        .app-data-table {
            width: 100%;
            border-collapse: collapse;
            color: var(--app-text);
            font-size: var(--token-font-sm);
            line-height: var(--token-line-height-normal);
            font-variant-numeric: tabular-nums;
        }
        .app-data-table th,
        .app-data-table td {
            min-height: var(--token-table-min-row-height);
            padding: 10px 12px;
            border-bottom: 1px solid var(--app-border);
            background: var(--app-panel);
            color: var(--app-text);
            vertical-align: middle;
            white-space: nowrap;
        }
        .app-data-table th {
            background: var(--app-table-header);
            color: var(--app-heading);
            font-weight: 800;
            text-align: left;
        }
        .app-data-table tr:nth-child(even) td {
            background: var(--token-table-row-alt-bg);
        }
        .app-data-table tbody tr:hover td {
            background: var(--app-table-hover);
        }
        .app-data-table tbody tr:last-child td {
            border-bottom: 0;
        }
        .app-data-table .num,
        .app-data-table .pct {
            text-align: right;
        }
        .app-data-table .center {
            text-align: center;
        }
        .app-table-progress {
            display: inline-grid;
            grid-template-columns: minmax(5.2rem, 1fr) 3.5rem;
            align-items: center;
            gap: var(--token-space-2);
            width: 100%;
            min-width: 9rem;
        }
        .app-table-progress-track {
            height: 0.42rem;
            border-radius: var(--token-radius-pill);
            background: var(--app-surface-alt);
            border: 1px solid var(--app-border);
            overflow: hidden;
        }
        .app-table-progress-fill {
            display: block;
            height: 100%;
            border-radius: inherit;
            background: var(--app-primary);
        }
        .app-table-progress-value {
            color: var(--app-text);
            font-weight: 760;
            text-align: right;
        }
        div[data-testid="stWidgetLabel"],
        div[data-testid="stWidgetLabel"] *,
        div[data-testid="stForm"] label,
        div[data-testid="stForm"] label *,
        div[data-testid="stTextInput"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stSelectbox"] label,
        div[data-testid="stTextArea"] label,
        div[data-baseweb="form-control"] label,
        div[data-baseweb="form-control"] label * {
            color: var(--app-text) !important;
            opacity: 1 !important;
            font-size: var(--token-font-sm) !important;
            line-height: var(--token-line-height-normal) !important;
        }
        div[data-testid="stExpander"] details {
            background: var(--summary-panel-bg);
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-md);
            box-shadow: var(--app-shadow-sm);
            margin-bottom: var(--token-space-3);
        }
        div[data-testid="stExpander"] details > summary,
        div[data-testid="stExpander"] details > summary:hover,
        div[data-testid="stExpander"] details[open] > summary {
            background: var(--app-panel) !important;
            color: var(--app-heading) !important;
            border-radius: var(--token-radius-md) var(--token-radius-md) 0 0;
            font-weight: 760;
        }
        div[data-testid="stExpander"] details[open] > summary {
            border-bottom: 1px solid var(--app-border) !important;
        }
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] summary *,
        div[data-testid="stExpander"] summary svg,
        div[data-testid="stExpander"] summary path {
            color: var(--app-heading) !important;
            fill: var(--app-heading) !important;
            stroke: var(--app-heading) !important;
            opacity: 1 !important;
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
            border-color: var(--token-input-border) !important;
            color: var(--app-text) !important;
            min-height: var(--token-input-height-md) !important;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"],
        div[data-testid="stNumberInput"] div[data-baseweb="input"],
        div[data-testid="stTextArea"] div[data-baseweb="textarea"],
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
        div[data-testid="stDateInput"] div[data-baseweb="input"] {
            background: var(--app-input-bg) !important;
            border: 1px solid var(--token-input-border) !important;
            border-radius: var(--token-radius-md) !important;
            box-shadow: inset 0 0 0 1px var(--token-input-border) !important;
        }
        div[data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
        div[data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within,
        div[data-testid="stTextArea"] div[data-baseweb="textarea"]:focus-within,
        div[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within > div,
        div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {
            border-color: var(--token-input-focus) !important;
            box-shadow: inset 0 0 0 1px var(--token-input-focus), 0 0 0 3px var(--app-primary-soft) !important;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stDateInput"] input {
            background: transparent !important;
        }
        div[data-baseweb="input"],
        div[data-baseweb="textarea"],
        div[data-baseweb="select"] {
            color: var(--app-text);
        }
        div[data-baseweb="select"] *,
        div[data-baseweb="popover"] li,
        div[data-baseweb="popover"] li * {
            color: var(--app-text) !important;
        }
        div[data-baseweb="popover"] {
            background: var(--app-panel) !important;
        }
        input::placeholder,
        textarea::placeholder {
            color: var(--app-muted) !important;
            opacity: 1 !important;
        }
        div[data-testid="stButton"] button {
            min-height: var(--token-button-height-md);
            border-radius: var(--token-radius-md);
            font-weight: 720;
            letter-spacing: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.45rem;
            text-align: center;
            white-space: nowrap;
        }
        div[data-testid="stButton"] button p {
            margin: 0;
        }
        div[data-testid="stButton"] button[kind="primary"] {
            background: linear-gradient(135deg, var(--app-primary), var(--app-primary-hover));
            border: 1px solid var(--app-primary-hover);
            color: var(--app-primary-text);
            box-shadow: var(--app-primary-shadow);
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
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stFileUploader"] button {
            min-height: var(--token-button-height-md);
            border-radius: var(--token-radius-md);
            font-weight: 720;
        }
        div[data-testid="stFileUploader"] section {
            border-radius: var(--token-radius-md);
            border-color: var(--app-border) !important;
            background: var(--app-panel) !important;
        }
        div[role="radiogroup"] {
            gap: var(--token-space-2);
        }
        div[role="radiogroup"] label {
            box-sizing: border-box;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            min-height: var(--token-control-height-md);
            padding: var(--token-space-2) var(--token-space-3);
            border-radius: var(--token-radius-md);
            border: 1px solid var(--app-border);
            background: var(--app-panel);
            color: var(--app-text);
            font-weight: 760;
            text-align: center;
        }
        div[role="radiogroup"] label > div:first-child {
            display: none !important;
        }
        div[role="radiogroup"] label > div {
            margin: 0 !important;
            padding: 0 !important;
        }
        div[role="radiogroup"] label * {
            color: inherit !important;
        }
        div[role="radiogroup"] label div[data-testid="stMarkdownContainer"] {
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
        }
        div[role="radiogroup"] label p {
            margin: 0;
            width: 100%;
            text-align: center;
        }
        div[role="radiogroup"] label:hover {
            border-color: var(--app-primary-hover);
            background: var(--app-primary-soft);
        }
        div[role="radiogroup"] label:has(input:checked) {
            border-color: var(--app-primary-hover);
            background: var(--app-primary);
            color: var(--app-primary-text);
        }
        div[data-testid="stTabs"] [role="tablist"] {
            gap: var(--token-space-2);
            border-bottom: 1px solid var(--app-border);
        }
        div[data-testid="stTabs"] [role="tab"] {
            min-height: var(--token-tab-height);
            padding: 0 var(--token-space-4);
            border-radius: var(--token-radius-md) var(--token-radius-md) 0 0;
            color: var(--app-muted);
            font-weight: 760;
        }
        div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
            color: var(--app-heading);
            background: var(--app-primary-soft);
        }
        div[data-testid="stAlert"] {
            border-radius: var(--token-radius-md);
            border: 1px solid var(--app-border);
            background: var(--app-panel) !important;
            color: var(--app-text) !important;
            box-shadow: var(--app-shadow-sm);
        }
        div[data-testid="stAlert"] *,
        div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] *,
        div[data-testid="stAlert"] div,
        div[data-testid="stAlert"] p {
            color: var(--app-text) !important;
            opacity: 1 !important;
        }
        div[data-testid="stAlert"] svg {
            color: var(--app-warning) !important;
            fill: var(--app-warning) !important;
        }
        .app-empty-state {
            padding: var(--token-card-padding);
            margin: var(--token-space-3) 0 var(--token-space-4);
            border: 1px dashed var(--app-border-strong);
            border-radius: var(--token-radius-md);
            background: var(--app-panel);
            color: var(--app-text);
        }
        .app-empty-title {
            color: var(--app-heading);
            font-weight: 850;
            font-size: var(--token-font-lg);
            margin-bottom: var(--token-space-1);
        }
        .app-empty-message {
            color: var(--app-muted);
            line-height: 1.55;
        }
        .app-box {
            display: grid;
            gap: var(--token-space-1);
            padding: var(--token-space-3) var(--token-space-4);
            margin: var(--token-space-3) 0 var(--token-space-4);
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-md);
            color: var(--app-text);
        }
        .app-box strong {
            color: var(--app-heading);
        }
        .app-box span {
            color: var(--app-text);
        }
        .app-box-info { background: var(--token-info-soft); border-color: var(--app-info); }
        .app-box-warning { background: var(--token-warning-soft); border-color: var(--app-warning); }
        .app-box-danger { background: var(--token-danger-soft); border-color: var(--app-danger); }
        .app-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 1.55rem;
            padding: 0.2rem var(--token-space-2);
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-pill);
            color: var(--app-text);
            background: var(--app-panel-strong);
            font-size: var(--token-font-xs);
            font-weight: 800;
            line-height: 1.2;
        }
        .app-badge-success { color: var(--token-success-text); background: var(--token-success-soft); border-color: var(--app-success); }
        .app-badge-warning { color: var(--token-warning-text); background: var(--token-warning-soft); border-color: var(--app-warning); }
        .app-badge-danger { color: var(--token-danger-text); background: var(--token-danger-soft); border-color: var(--app-danger); }
        .app-badge-info { color: var(--token-info-text); background: var(--token-info-soft); border-color: var(--app-info); }
        .app-header-status {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--token-space-2);
            min-height: var(--token-control-height-md);
        }
        .app-header-save {
            color: var(--token-text-muted);
            font-size: var(--token-font-sm);
            font-weight: 740;
        }
        .app-header-refresh-meta {
            color: var(--app-muted);
            font-size: var(--token-font-sm);
            font-weight: 760;
            line-height: 1.35;
            text-align: left;
            word-break: keep-all;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: var(--token-card-gap);
        }
        .app-metric-card {
            min-height: 120px;
            padding: var(--token-card-padding);
            border: 1px solid var(--token-border);
            border-left: 4px solid var(--token-border-strong);
            border-radius: var(--token-radius-md);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--token-surface-raised) 100%);
            box-shadow: var(--app-shadow);
            color: var(--token-text);
        }
        .app-metric-success {
            border-left-color: var(--token-success);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--token-success-soft) 100%);
        }
        .app-metric-warning {
            border-left-color: var(--token-warning);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--token-warning-soft) 100%);
        }
        .app-metric-danger {
            border-left-color: var(--token-danger);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--token-danger-soft) 100%);
        }
        .app-metric-info {
            border-left-color: var(--token-primary);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--token-info-soft) 100%);
        }
        .app-metric-profit {
            border-left-color: var(--app-profit);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--app-profit-soft) 100%);
        }
        .app-metric-loss {
            border-left-color: var(--app-loss);
            background: linear-gradient(135deg, var(--token-surface) 0%, var(--app-loss-soft) 100%);
        }
        .app-metric-title {
            color: var(--app-heading);
            font-size: var(--token-font-sm);
            font-weight: 760;
            line-height: 1.25;
        }
        .app-metric-info .app-metric-delta { color: var(--app-primary); }
        .app-metric-success .app-metric-delta { color: var(--token-success-text); }
        .app-metric-warning .app-metric-delta { color: var(--token-warning-text); }
        .app-metric-danger .app-metric-delta { color: var(--token-danger-text); }
        .app-metric-profit .app-metric-delta { color: var(--app-profit); }
        .app-metric-loss .app-metric-delta { color: var(--app-loss); }
        .app-metric-value {
            color: var(--token-text);
            font-size: clamp(1.14rem, 1.5vw, 1.42rem);
            font-weight: 880;
            line-height: 1.18;
            margin-top: 0.45rem;
            overflow-wrap: anywhere;
            font-variant-numeric: tabular-nums;
        }
        .app-metric-delta {
            color: var(--token-text-subtle);
            font-size: var(--token-font-sm);
            font-weight: 760;
            margin-top: 0.4rem;
        }
        .app-metric-help {
            color: var(--token-text-muted);
            font-size: var(--token-font-xs);
            line-height: 1.35;
            margin-top: 0.55rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .app-theme-toggle-label {
            color: var(--app-muted);
            font-size: 0.82rem;
            font-weight: 760;
            margin-bottom: 0.25rem;
        }
        .st-key-app_theme_topbar {
            position: absolute;
            top: var(--token-space-4);
            right: 0;
            z-index: 30;
            width: auto !important;
            max-width: 9.6rem;
        }
        .st-key-app_theme_topbar div[role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(2, 4.45rem);
            justify-content: flex-end;
            gap: var(--token-space-2);
        }
        .st-key-app_theme_topbar div[role="radiogroup"] label {
            width: 4.45rem;
            min-height: var(--token-button-height-sm);
            padding: 0 var(--token-space-2);
            font-size: var(--token-font-sm);
            box-shadow: var(--app-shadow);
            white-space: nowrap;
            line-height: 1;
        }
        .st-key-app_theme_topbar div[role="radiogroup"] label > div,
        .st-key-app_theme_topbar div[role="radiogroup"] label p {
            white-space: nowrap !important;
            word-break: keep-all !important;
            line-height: 1 !important;
        }
        .st-key-app_header_refresh button {
            width: 190px !important;
            min-width: 190px !important;
            max-width: 220px !important;
            min-height: var(--token-button-height-lg) !important;
            padding: 0 var(--token-space-4) !important;
            font-size: var(--token-font-md) !important;
        }
        .st-key-public_section_tabs {
            margin: var(--token-space-5) 0 var(--token-space-6);
        }
        .st-key-public_section_tabs div[role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0;
            width: 100%;
            padding: 0;
            border-bottom: 1px solid var(--app-border);
            background: transparent;
            box-shadow: none;
        }
        .st-key-public_section_tabs div[role="radiogroup"] label {
            position: relative;
            width: 100%;
            min-width: 0;
            min-height: var(--token-tab-height);
            padding: 0 var(--token-space-2) var(--token-space-2);
            border: 0;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
            color: var(--app-muted);
            font-size: var(--token-font-base);
            font-weight: 820;
            white-space: nowrap;
        }
        .st-key-public_section_tabs div[role="radiogroup"] label::after {
            content: "";
            position: absolute;
            left: 0;
            right: 0;
            bottom: -1px;
            height: 3px;
            border-radius: 999px 999px 0 0;
            background: transparent;
        }
        .st-key-public_section_tabs div[role="radiogroup"] label:hover {
            background: transparent;
            color: var(--app-heading);
        }
        .st-key-public_section_tabs div[role="radiogroup"] label:has(input:checked) {
            background: transparent;
            color: var(--app-heading);
        }
        .st-key-public_section_tabs div[role="radiogroup"] label:has(input:checked)::after {
            background: var(--app-primary);
        }
        .st-key-public_input_tabs {
            margin: 0 0 var(--token-space-5);
        }
        .st-key-public_input_tabs div[role="radiogroup"] {
            display: grid !important;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0;
            width: 100%;
            padding: 0;
            border-bottom: 1px solid var(--app-border);
            background: transparent;
        }
        .st-key-public_input_tabs div[role="radiogroup"] label {
            position: relative;
            width: 100%;
            min-width: 0;
            min-height: var(--token-subtab-height);
            padding: 0 var(--token-space-2) var(--token-space-2);
            border: 0;
            border-radius: 0;
            background: transparent;
            box-shadow: none;
            color: var(--app-muted);
            font-size: var(--token-font-sm);
            font-weight: 760;
            white-space: nowrap;
        }
        .st-key-public_input_tabs div[role="radiogroup"] label::after {
            content: "";
            position: absolute;
            left: 12%;
            right: 12%;
            bottom: -1px;
            height: 2px;
            border-radius: 999px 999px 0 0;
            background: transparent;
        }
        .st-key-public_input_tabs div[role="radiogroup"] label:hover {
            background: transparent;
            color: var(--app-heading);
        }
        .st-key-public_input_tabs div[role="radiogroup"] label:has(input:checked) {
            background: transparent;
            color: var(--app-heading);
        }
        .st-key-public_input_tabs div[role="radiogroup"] label:has(input:checked)::after {
            background: var(--app-primary);
        }
        .app-header-panel {
            border: 1px solid var(--app-border);
            border-radius: var(--token-radius-md);
            padding: var(--token-card-padding-compact);
            background: var(--summary-panel-bg);
            box-shadow: var(--app-shadow);
        }
        .app-table-note {
            color: var(--app-muted);
            font-size: var(--token-font-sm);
            margin: var(--token-space-2) 0 var(--token-space-4);
        }
        @media (max-width: 720px) {
            .stApp { font-size: 16px; }
            .block-container {
                padding-top: var(--token-space-5);
                padding-left: var(--token-page-padding-x-mobile);
                padding-right: var(--token-page-padding-x-mobile);
                padding-bottom: calc(var(--token-space-12) + 96px);
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
                min-height: var(--token-button-height-lg);
                width: 100%;
            }
            .st-key-app_theme_topbar {
                top: 0.72rem;
                right: 0.75rem;
                max-width: 9.1rem;
            }
            .st-key-app_theme_topbar div[role="radiogroup"] {
                grid-template-columns: repeat(2, 4.35rem);
                gap: 0.3rem;
            }
            .st-key-app_theme_topbar div[role="radiogroup"] label {
                width: 4.35rem;
                min-height: 2.15rem;
                padding: 0.34rem 0.2rem;
                font-size: 0.82rem;
            }
            .app-header-status {
                gap: 0.38rem;
                min-height: auto;
            }
            .app-header-status .app-badge {
                justify-content: flex-start;
                max-width: 100%;
                padding: 0.28rem 0.58rem;
                font-size: 0.78rem;
                line-height: 1.36;
                text-align: left;
            }
            .app-header-save {
                width: 100%;
                font-size: 0.84rem;
            }
            .app-header-refresh-meta {
                font-size: 0.74rem;
                line-height: 1.3;
                text-align: left;
            }
            .st-key-app_header_refresh {
                display: flex;
                justify-content: center;
            }
            .st-key-app_header_refresh button {
                width: 100% !important;
                min-width: 0 !important;
                max-width: none !important;
                min-height: var(--token-button-height-lg) !important;
                padding: 0 var(--token-space-4) !important;
                font-size: var(--token-font-base) !important;
                box-shadow: var(--app-primary-shadow) !important;
            }
            .st-key-public_section_tabs {
                margin: 0.7rem 0 0.95rem;
            }
            .st-key-public_section_tabs div[role="radiogroup"] {
                display: flex !important;
                grid-template-columns: none;
                flex-wrap: nowrap;
                justify-content: flex-start;
                gap: var(--token-space-4);
                overflow-x: auto;
                overflow-y: hidden;
                padding: 0 0.1rem;
                scrollbar-width: none;
                scroll-snap-type: x proximity;
            }
            .st-key-public_section_tabs div[role="radiogroup"]::-webkit-scrollbar {
                display: none;
            }
            .st-key-public_section_tabs div[role="radiogroup"] label {
                flex: 0 0 auto;
                width: auto;
                min-width: max-content;
                min-height: var(--token-tab-height);
                padding: 0 var(--token-space-1) var(--token-space-2);
                font-size: var(--token-font-base);
                letter-spacing: 0;
                scroll-snap-align: start;
            }
            .st-key-public_input_tabs {
                margin: 0 0 0.85rem;
            }
            .st-key-public_input_tabs div[role="radiogroup"] {
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }
            .st-key-public_input_tabs div[role="radiogroup"] label {
                min-height: 2.16rem;
                padding: 0 var(--token-space-1) var(--token-space-1);
                font-size: clamp(0.72rem, 2.85vw, 0.82rem);
            }
            div[data-testid="stTabs"] [role="tablist"] {
                position: sticky;
                top: 0;
                z-index: 20;
                display: flex;
                flex-wrap: nowrap;
                overflow-x: auto;
                gap: var(--token-space-2);
                padding: var(--token-space-2) 0;
                background: var(--app-surface);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid var(--app-border);
            }
            div[data-testid="stTabs"] [role="tab"] {
                flex: 0 0 auto;
                min-width: 5.8rem;
                min-height: var(--token-tab-height);
                justify-content: center;
                border-radius: var(--token-radius-md);
                background: var(--app-panel);
                color: var(--app-text);
                font-weight: 760;
                padding: 0 0.35rem;
            }
            div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
                background: var(--app-primary);
                color: var(--app-primary-text);
            }
            div[data-testid="stDataFrame"],
            div[data-testid="stDataEditor"] {
                overflow-x: auto;
            }
            .holdings-data-table-wrap {
                display: none;
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
