from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


_ensure_project_root_on_path()

DASHBOARD_MODULE = "app.portfolio_dashboard"


def _load_dashboard_module() -> None:
    module = sys.modules.get(DASHBOARD_MODULE)
    if module is None:
        importlib.import_module(DASHBOARD_MODULE)
        return

    try:
        importlib.reload(module)
    except ImportError as exc:
        if f"module {DASHBOARD_MODULE!r} not in sys.modules" not in str(exc):
            raise
        sys.modules.pop(DASHBOARD_MODULE, None)
        importlib.import_module(DASHBOARD_MODULE)


_previous_public_auth = os.environ.get("PORTFOLIO_PUBLIC_AUTH")
os.environ["PORTFOLIO_PUBLIC_AUTH"] = "1"
try:
    _load_dashboard_module()
finally:
    if _previous_public_auth is None:
        os.environ.pop("PORTFOLIO_PUBLIC_AUTH", None)
    else:
        os.environ["PORTFOLIO_PUBLIC_AUTH"] = _previous_public_auth
