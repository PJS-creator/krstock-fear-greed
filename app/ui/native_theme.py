"""Session-local native canvas theme bridge for Streamlit 1.50 on Cloud.

The host theme message updates React/Glide without changing server config,
widget state, navigation or authentication. The frontend validates origins.
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from .theme import get_theme_tokens


def native_theme_config(mode: str) -> dict:
    tokens = get_theme_tokens(mode)
    return {
        "base": 0 if mode == "light" else 1,
        "primaryColor": tokens["primary"],
        "backgroundColor": tokens["surface"],
        "secondaryBackgroundColor": tokens["surface_raised"],
        "textColor": tokens["text"],
        "borderColor": tokens["border_strong"],
        "dataframeBorderColor": tokens["border"],
        "dataframeHeaderBackgroundColor": tokens["table_header_bg"],
    }


def sync_native_theme(mode: str) -> None:
    theme = json.dumps(native_theme_config(mode))
    # Only color tokens go to the same-origin parent. Never relax the host
    # allowlist in application code or change a process-global theme per user.
    with st.container(key="native_theme_bridge"):
        components.html(
            """<script>
            const themeInfo = __THEME__;
            const message = {stCommVersion: 1, type: 'SET_CUSTOM_THEME_CONFIG',
                themeName: 'JisungPort', themeInfo};
            for (const delay of [0, 150, 600]) {
                setTimeout(() => window.parent.postMessage(message, window.parent.location.origin), delay);
            }
            </script>""".replace("__THEME__", theme),
            height=0, scrolling=False,
        )
