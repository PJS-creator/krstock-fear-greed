import pytest

from portfolio.session_persistence import (
    DEFAULT_REMEMBER_DAYS,
    SESSION_SECRET_MIN_LENGTH,
    SessionPersistenceError,
    decode_remembered_session,
    encode_remembered_session,
    validate_session_secret,
)


SECRET = "x" * SESSION_SECRET_MIN_LENGTH


def test_remembered_session_round_trips_encrypted_payload():
    token = encode_remembered_session(
        account_id="user@example.com",
        owner_id="auth-user-id",
        access_token="access-token",
        refresh_token="refresh-token",
        secret=SECRET,
        now=1000,
    )

    assert "refresh-token" not in token
    restored = decode_remembered_session(token, secret=SECRET, now=1001)

    assert restored.account_id == "user@example.com"
    assert restored.owner_id == "auth-user-id"
    assert restored.access_token == "access-token"
    assert restored.refresh_token == "refresh-token"
    assert restored.expires_at == 1000 + DEFAULT_REMEMBER_DAYS * 24 * 60 * 60


def test_remembered_session_rejects_short_secret_and_tampered_token():
    with pytest.raises(SessionPersistenceError, match="AUTH_SESSION_SECRET"):
        validate_session_secret("too-short")

    token = encode_remembered_session(
        account_id="user@example.com",
        owner_id="auth-user-id",
        access_token="access-token",
        refresh_token="refresh-token",
        secret=SECRET,
        now=1000,
    )

    tampered = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
    with pytest.raises(SessionPersistenceError, match="invalid"):
        decode_remembered_session(tampered, secret=SECRET, now=1001)


def test_remembered_session_expires():
    token = encode_remembered_session(
        account_id="user@example.com",
        owner_id="auth-user-id",
        access_token="access-token",
        refresh_token="refresh-token",
        secret=SECRET,
        remember_days=1,
        now=1000,
    )

    with pytest.raises(SessionPersistenceError, match="expired"):
        decode_remembered_session(token, secret=SECRET, now=1000 + 24 * 60 * 60 + 1)
