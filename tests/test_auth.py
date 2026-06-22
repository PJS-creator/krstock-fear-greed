from portfolio.auth import (
    AUTH_SCOPE_ALL,
    AUTH_SCOPE_MANUAL,
    AppSecurityConfig,
    config_from_secrets,
    normalize_auth_scope,
    should_disable_price_update,
    should_lock_entire_app,
    should_lock_manual_mode,
    verify_password,
)


def test_missing_app_password_config_does_not_fail():
    config = config_from_secrets(None)

    assert config.app_password is None
    assert config.auth_scope == AUTH_SCOPE_ALL
    assert config.alpha_vantage_api_key is None
    assert not should_lock_entire_app(config, is_authenticated=False)
    assert not should_lock_manual_mode(config, is_authenticated=False)


def test_password_verification_accepts_only_correct_password():
    expected_password = "expected-password"

    assert verify_password("expected-password", expected_password)
    assert not verify_password("wrong-password", expected_password)


def test_empty_password_input_fails():
    assert not verify_password("", "expected-password")
    assert not verify_password("   ", "expected-password")
    assert not verify_password(None, "expected-password")


def test_price_update_is_disabled_when_api_key_exists_without_app_password():
    config = AppSecurityConfig(app_password=None, alpha_vantage_api_key="demo-api-key")

    assert should_disable_price_update(config)


def test_price_update_policy_allows_no_key_or_password_protected_key():
    no_key_config = AppSecurityConfig(app_password=None, alpha_vantage_api_key=None)
    protected_key_config = AppSecurityConfig(app_password="expected-password", alpha_vantage_api_key="demo-api-key")

    assert not should_disable_price_update(no_key_config)
    assert not should_disable_price_update(protected_key_config)


def test_auth_scope_defaults_to_all_and_allows_manual_scope():
    assert normalize_auth_scope(None) == AUTH_SCOPE_ALL
    assert normalize_auth_scope("unknown") == AUTH_SCOPE_ALL
    assert normalize_auth_scope("manual") == AUTH_SCOPE_MANUAL


def test_lock_policies_follow_configured_scope():
    full_lock_config = AppSecurityConfig(app_password="expected-password", auth_scope=AUTH_SCOPE_ALL)
    manual_lock_config = AppSecurityConfig(app_password="expected-password", auth_scope=AUTH_SCOPE_MANUAL)

    assert should_lock_entire_app(full_lock_config, is_authenticated=False)
    assert not should_lock_entire_app(full_lock_config, is_authenticated=True)
    assert not should_lock_manual_mode(full_lock_config, is_authenticated=False)

    assert not should_lock_entire_app(manual_lock_config, is_authenticated=False)
    assert should_lock_manual_mode(manual_lock_config, is_authenticated=False)
    assert not should_lock_manual_mode(manual_lock_config, is_authenticated=True)
