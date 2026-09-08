from __future__ import annotations

import streamlit as st

from portfolio.storage import PortfolioRecord

BASE_VERSION_KEY = "portfolio_base_version"
SAVE_CONFLICT_KEY = "portfolio_save_conflict"


def record_loaded_version(record: PortfolioRecord) -> None:
    st.session_state[BASE_VERSION_KEY] = {
        "owner_id": record.owner_id, "portfolio_name": record.portfolio_name,
        "updated_at": record.updated_at,
    }
    st.session_state.pop(SAVE_CONFLICT_KEY, None)


def expected_version(owner_id: str, portfolio_name: str) -> str | None:
    base = st.session_state.get(BASE_VERSION_KEY) or {}
    if base.get("owner_id") == owner_id and base.get("portfolio_name") == portfolio_name:
        return base.get("updated_at")
    return None
