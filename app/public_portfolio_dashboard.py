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
_previous_public_auth = os.environ.get("PORTFOLIO_PUBLIC_AUTH")
os.environ["PORTFOLIO_PUBLIC_AUTH"] = "1"
try:
    if DASHBOARD_MODULE in sys.modules:
        importlib.reload(sys.modules[DASHBOARD_MODULE])
    else:
        importlib.import_module(DASHBOARD_MODULE)
finally:
    if _previous_public_auth is None:
        os.environ.pop("PORTFOLIO_PUBLIC_AUTH", None)
    else:
        os.environ["PORTFOLIO_PUBLIC_AUTH"] = _previous_public_auth
