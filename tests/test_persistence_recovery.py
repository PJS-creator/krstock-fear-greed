from __future__ import annotations

from portfolio.history import build_history_record
from portfolio.holdings import build_portfolio_metrics
from portfolio.persistence import portfolio_payload_has_data, recover_portfolio_payload_from_history
from portfolio.storage import deserialize_portfolio_payload_v2, serialize_portfolio_payload


def _holding(ticker: str = "005930") -> dict[str, object]:
    return {
        "ticker": ticker,
        "display_name": "삼성전자" if ticker == "005930" else ticker,
        "market": "KR",
        "currency": "KRW",
        "quantity": 10,
        "avg_price": 70_000,
        "current_price": 75_000,
        "previous_close": 74_000,
    }


def _payload(*, ticker: str = "005930", cash_krw: float = 1_000_000) -> dict[str, object]:
    return serialize_portfolio_payload(
        [_holding(ticker)],
        usd_krw=1_350,
        cash_krw=cash_krw,
        cash_usd=100,
        transactions=[
            {
                "transaction_type": "buy",
                "ticker": ticker,
                "display_name": ticker,
                "market": "KR",
                "currency": "KRW",
                "unit_price": 70_000,
                "quantity": 10,
                "fee": 0,
                "tax": 0,
                "occurred_at": "2026-04-08",
            }
        ],
        cash_ledger=[
            {
                "event_date": "2026-04-01",
                "currency": "KRW",
                "event_type": "deposit",
                "amount": str(cash_krw),
            }
        ],
    )


def test_portfolio_payload_has_data_distinguishes_real_and_empty_state():
    empty = serialize_portfolio_payload([], usd_krw=1_350, cash_krw=0, cash_usd=0)

    assert not portfolio_payload_has_data(empty)
    assert portfolio_payload_has_data(_payload())
    assert portfolio_payload_has_data(
        serialize_portfolio_payload([], usd_krw=1_350, cash_krw=10_000, cash_usd=0)
    )


def test_history_recovery_prefers_full_portfolio_backup():
    full_payload = _payload()
    metrics = build_portfolio_metrics([_holding()], cash_krw=1_000_000, cash_usd=100, usd_krw=1_350)
    record = build_history_record(
        owner_id="owner-a",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=metrics,
        portfolio_payload=full_payload,
    )

    recovered = recover_portfolio_payload_from_history(
        [record], owner_id="owner-a", portfolio_name="main"
    )
    clean = deserialize_portfolio_payload_v2(recovered)

    assert clean["holdings"][0]["ticker"] == "005930"
    assert clean["transactions"][0]["ticker"] == "005930"
    assert clean["cash_ledger"][0]["event_type"] == "deposit"


def test_history_recovery_uses_legacy_metrics_snapshot_and_skips_other_owner():
    metrics = build_portfolio_metrics([_holding()], cash_krw=1_000_000, cash_usd=100, usd_krw=1_350)
    other_owner = build_history_record(
        owner_id="owner-b",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=metrics,
    )
    owner_record = build_history_record(
        owner_id="owner-a",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=metrics,
    )

    recovered = recover_portfolio_payload_from_history(
        [owner_record, other_owner], owner_id="owner-a", portfolio_name="main"
    )
    clean = deserialize_portfolio_payload_v2(recovered)

    assert clean["holdings"][0]["ticker"] == "005930"
    assert clean["cash_balances"] == {"KRW": 1_000_000.0, "USD": 100.0}
    assert clean["transactions"] == []


def test_history_recovery_skips_newer_empty_snapshot():
    populated_metrics = build_portfolio_metrics([_holding()], cash_krw=500_000, cash_usd=0, usd_krw=1_350)
    empty_metrics = build_portfolio_metrics([], cash_krw=0, cash_usd=0, usd_krw=1_350)
    older = build_history_record(
        owner_id="owner-a",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=populated_metrics,
        captured_at="2026-07-01T00:00:00+00:00",
    )
    newer = build_history_record(
        owner_id="owner-a",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=empty_metrics,
        captured_at="2026-07-02T00:00:00+00:00",
    )

    recovered = recover_portfolio_payload_from_history(
        [older, newer], owner_id="owner-a", portfolio_name="main"
    )

    assert deserialize_portfolio_payload_v2(recovered)["holdings"][0]["ticker"] == "005930"
