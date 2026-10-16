from streamlit.testing.v1 import AppTest

from app import portfolio_dashboard as dashboard


def login(app):
    app.text_input(key="public_login_email").set_value("qa@example.invalid")
    app.text_input(key="public_login_password").set_value("test-password")
    app.checkbox(key="public_login_remember_me").check()
    next(button for button in app.button if button.label == "로그인").click().run(timeout=20)
    assert not app.exception
    assert app.session_state[dashboard.AUTHENTICATED_KEY]


def test_logout_with_delayed_cookie_stays_logged_out_across_reruns_and_login_works():
    app = AppTest.from_file("tests/browser/auth_fixture.py")
    app.query_params["cookies"] = "fake"
    app.run(timeout=20)
    login(app)
    next(button for button in app.button if button.label == "로그아웃").click().run(timeout=20)
    for _ in range(3):
        app.run(timeout=20)
        assert not app.exception
        assert not app.session_state[dashboard.AUTHENTICATED_KEY]
        assert app.text_input(key="public_login_email")
    assert app.session_state["qa_signout_count"] == 1
    assert app.session_state["qa_cookie_expirations"] >= 3
    assert app.session_state.filtered_state.get("qa_restore_count", 0) == 0
    login(app)
    assert "app_logout" not in app.query_params


def test_mobile_logout_on_fresh_session_does_not_restore_cookie_before_login_gate():
    app = AppTest.from_file("tests/browser/auth_fixture.py")
    app.query_params.update(cookies="fake", seed_cookie="1", app_logout="1")
    app.run(timeout=20)
    assert not app.exception
    assert not app.session_state[dashboard.AUTHENTICATED_KEY]
    assert app.session_state.filtered_state.get("qa_restore_count", 0) == 0
    assert app.session_state["qa_cookie_expirations"] == 1
    app.text_input(key="public_login_email").set_value("bad@example.invalid")
    app.text_input(key="public_login_password").set_value("wrong")
    next(button for button in app.button if button.label == "로그인").click().run(timeout=20)
    assert app.session_state[dashboard.PUBLIC_LOGGED_OUT_KEY]
    assert not app.session_state[dashboard.AUTHENTICATED_KEY]
    login(app)
