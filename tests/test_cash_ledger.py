from decimal import Decimal

import pytest

from portfolio.cash_ledger import (
    calculate_cash_balances,
    create_cash_ledger_entries_for_trade,
    create_fx_conversion_entries,
    create_cash_movement_entry,
    validate_cash_ledger_entry,
)


def test_krw_deposit_then_korean_stock_buy_reduces_cash_balance():
    ledger = [
        create_cash_movement_entry(
            event_type="deposit",
            currency="KRW",
            amount="10000000",
            event_date="2026-04-13",
        )
    ]
    ledger.extend(
        create_cash_ledger_entries_for_trade(
            {
                "transaction_type": "buy",
                "ticker": "005930",
                "market": "KR",
                "currency": "KRW",
                "display_name": "삼성전자",
                "unit_price": "70000",
                "quantity": "10",
                "fee": "1000",
                "tax": "0",
                "occurred_at": "2026-04-13",
            }
        )
    )

    assert calculate_cash_balances(ledger)["KRW"] == Decimal("9299000")


def test_usd_deposit_then_us_stock_buy_reduces_cash_balance():
    ledger = [
        create_cash_movement_entry(
            event_type="deposit",
            currency="USD",
            amount="1000",
            event_date="2026-04-13",
        )
    ]
    ledger.extend(
        create_cash_ledger_entries_for_trade(
            {
                "transaction_type": "buy",
                "ticker": "QURE",
                "market": "US",
                "currency": "USD",
                "display_name": "QURE",
                "unit_price": "41",
                "quantity": "10",
                "fee": "1",
                "tax": "0",
                "occurred_at": "2026-04-13",
            }
        )
    )

    assert calculate_cash_balances(ledger)["USD"] == Decimal("589")


def test_stock_sell_increases_cash_balance_after_fees_and_tax():
    ledger = [
        create_cash_movement_entry(
            event_type="deposit",
            currency="USD",
            amount="100",
            event_date="2026-04-13",
        )
    ]
    ledger.extend(
        create_cash_ledger_entries_for_trade(
            {
                "transaction_type": "sell",
                "ticker": "QURE",
                "market": "US",
                "currency": "USD",
                "display_name": "QURE",
                "unit_price": "50",
                "quantity": "2",
                "fee": "1",
                "tax": "2",
                "occurred_at": "2026-05-01",
            }
        )
    )

    assert calculate_cash_balances(ledger)["USD"] == Decimal("197")


def test_withdrawal_decreases_cash_balance():
    ledger = [
        create_cash_movement_entry(event_type="deposit", currency="KRW", amount="1000", event_date="2026-04-13"),
        create_cash_movement_entry(event_type="withdrawal", currency="KRW", amount="-250", event_date="2026-04-14"),
    ]

    assert calculate_cash_balances(ledger)["KRW"] == Decimal("750")


def test_fx_conversion_creates_out_and_in_cash_ledger_entries():
    ledger = [
        create_cash_movement_entry(event_type="deposit", currency="USD", amount="1000", event_date="2026-04-13"),
        create_cash_movement_entry(event_type="deposit", currency="KRW", amount="10000", event_date="2026-04-13"),
    ]
    ledger.extend(
        create_fx_conversion_entries(
            from_currency="USD",
            to_currency="KRW",
            from_amount="100",
            fx_rate_to_krw="1400",
            fee="1",
            event_date="2026-04-14",
        )
    )

    balances = calculate_cash_balances(ledger)

    assert balances["USD"] == Decimal("899")
    assert balances["KRW"] == Decimal("150000")


def test_cash_ledger_sum_matches_current_cash_balance():
    ledger = [
        create_cash_movement_entry(event_type="opening_balance", currency="KRW", amount="10000", event_date="2026-04-13"),
        create_cash_movement_entry(event_type="manual_adjustment", currency="KRW", amount="-500", event_date="2026-04-14"),
        create_cash_movement_entry(event_type="dividend", currency="USD", amount="12.50", event_date="2026-04-15"),
    ]

    balances = calculate_cash_balances(ledger)

    assert balances == {"KRW": Decimal("9500"), "USD": Decimal("12.50")}


@pytest.mark.parametrize(
    ("event_type", "amount"),
    [
        ("deposit", "-1"),
        ("withdrawal", "1"),
        ("buy_settlement", "0"),
        ("sell_settlement", "-1"),
    ],
)
def test_cash_ledger_entry_rejects_invalid_amount_signs(event_type, amount):
    with pytest.raises(ValueError):
        validate_cash_ledger_entry(
            {
                "event_date": "2026-04-13",
                "currency": "KRW",
                "event_type": event_type,
                "amount": amount,
            }
        )
