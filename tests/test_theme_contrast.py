import re

from app.ui.theme import get_theme_tokens


RGBA_RE = re.compile(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)")


def _rgb(color: str, *, background: str = "#FFFFFF") -> tuple[float, float, float]:
    color = color.strip()
    match = RGBA_RE.fullmatch(color)
    if match:
        red, green, blue, alpha = match.groups()
        fg = (int(red), int(green), int(blue))
        bg = _rgb(background)
        a = float(alpha)
        return tuple((fg[index] * a + bg[index] * (1 - a)) for index in range(3))
    if color.startswith("#"):
        raw = color[1:]
        if len(raw) == 3:
            raw = "".join(part * 2 for part in raw)
        return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))
    raise AssertionError(f"unsupported color format: {color}")


def _channel(value: float) -> float:
    value = value / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(color: str, *, background: str = "#FFFFFF") -> float:
    red, green, blue = _rgb(color, background=background)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast(foreground: str, background: str, *, page_bg: str = "#FFFFFF") -> float:
    bg_rgb = _rgb(background, background=page_bg)
    bg_hex = "#" + "".join(f"{round(channel):02X}" for channel in bg_rgb)
    lighter = max(_luminance(foreground, background=bg_hex), _luminance(background, background=page_bg))
    darker = min(_luminance(foreground, background=bg_hex), _luminance(background, background=page_bg))
    return (lighter + 0.05) / (darker + 0.05)


def test_core_theme_text_contrast_is_readable():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)
        assert _contrast(tokens["text"], tokens["bg"]) >= 4.5
        assert _contrast(tokens["text"], tokens["surface"]) >= 4.5
        assert _contrast(tokens["text_muted"], tokens["surface"]) >= 3.0
        assert _contrast(tokens["table_header_text"], tokens["table_header_bg"], page_bg=tokens["bg"]) >= 4.5
        assert _contrast(tokens["table_text"], tokens["table_row_bg"], page_bg=tokens["bg"]) >= 4.5
        assert _contrast(tokens["primary_text"], tokens["primary"]) >= 4.5


def test_semantic_soft_backgrounds_have_readable_text():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)
        page_bg = tokens["bg"]
        for tone in ("profit", "loss", "success", "warning", "danger", "info"):
            assert _contrast(tokens[f"{tone}_text"], tokens[f"{tone}_soft"], page_bg=page_bg) >= 3.0
