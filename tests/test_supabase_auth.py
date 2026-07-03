import pytest

from portfolio.supabase_auth import (
    SupabaseAuthError,
    SupabaseAuthValidationError,
    account_from_auth_response,
    normalize_email,
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
