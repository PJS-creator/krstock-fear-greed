from datetime import datetime, timedelta, timezone

from portfolio.chart_data import contribution_frame, currency_exposure_frame, history_frame, holdings_allocation_frame
from portfolio.diagnostics import calculate_diagnostics
from portfolio.history import MemoryPortfolioHistoryStore, build_history_record
from portfolio.holdings import build_portfolio_metrics
from portfolio.storage import serialize_portfolio_payload


def _metrics(quantity=2):
    return build_portfolio_metrics(
        [
            {"ticker": "AAA", "quantity": quantity, "current_price": 10, "previous_close": 9, "avg_price": 8, "strategy_tag": "Core"},
            {"ticker": "BBB", "quantity": 1, "current_price": 20, "previous_close": 22, "avg_price": 25, "strategy_tag": "Core"},
        ],
        cash_krw=100,
        cash_usd=1,
        usd_krw=1000,
    )


def test_history_snapshot_creation_and_fingerprint_deduplication():
    store = MemoryPortfolioHistoryStore()
    record = build_history_record(owner_id="owner", portfolio_name="main", event_type="manual_capture", metrics=_metrics())

    first = store.save_snapshot(record)
    second = store.save_snapshot(record)

    assert first.id == second.id
    assert len(store.list_history("owner", "main")) == 1
    assert first.fingerprint
    assert first.total_value_krw > 0


def test_history_snapshot_keeps_full_portfolio_backup_and_fingerprints_transactions():
    metrics = _metrics()
    base_payload = serialize_portfolio_payload(
        [row.holding for row in metrics.rows],
        usd_krw=metrics.usd_krw,
        cash_krw=metrics.cash.cash_krw,
        cash_usd=metrics.cash.cash_usd,
    )
    changed_payload = {
        **base_payload,
        "transactions": [
            {
                "transaction_type": "buy",
                "ticker": "AAA",
                "display_name": "AAA",
                "market": "US",
                "currency": "USD",
                "unit_price": 8,
                "quantity": 2,
                "fee": 0,
                "tax": 0,
                "occurred_at": "2026-01-01",
                "memo": "backup check",
            }
        ],
    }

    first = build_history_record(
        owner_id="owner",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=metrics,
        portfolio_payload=base_payload,
    )
    changed = build_history_record(
        owner_id="owner",
        portfolio_name="main",
        event_type="portfolio_save",
        metrics=metrics,
        portfolio_payload=changed_payload,
    )

    assert first.payload_json["schema_version"] == 2
    assert first.payload_json["portfolio_backup"] == base_payload
    assert first.fingerprint != changed.fingerprint


def test_history_period_filter():
    store = MemoryPortfolioHistoryStore()
    now = datetime.now(timezone.utc)
    old = build_history_record(
        owner_id="owner",
        portfolio_name="main",
        event_type="manual_capture",
        metrics=_metrics(quantity=2),
        captured_at=(now - timedelta(days=40)).isoformat(),
    )
    recent = build_history_record(
        owner_id="owner",
        portfolio_name="main",
        event_type="holdings_changed",
        metrics=_metrics(quantity=3),
        captured_at=now.isoformat(),
    )

    store.save_snapshot(old)
    store.save_snapshot(recent)

    assert len(store.list_history("owner", "main", period="all")) == 2
    assert len(store.list_history("owner", "main", period="1w")) == 1


def test_diagnostics_calculation_is_objective_and_handles_coverage():
    diagnostics = calculate_diagnostics(_metrics())
    keys = {item.key for item in diagnostics}

    assert "max_position_weight" in keys
    assert "hhi" in keys
    assert "cost_basis_coverage" in keys
    assert all("매수" not in item.message and "매도" not in item.message for item in diagnostics)


def test_chart_dataframe_builders():
    metrics = _metrics()
    records = [
        build_history_record(owner_id="owner", portfolio_name="main", event_type="manual_capture", metrics=metrics),
        build_history_record(owner_id="owner", portfolio_name="main", event_type="holdings_changed", metrics=_metrics(quantity=3)),
    ]

    assert not holdings_allocation_frame(metrics).empty
    assert not contribution_frame(metrics).empty
    assert not currency_exposure_frame(metrics).empty
    assert not history_frame(records).empty
