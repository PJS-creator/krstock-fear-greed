"""Local/CI-only fixture using the public dashboard with synthetic data and no credentials."""
from contextlib import ExitStack
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import streamlit as st

from app import portfolio_dashboard as dashboard
from app.ui import chart_analysis
from portfolio.auth import AppSecurityConfig
from portfolio.chart_analysis import AnalysisInstrument, DailyHistoryInput, analyze_daily_history
from portfolio.storage import SupabaseStorageConfig


def disabled_auth(*args, **kwargs):
    raise dashboard.SupabaseAuthError("QA fixture: 실제 계정 인증은 실행하지 않습니다.")


def synthetic_refresh(*args, **kwargs):
    st.session_state["last_price_refresh_at"] = "2026-09-08T00:00:00+00:00"
    dashboard.request_app_rerun()


def analysis(payload, *args, **kwargs):
    values = 100 + np.arange(400) * 0.2 + np.sin(np.arange(400) / 8) * 8
    frame = pd.DataFrame({
        "timestamp": pd.bdate_range(end="2026-09-04", periods=400),
        "open": values, "high": values + 2, "low": values - 2,
        "close": values, "volume": 10000, "traded_value": values * 10000,
    })
    return tuple(analyze_daily_history(DailyHistoryInput(
        instrument=AnalysisInstrument(market, symbol, name), frame=frame, provider="QA fixture",
    )) for market, symbol, name in payload)


scenario = st.query_params.get("scenario", "ready")
if not st.session_state.get("qa_initialized"):
    dashboard._initialize_session_state(public_auth_enabled=True)
    mode = st.query_params.get("theme", "dark")
    st.session_state.update({
        "qa_initialized": True, "app_theme_mode": mode, "theme_mode": mode,
        "app_theme_choice": "라이트" if mode == "light" else "다크",
        "is_authenticated": scenario != "login", "authenticated_account_id": "qa@example.invalid",
        "authenticated_owner_id": "qa-owner", "authenticated_default_portfolio": "main",
        "usd_krw": 1350.0, "cash_krw": 1000000.0 if scenario != "empty" else 0.0,
        "holdings_rows": [] if scenario == "empty" else [
            {"ticker": "005930", "display_name": "삼성전자", "market": "KR", "currency": "KRW", "quantity": 10,
             "avg_price": 70000, "current_price": 75000, "previous_close": 73000},
            {"ticker": "MSFT", "display_name": "Microsoft", "market": "US", "currency": "USD", "quantity": 2,
             "avg_price": 300, "current_price": None if scenario == "partial" else 400, "previous_close": 410},
        ],
    })

with ExitStack() as stack:
    overrides = {
        "_read_security_config": lambda: AppSecurityConfig(None),
        "_read_storage_config": lambda **kwargs: SupabaseStorageConfig(None, None, None),
        "_build_stores": lambda *args: (None, None, None, None),
        "_build_public_auth_store": lambda *args: SimpleNamespace(sign_in=disabled_auth, sign_up=disabled_auth),
        "_secret_text": lambda *args, **kwargs: "",
        "_run_price_refresh": synthetic_refresh,
        "_restore_public_auth_session": lambda *args: False,
        "_refresh_public_auth_session_if_due": lambda *args: False,
        "get_cookie_manager": lambda: None,
        "_remember_login_available": lambda *args: True,
        "_read_kis_quote_provider": lambda: None,
        "_load_official_meta_strategy_state": lambda: None,
        "_load_alternative_meta_strategy_state": lambda: None,
        "_cached_market_indices": lambda *args: [],
        "_read_market_warning_signals": lambda *args: [],
    }
    for name, value in overrides.items():
        stack.enter_context(patch.object(dashboard, name, value))
    stack.enter_context(patch.object(chart_analysis, "_load_chart_analysis", analysis))
    dashboard.run_dashboard(public_auth_enabled=True)
