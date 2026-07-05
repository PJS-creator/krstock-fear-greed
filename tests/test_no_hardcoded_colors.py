import re
from pathlib import Path


COLOR_RE = re.compile(r"#[0-9A-Fa-f]{3,8}|rgba?\(|hsla?\(")
ALLOWED_PATHS = {
    ".streamlit/config.toml",
    "app/ui/theme.py",
}
ALLOWED_SNIPPETS = {
    'paper_bgcolor="rgba(0,0,0,0)"',
    'plot_bgcolor="rgba(0,0,0,0)"',
}


def test_app_ui_color_values_are_centralized_in_theme_tokens():
    offenders: list[str] = []
    for path in [*Path("app/ui").glob("*.py"), Path(".streamlit/config.toml")]:
        normalized = path.as_posix()
        if normalized in ALLOWED_PATHS:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not COLOR_RE.search(line):
                continue
            if any(snippet in line for snippet in ALLOWED_SNIPPETS):
                continue
            offenders.append(f"{normalized}:{line_number}: {line.strip()}")

    assert offenders == []
