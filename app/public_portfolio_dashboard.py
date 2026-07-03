from __future__ import annotations

import os
from pathlib import Path
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


_ensure_project_root_on_path()
os.environ["PORTFOLIO_PUBLIC_AUTH"] = "1"

import app.portfolio_dashboard  # noqa: E402,F401
