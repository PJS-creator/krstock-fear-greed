from app.ui.theme import REQUIRED_THEME_TOKEN_KEYS, get_chart_palette, get_status_color, get_theme_tokens, theme_tokens


def test_light_and_dark_theme_tokens_have_required_keys():
    for mode in ("light", "dark"):
        tokens = theme_tokens(mode)
        assert REQUIRED_THEME_TOKEN_KEYS <= set(tokens)
        assert tokens["text"] != tokens["surface"]
        assert tokens["text"] != tokens["bg"]
        assert tokens["table_header_bg"] != tokens["text"]


def test_status_background_tokens_do_not_match_text_tokens():
    for mode in ("light", "dark"):
        tokens = theme_tokens(mode)
        for tone in ("success", "warning", "danger", "info"):
            assert tokens[f"{tone}_bg"] != tokens[tone]
            assert tokens[f"{tone}_bg"] != tokens["text"]


def test_light_and_dark_theme_tokens_have_identical_key_sets():
    light = get_theme_tokens("light")
    dark = get_theme_tokens("dark")

    assert set(light) == set(dark)
    assert REQUIRED_THEME_TOKEN_KEYS == set(light)
    for tokens in (light, dark):
        for key in ("profit", "loss", "success", "danger", "warning", "info", "accent", "cash"):
            assert tokens[key]


def test_chart_palettes_are_limited_and_non_empty():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)
        for kind in ("default", "allocation", "diverging", "status"):
            palette = get_chart_palette(tokens, kind)
            assert 1 <= len(palette) <= 8
            assert all(palette)


def test_status_tokens_are_semantic_not_pnl_aliases():
    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)
        success = get_status_color("success", tokens)
        failed = get_status_color("failed", tokens)

        assert success["color"] == tokens["success"]
        assert failed["color"] == tokens["danger"]
        assert success["color"] != tokens["profit"]
        assert failed["color"] != tokens["loss"]


def test_dark_mode_input_tokens_are_visible_against_page_background():
    tokens = get_theme_tokens("dark")

    assert tokens["input_bg"] != tokens["bg"]
    assert tokens["input_border"] == tokens["border_strong"]
    assert tokens["input_text"] != tokens["input_bg"]
