import pytest

from portfolio.storage import (
    MemoryPortfolioStore,
    PortfolioPayloadError,
    deserialize_portfolio_payload,
    deserialize_portfolio_payload_v2,
    has_supabase_credentials,
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
    payload = serialize_portfolio_payload(
        [
            _row(
                symbol="abc",
                provider="yfinance",
                source="yfinance",
                price_date="2026-06-30",
                as_of_timestamp="2026-06-30T15:00:00+00:00",
                quote_status="updated",
            )
        ],
        usd_krw=1300,
        cash_krw=10000,
        cash_usd=5,
        transactions=[
            {"transaction_type": "매입", "ticker_or_name": "ABC", "unit_price": "100", "quantity": "2", "occurred_at": "2026-01-01"}
        ],
        cash_ledger=[
            {"event_date": "2026-01-01", "currency": "KRW", "event_type": "deposit", "amount": "10000"}
        ],
        fx_metadata={
            "rate_date": "2026-06-30",
            "as_of_timestamp": "2026-06-30T15:00:00+00:00",
            "source": "yahoo-chart",
            "status": "updated",
            "fetched_at": "2026-06-30T15:01:00+00:00",
        },
        target_allocations=[
            {"asset_type": "stock", "symbol": "ABC", "market": "US", "currency": "USD", "display_name": "ABC", "target_weight_pct": 70},
            {"asset_type": "cash", "currency": "KRW", "target_weight_pct": 30},
        ],
        journal_notes=[
            {"note_date": "2026-02-01", "title": "첫 메모", "body": "복기", "symbol": "ABC", "tags": ["복기"]},
        ],
    )

    rows, usd_krw, cash_krw = deserialize_portfolio_payload(payload)
    v2 = deserialize_portfolio_payload_v2(payload)

    assert payload["schema_version"] == 3
    assert rows[0]["ticker"] == "ABC"
    assert rows[0]["quantity"] == 2.0
    assert usd_krw == 1300.0
    assert cash_krw == 10000.0
    assert v2["cash_balances"]["USD"] == 5.0
    assert v2["last_known_quotes"]["ABC"]["current_price"] == 125.0
    assert v2["last_known_quotes"]["ABC"]["source"] == "yfinance"
    assert v2["last_known_quotes"]["ABC"]["price_date"] == "2026-06-30"
    assert v2["fx_metadata"]["source"] == "yahoo-chart"
    assert v2["fx_metadata"]["rate_date"] == "2026-06-30"
    assert v2["target_allocations"][0]["symbol"] == "ABC"
    assert v2["target_allocations"][0]["target_weight_pct"] == 70.0
    assert v2["target_allocations"][1]["symbol"] == "CASH_KRW"
    assert v2["transactions"][0]["transaction_type"] == "buy"
    assert v2["transactions"][0]["ticker"] == "ABC"
    assert v2["cash_ledger"][0]["event_type"] == "deposit"
    assert v2["cash_ledger"][0]["amount"] == "10000"
    assert v2["journal_notes"][0]["title"] == "첫 메모"


def test_v1_payload_migrates_to_current_schema():
    v1 = {"schema_version": 1, "rows": [_row(symbol="abc")], "usd_krw": 1300, "cash_krw": 10000}

    migrated = migrate_v1_payload_to_v2(v1)

    assert migrated["schema_version"] == 3
    assert migrated["holdings"][0]["ticker"] == "ABC"
    assert migrated["cash_balances"] == {"KRW": 10000.0, "USD": 0.0}
    assert migrated["transactions"] == []


def test_v2_payload_loads_without_transactions_for_backward_compatibility():
    v2 = {
        "schema_version": 2,
        "holdings": [_row(symbol="abc")],
        "cash_balances": {"KRW": 10000, "USD": 5},
        "usd_krw": 1300,
    }

    payload = deserialize_portfolio_payload_v2(v2)

    assert payload["schema_version"] == 3
    assert payload["holdings"][0]["ticker"] == "ABC"
    assert payload["transactions"] == []
    assert payload["target_allocations"] == []


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


def test_memory_store_isolates_records_by_owner_id():
    store = MemoryPortfolioStore()
    payload_a = serialize_portfolio_payload([_row(symbol="AAA")], usd_krw=1300, cash_krw=0)
    payload_b = serialize_portfolio_payload([_row(symbol="BBB")], usd_krw=1300, cash_krw=0)

    store.save_portfolio("owner-a", "main", payload_a)
    store.save_portfolio("owner-b", "main", payload_b)

    assert store.get_portfolio("owner-a", "main").payload_json["holdings"][0]["ticker"] == "AAA"
    assert store.get_portfolio("owner-b", "main").payload_json["holdings"][0]["ticker"] == "BBB"
    assert [record.owner_id for record in store.list_portfolios("owner-a")] == ["owner-a"]


def test_missing_supabase_secrets_disable_storage_policy():
    assert not should_enable_storage(supabase_config_from_secrets({}))
    credentials_only = supabase_config_from_secrets(
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "placeholder-service-role-key",
        }
    )
    assert has_supabase_credentials(credentials_only)
    assert not should_enable_storage(credentials_only)
    assert should_enable_storage(credentials_only, owner_id="account-owner")
    assert should_enable_storage(
        supabase_config_from_secrets(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "placeholder-service-role-key",
                "PORTFOLIO_OWNER_ID": "test-owner",
            }
        )
    )


def test_publishable_key_can_configure_authenticated_public_storage():
    config = supabase_config_from_secrets(
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "placeholder-publishable-key",
        }
    )
    authed = config.with_auth_session(owner_id="auth-user-id", access_token="access-token", refresh_token="refresh-token")

    assert has_supabase_credentials(config)
    assert config.api_key == "placeholder-publishable-key"
    assert not should_enable_storage(config)
    assert should_enable_storage(authed)
    assert authed.owner_id == "auth-user-id"
    assert authed.service_role_key is None


def test_invalid_payload_validation_errors():
    with pytest.raises(PortfolioPayloadError, match="schema_version"):
        deserialize_portfolio_payload({"schema_version": 999, "holdings": [], "usd_krw": 1300, "cash_balances": {}})

    with pytest.raises(PortfolioPayloadError, match="holdings"):
        deserialize_portfolio_payload({"schema_version": 2, "holdings": "not-a-list", "usd_krw": 1300, "cash_balances": {}})

    with pytest.raises(PortfolioPayloadError, match="usd_krw"):
        deserialize_portfolio_payload({"schema_version": 2, "holdings": [], "usd_krw": 0, "cash_balances": {}})

    with pytest.raises(PortfolioPayloadError, match="quantity"):
        deserialize_portfolio_payload({"schema_version": 2, "holdings": [{"ticker": "AAA"}], "usd_krw": 1300, "cash_balances": {}})
