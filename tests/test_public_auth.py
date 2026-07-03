import pytest

from portfolio.public_auth import (
    PASSWORD_ALGORITHM,
    PublicAccountValidationError,
    hash_password,
    normalize_account_id,
    owner_id_for_account,
    verify_password_hash,
)


def test_public_account_id_is_normalized_and_scoped_to_owner_id():
    assert normalize_account_id(" Jisung.Main ") == "jisung.main"
    assert owner_id_for_account("Jisung.Main") == "public:jisung.main"


@pytest.mark.parametrize("value", ["ab", "bad id", "한글아이디", "-starts-with-dash", ""])
def test_invalid_public_account_id_is_rejected(value):
    with pytest.raises(PublicAccountValidationError):
        normalize_account_id(value)


def test_public_password_hash_uses_salt_and_verifies_without_plaintext():
    salt_a, hash_a = hash_password("strong-password")
    salt_b, hash_b = hash_password("strong-password")

    assert PASSWORD_ALGORITHM == "pbkdf2_sha256"
    assert salt_a != salt_b
    assert hash_a != hash_b
    assert "strong-password" not in hash_a
    assert verify_password_hash("strong-password", salt_a, hash_a)
    assert not verify_password_hash("wrong-password", salt_a, hash_a)


def test_public_password_requires_minimum_length():
    with pytest.raises(PublicAccountValidationError):
        hash_password("short")
