from types import SimpleNamespace
import sys

from app.ui import auth_persistence as auth


def test_cookie_manager_is_isolated_per_browser_and_refreshed_per_run(monkeypatch):
    constructed = []

    def manager(**kwargs):
        result = SimpleNamespace(cookies={"browser": len(constructed)}, key=kwargs["key"])
        constructed.append(result)
        return result

    monkeypatch.setitem(sys.modules, "extra_streamlit_components", SimpleNamespace(CookieManager=manager))
    browser_a, browser_b = {}, {}
    monkeypatch.setattr(auth, "st", SimpleNamespace(session_state=browser_a))
    auth.begin_cookie_run()
    first = auth.get_cookie_manager()
    assert auth.get_cookie_manager() is first
    monkeypatch.setattr(auth, "st", SimpleNamespace(session_state=browser_b))
    auth.begin_cookie_run()
    second = auth.get_cookie_manager()
    assert second is not first
    second.cookies.clear()
    assert first.cookies == {"browser": 0}
    monkeypatch.setattr(auth, "st", SimpleNamespace(session_state=browser_a))
    auth.begin_cookie_run()
    assert auth.get_cookie_manager() is not first
    assert len(constructed) == 3
