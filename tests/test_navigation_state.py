from portfolio.navigation import resolve_quick_nav_target


def test_quick_nav_targets_analysis_subtabs():
    assert resolve_quick_nav_target("profit") == ("analysis", "profit")
    assert resolve_quick_nav_target("tax") == ("analysis", "tax")
    assert resolve_quick_nav_target("dividend") == ("analysis", "dividend")
    assert resolve_quick_nav_target("trend") == ("analysis", "trend")
    assert resolve_quick_nav_target("allocation") == ("analysis", "allocation")


def test_quick_nav_targets_journal_and_input_subtabs():
    assert resolve_quick_nav_target("journal") == ("journal", None)
    assert resolve_quick_nav_target("cash") == ("input", "cash_fx")
    assert resolve_quick_nav_target("trade") == ("input", "transactions")


def test_unknown_quick_nav_is_ignored():
    assert resolve_quick_nav_target("unknown") is None
