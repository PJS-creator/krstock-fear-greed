from portfolio.journal import build_journal_events, filter_journal_events, normalize_journal_note


def _buy_transaction():
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "transaction_type": "buy",
        "ticker": "QURE",
        "market": "US",
        "currency": "USD",
        "display_name": "QURE",
        "unit_price": 41,
        "quantity": 10,
        "fee": 1,
        "tax": 0,
        "occurred_at": "2026-04-13",
    }


def test_transaction_and_linked_cash_ledger_are_single_journal_event():
    events = build_journal_events(
        transactions=[_buy_transaction()],
        cash_ledger=[
            {
                "event_date": "2026-04-13",
                "currency": "USD",
                "event_type": "buy_settlement",
                "amount": "-411",
                "linked_transaction_id": "11111111-1111-1111-1111-111111111111",
            }
        ],
    )

    assert len(events) == 1
    assert events[0].event_type == "buy"
    assert events[0].cash_impact == -411


def test_transaction_and_matching_unlinked_cash_ledger_are_single_journal_event():
    events = build_journal_events(
        transactions=[_buy_transaction()],
        cash_ledger=[
            {
                "event_date": "2026-04-13",
                "currency": "USD",
                "event_type": "buy_settlement",
                "amount": "-411",
                "memo": "QURE buy",
            }
        ],
    )

    assert len(events) == 1
    assert events[0].event_type == "buy"
    assert events[0].cash_impact == -411


def test_independent_deposit_and_dividend_become_events():
    events = build_journal_events(
        cash_ledger=[
            {"event_date": "2026-04-12", "currency": "KRW", "event_type": "deposit", "amount": "1000000"},
            {"event_date": "2026-04-20", "currency": "USD", "event_type": "dividend", "amount": "10"},
        ]
    )

    assert [event.event_type for event in events] == ["dividend", "deposit"]


def test_fx_conversion_out_and_in_are_grouped():
    events = build_journal_events(
        cash_ledger=[
            {"event_date": "2026-04-15", "currency": "KRW", "event_type": "fx_conversion_out", "amount": "-130000", "fx_rate_to_krw": "1300", "memo": "KRW->USD 환전 출금"},
            {"event_date": "2026-04-15", "currency": "USD", "event_type": "fx_conversion_in", "amount": "100", "fx_rate_to_krw": "1300", "memo": "KRW->USD 환전 입금"},
        ]
    )

    assert len(events) == 1
    assert events[0].event_type == "fx_conversion"
    assert "KRW -> 100" in events[0].subtitle


def test_manual_note_event_and_filtering():
    note = normalize_journal_note({"note_date": "2026-04-21", "title": "실수 복기", "body": "늦은 진입", "symbol": "QURE", "tags": ["복기"]})
    events = build_journal_events(transactions=[_buy_transaction()], journal_notes=[note])

    note_events = filter_journal_events(events, event_group="메모")
    qure_events = filter_journal_events(events, symbol="QURE")

    assert len(note_events) == 1
    assert note_events[0].title == "실수 복기"
    assert len(qure_events) == 2


def test_journal_events_sort_newest_first_by_default():
    events = build_journal_events(
        cash_ledger=[
            {"event_date": "2026-04-12", "currency": "KRW", "event_type": "deposit", "amount": "1000000"},
            {"event_date": "2026-04-20", "currency": "KRW", "event_type": "withdrawal", "amount": "-100000"},
        ]
    )

    assert [event.event_date for event in events] == ["2026-04-20", "2026-04-12"]
