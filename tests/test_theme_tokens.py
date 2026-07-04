from app.ui.theme import REQUIRED_THEME_TOKEN_KEYS, theme_tokens


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
