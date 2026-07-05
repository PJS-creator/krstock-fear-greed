from app.ui.theme import get_theme_tokens


SPACING_KEYS = {
    "space_0",
    "space_1",
    "space_2",
    "space_3",
    "space_4",
    "space_5",
    "space_6",
    "space_8",
    "space_10",
    "space_12",
}
TYPOGRAPHY_KEYS = {
    "font_xs",
    "font_sm",
    "font_base",
    "font_md",
    "font_lg",
    "font_xl",
    "font_2xl",
    "font_3xl",
    "line_height_tight",
    "line_height_normal",
    "line_height_loose",
}
CONTROL_KEYS = {
    "control_height_sm",
    "control_height_md",
    "control_height_lg",
    "button_height_sm",
    "button_height_md",
    "button_height_lg",
    "input_height_md",
    "tab_height",
    "subtab_height",
}
LAYOUT_KEYS = {
    "page_max_width",
    "page_padding_x_desktop",
    "page_padding_x_tablet",
    "page_padding_x_mobile",
    "section_gap",
    "card_gap",
    "card_padding",
    "card_padding_compact",
    "table_min_row_height",
    "table_compact_row_height",
    "chart_height_sm",
    "chart_height_md",
    "chart_height_lg",
}


def test_layout_tokens_exist_for_light_and_dark_modes():
    required = SPACING_KEYS | TYPOGRAPHY_KEYS | CONTROL_KEYS | LAYOUT_KEYS

    for mode in ("light", "dark"):
        tokens = get_theme_tokens(mode)

        assert required <= set(tokens)
        assert all(tokens[key] not in ("", None) for key in required)


def test_layout_token_sets_are_identical_between_modes():
    light = get_theme_tokens("light")
    dark = get_theme_tokens("dark")

    for key in SPACING_KEYS | TYPOGRAPHY_KEYS | CONTROL_KEYS | LAYOUT_KEYS:
        assert key in light
        assert key in dark
