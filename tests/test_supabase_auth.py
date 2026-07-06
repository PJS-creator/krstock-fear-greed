import pytest

from portfolio.supabase_auth import (
    SupabaseAuthError,
    SupabaseAuthStore,
    SupabaseAuthValidationError,
    account_from_auth_response,
    normalize_email,
    normalize_redirect_url,
    validate_password,
)


def test_supabase_auth_account_uses_user_id_as_owner_id():
    response = {
        "session": {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "user": {"id": "auth-user-id", "email": "User@Example.COM"},
        }
    }

    account = account_from_auth_response(response)

    assert account is not None
    assert account.owner_id == "auth-user-id"
    assert account.account_id == "user@example.com"
    assert account.access_token == "access-token"
    assert account.refresh_token == "refresh-token"


def test_supabase_auth_missing_session_means_confirmation_required():
    assert account_from_auth_response({"user": {"id": "auth-user-id", "email": "user@example.com"}}) is None


def test_supabase_auth_rejects_incomplete_session():
    with pytest.raises(SupabaseAuthError):
        account_from_auth_response({"session": {"user": {"id": "auth-user-id", "email": "user@example.com"}}})


def test_supabase_auth_validates_email_and_password():
    assert normalize_email(" User@Example.COM ") == "user@example.com"
    assert validate_password("strong-password") == "strong-password"
    with pytest.raises(SupabaseAuthValidationError):
        normalize_email("bad-email")
    with pytest.raises(SupabaseAuthValidationError):
        validate_password("short")


def test_supabase_auth_normalizes_email_redirect_url():
    assert normalize_redirect_url("https://jisungport.streamlit.app/?code=abc#token") == "https://jisungport.streamlit.app/"
    assert normalize_redirect_url("null") is None
    assert normalize_redirect_url("") is None


def test_supabase_signup_passes_email_redirect_option():
    class FakeAuth:
        def __init__(self):
            self.payload = None

        def sign_up(self, payload):
            self.payload = payload
            return {"user": {"id": "auth-user-id", "email": "user@example.com"}}

    class FakeClient:
        def __init__(self):
            self.auth = FakeAuth()

    store = SupabaseAuthStore.__new__(SupabaseAuthStore)
    store._client = FakeClient()

    result = store.sign_up("User@Example.COM", "strong-password", email_redirect_to="https://jisungport.streamlit.app/?x=1")

    assert result.confirmation_required
    assert store._client.auth.payload == {
        "email": "user@example.com",
        "password": "strong-password",
        "options": {"email_redirect_to": "https://jisungport.streamlit.app/"},
    }


def test_supabase_auth_restore_session_uses_saved_tokens():
    class FakeAuth:
        def __init__(self):
            self.tokens = None

        def set_session(self, access_token, refresh_token):
            self.tokens = (access_token, refresh_token)
            return {
                "session": {
                    "access_token": "new-access-token",
                    "refresh_token": "new-refresh-token",
                    "user": {"id": "auth-user-id", "email": "user@example.com"},
                }
            }

    class FakeClient:
        def __init__(self):
            self.auth = FakeAuth()

    store = SupabaseAuthStore.__new__(SupabaseAuthStore)
    store._client = FakeClient()

    account = store.restore_session("old-access-token", "old-refresh-token")

    assert store._client.auth.tokens == ("old-access-token", "old-refresh-token")
    assert account.owner_id == "auth-user-id"
    assert account.account_id == "user@example.com"
    assert account.access_token == "new-access-token"
    assert account.refresh_token == "new-refresh-token"
