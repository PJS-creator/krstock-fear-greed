import pytest

from portfolio.storage import (
    MemoryPortfolioStore,
    PortfolioPayloadError,
    deserialize_portfolio_payload,
    deserialize_portfolio_payload_v2,
    migrate_v1_payload_to_v2,
    serialize_portfolio_payload,
    should_enable_storage,
    supabase_config_from_secrets,
)


def _row(**overrides):
    row = {
        "market": "US",
        "symbol": "TST",
        "name": "Test Holding",
        "currency": "USD",
        "quantity": "2",
        "avg_price": "100",
        "current_price": "125",
        "previous_close": "120",
        "target_weight": "0.5",
        "strategy_tag": "Test",
    }
    row.update(overrides)
    return row


def test_portfolio_payload_round_trip():
    payload = serialize_portfolio_payload([_row(symbol="abc")], usd_krw=1300, cash_krw=10000, cash_usd=5)

    rows, usd_krw, cash_krw = deserialize_portfolio_payload(payload)
    v2 = deserialize_portfolio_payload_v2(payload)

    assert payload["schema_version"] == 2
    assert rows[0]["ticker"] == "ABC"
    assert rows[0]["quantity"] == 2.0
    assert usd_krw == 1300.0
    assert cash_krw == 10000.0
    assert v2["cash_balances"]["USD"] == 5.0
    assert v2["last_known_quotes"]["ABC"]["current_price"] == 125.0


def test_v1_payload_migrates_to_v2():
    v1 = {"schema_version": 1, "rows": [_row(symbol="abc")], "usd_krw": 1300, "cash_krw": 10000}

    migrated = migrate_v1_payload_to_v2(v1)

    assert migrated["schema_version"] == 2
    assert migrated["holdings"][0]["ticker"] == "ABC"
    assert migrated["cash_balances"] == {"KRW": 10000.0, "USD": 0.0}


def test_memory_store_save_load_and_delete():
    store = MemoryPortfolioStore()
    payload = serialize_portfolio_payload([_row(symbol="AAA")], usd_krw=1300, cash_krw=0)

    saved = store.save_portfolio("owner-a", "core", payload)
    loaded = store.get_portfolio("owner-a", "core")

    assert saved.portfolio_name == "core"
    assert loaded is not None
    assert loaded.payload_json == payload
    assert [record.portfolio_name for record in store.list_portfolios("owner-a")] == ["core"]
    assert store.delete_portfolio("owner-a", "core")
    assert store.get_portfolio("owner-a", "core") is None
    assert not store.delete_portfolio("owner-a", "core")


def test_memory_store_overwrites_same_portfolio_name():
    store = MemoryPortfolioStore()
    first_payload = serialize_portfolio_payload([_row(symbol="AAA")], usd_krw=1300, cash_krw=0)
    second_payload = serialize_portfolio_payload([_row(symbol="BBB")], usd_krw=1400, cash_krw=5000)

    first = store.save_portfolio("owner-a", "core", first_payload)
    second = store.save_portfolio("owner-a", "core", second_payload)
    loaded = store.get_portfolio("owner-a", "core")

    assert loaded is not None
    assert first.created_at == second.created_at
    assert loaded.payload_json["holdings"][0]["ticker"] == "BBB"
    assert loaded.payload_json["usd_krw"] == 1400.0
    assert len(store.list_portfolios("owner-a")) == 1


def test_missing_supabase_secrets_disable_storage_policy():
    assert not should_enable_storage(supabase_config_from_secrets({}))
    assert not should_enable_storage(
        supabase_config_from_secrets(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "placeholder-service-role-key",
            }
        )
    )
    assert should_enable_storage(
        supabase_config_from_secrets(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "placeholder-service-role-key",
                "PORTFOLIO_OWNER_ID": "test-owner",
            }
        )
    )


def test_invalid_payload_validation_errors():
    with pytest.raises(PortfolioPayloadError, match="schema_version"):
        deserialize_portfolio_payload({"schema_version": 999, "holdings": [], "usd_krw": 1300, "cash_balances": {}})

    with pytest.raises(PortfolioPayloadError, match="holdings"):
        deserialize_portfolio_payload({"schema_version": 2, "holdings": "not-a-list", "usd_krw": 1300, "cash_balances": {}})

    with pytest.raises(PortfolioPayloadError, match="usd_krw"):
        deserialize_portfolio_payload({"schema_version": 2, "holdings": [], "usd_krw": 0, "cash_balances": {}})

    with pytest.raises(PortfolioPayloadError, match="quantity"):
        deserialize_portfolio_payload({"schema_version": 2, "holdings": [{"ticker": "AAA"}], "usd_krw": 1300, "cash_balances": {}})
