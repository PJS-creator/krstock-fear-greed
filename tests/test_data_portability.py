from portfolio.data_portability import (
    CASH_LEDGER_IMPORT_COLUMNS,
    TRANSACTION_IMPORT_COLUMNS,
    build_full_export_payload,
    csv_to_rows,
    preview_cash_ledger_import,
    preview_transaction_import,
    rows_to_csv,
)


KRX_RECORDS = [{"ticker": "005930", "display_name": "삼성전자"}]


def test_transaction_csv_preview_resolves_names_and_skips_duplicate_external_id():
    rows = csv_to_rows(
        rows_to_csv(
            [
                {
                    "external_id": "buy-001",
                    "transaction_type": "매입",
                    "ticker_or_name": "삼성전자",
                    "unit_price": "70000",
                    "quantity": "10",
                    "fee": "1000",
                    "tax": "0",
                    "occurred_at": "2026-04-13",
                    "note": "first buy",
                },
                {
                    "external_id": "buy-001",
                    "transaction_type": "매입",
                    "ticker_or_name": "삼성전자",
                    "unit_price": "70000",
                    "quantity": "10",
                    "fee": "1000",
                    "tax": "0",
                    "occurred_at": "2026-04-13",
                    "note": "first buy",
                },
            ],
            TRANSACTION_IMPORT_COLUMNS,
        )
    )

    preview = preview_transaction_import(rows, korea_listing_records=KRX_RECORDS)

    assert len(preview.rows) == 2
    assert len(preview.valid_rows) == 1
    assert preview.duplicate_count == 1
    assert preview.valid_rows[0]["ticker"] == "005930"
    assert preview.valid_rows[0]["external_id"] == "buy-001"


def test_transaction_csv_preview_skips_existing_duplicate():
    preview = preview_transaction_import(
        [
            {
                "transaction_type": "buy",
                "ticker": "QURE",
                "market": "US",
                "currency": "USD",
                "unit_price": "41",
                "quantity": "10",
                "occurred_at": "2026-04-13",
                "note": "existing",
            }
        ],
        existing_transactions=[
            {
                "transaction_type": "buy",
                "ticker": "QURE",
                "market": "US",
                "currency": "USD",
                "unit_price": "41",
                "quantity": "10",
                "occurred_at": "2026-04-13",
                "note": "existing",
            }
        ],
    )

    assert preview.valid_rows == []
    assert preview.duplicate_count == 1


def test_transaction_csv_preview_uses_explicit_korean_ticker_without_listing_data():
    preview = preview_transaction_import(
        [
            {
                "external_id": "kr-buy-001",
                "transaction_type": "매입",
                "ticker_or_name": "SK하이닉스",
                "ticker": "000660",
                "market": "KR",
                "currency": "KRW",
                "display_name": "SK하이닉스",
                "unit_price": "1117140",
                "quantity": "20",
                "occurred_at": "2026-04-08",
            }
        ],
        korea_listing_records=[],
    )

    assert preview.error_count == 0
    assert preview.valid_rows[0]["ticker"] == "000660"
    assert preview.valid_rows[0]["display_name"] == "SK하이닉스"
    assert preview.valid_rows[0]["external_id"] == "kr-buy-001"


def test_cash_ledger_csv_preview_validates_and_skips_duplicates():
    rows = csv_to_rows(
        rows_to_csv(
            [
                {
                    "external_id": "deposit-001",
                    "event_date": "2026-04-13",
                    "currency": "KRW",
                    "event_type": "deposit",
                    "amount": "1000000",
                    "memo": "start",
                },
                {
                    "external_id": "bad-001",
                    "event_date": "2026-04-13",
                    "currency": "KRW",
                    "event_type": "deposit",
                    "amount": "-1000",
                    "memo": "bad sign",
                },
                {
                    "external_id": "deposit-001",
                    "event_date": "2026-04-13",
                    "currency": "KRW",
                    "event_type": "deposit",
                    "amount": "1000000",
                    "memo": "start",
                },
            ],
            CASH_LEDGER_IMPORT_COLUMNS,
        )
    )

    preview = preview_cash_ledger_import(rows)

    assert len(preview.valid_rows) == 1
    assert preview.error_count == 1
    assert preview.duplicate_count == 1
    assert preview.valid_rows[0]["external_id"] == "deposit-001"


def test_full_export_payload_contains_portable_sections():
    payload = build_full_export_payload(
        holdings=[{"ticker": "QURE", "market": "US", "currency": "USD", "display_name": "QURE", "quantity": 1, "avg_price": 41}],
        transactions=[
            {
                "transaction_type": "buy",
                "ticker": "QURE",
                "market": "US",
                "currency": "USD",
                "unit_price": 41,
                "quantity": 1,
                "occurred_at": "2026-04-13",
            }
        ],
        cash_ledger=[{"event_date": "2026-04-13", "currency": "USD", "event_type": "deposit", "amount": "100"}],
        target_allocations=[],
        portfolio_snapshot={"usd_krw": 1380},
    )

    assert payload["schema_version"] == 1
    assert payload["transactions"][0]["ticker"] == "QURE"
    assert payload["cash_ledger"][0]["currency"] == "USD"
    assert payload["portfolio_snapshot"]["usd_krw"] == 1380
