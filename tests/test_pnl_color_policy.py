import math

from app.ui.theme import get_pnl_color, get_theme_tokens


def test_pnl_color_policy_uses_kr_investor_convention():
    tokens = get_theme_tokens("light")

    assert get_pnl_color(1.0, tokens) == tokens["profit"]
    assert get_pnl_color(-1.0, tokens) == tokens["loss"]
    assert get_pnl_color(0.0, tokens) == tokens["neutral_value"]
    assert get_pnl_color(None, tokens) == tokens["neutral_value"]
    assert get_pnl_color(math.nan, tokens) == tokens["neutral_value"]


def test_pnl_color_policy_is_separate_from_status_colors():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)

        assert tokens["profit"] != tokens["success"]
        assert tokens["loss"] != tokens["danger"]
