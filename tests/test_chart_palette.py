from app.ui.theme import get_chart_palette, get_theme_tokens


def test_allocation_palette_is_limited_and_separates_cash():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)
        palette = get_chart_palette(tokens, "allocation")

        assert len(palette) <= 8
        assert tokens["cash"] in palette
        assert tokens["cash"] != tokens["stock"]


def test_diverging_palette_separates_profit_neutral_loss():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)
        palette = get_chart_palette(tokens, "diverging")

        assert palette == [tokens["profit"], tokens["neutral_value"], tokens["loss"]]
        assert len(set(palette)) == 3


def test_chart_surface_tokens_exist_for_light_and_dark():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)

        assert tokens["chart_grid"]
        assert tokens["chart_axis"]
        assert tokens["chart_text"]
        assert tokens["chart_tooltip_bg"]
        assert tokens["chart_tooltip_text"]
