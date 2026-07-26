from datetime import date, datetime, timezone
import json

from portfolio.meta_strategy_artifacts import MetaStrategyArtifactStore


def _signal(decision_session: str = "2026-07-24") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pipeline_version": "test",
        "ruleset_version": "test",
        "status": "VALIDATED",
        "generated_at_utc": "2026-07-25T00:00:00+00:00",
        "decision_session": decision_session,
        "planned_execution_session": "2026-07-27",
        "market_regime": "MIXED",
        "market_regime_label": "혼재장",
        "active_strategy": "comparison3",
        "active_strategy_label": "비교3",
        "router_target": None,
        "overall_execution_target": "QLD",
        "liquidity": {
            "percentile": 81.9230769231,
            "rank_less": 213,
            "rank_equal": 0,
            "rank_denominator": 260,
        },
        "qqq": {},
        "red_router": {},
        "entry_advice": {},
        "rsi_reference": {},
    }


def test_validated_signal_writes_durable_and_compatibility_outputs(tmp_path):
    store = MetaStrategyArtifactStore(tmp_path)

    written = store.write_validated(_signal(), normalized_inputs={"source_hashes": {"qqq": "abc"}})

    assert written["signal_hash"]
    assert (tmp_path / "signals" / "latest_validated.json").exists()
    assert (tmp_path / "signals" / "history" / "2026-07-24.json").exists()
    assert (tmp_path / "latest_signal.json").exists()
    assert (tmp_path / "latest_signal.md").exists()
    assert (tmp_path / "state" / "latest_state.json").exists()
    assert (tmp_path / "normalized" / "latest_inputs.json").exists()


def test_retry_no_new_session_preserves_latest_validated_run(tmp_path):
    store = MetaStrategyArtifactStore(tmp_path)
    store.write_run(
        status="VALIDATED",
        run_slot="primary-0737-kst",
        decision_session=date(2026, 7, 24),
        message="ok",
        generated_at=datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc),
    )

    store.write_run(
        status="NO_NEW_SESSION",
        run_slot="retry-0757-kst",
        decision_session=date(2026, 7, 24),
        message="already done",
        preserve_validated_latest=True,
        generated_at=datetime(2026, 7, 25, 0, 20, tzinfo=timezone.utc),
    )

    latest = json.loads((tmp_path / "runs" / "latest_run.json").read_text(encoding="utf-8"))
    histories = list((tmp_path / "runs" / "history").glob("*.json"))
    assert latest["status"] == "VALIDATED"
    assert len(histories) == 2


def test_retry_preserves_primary_no_new_session_status(tmp_path):
    store = MetaStrategyArtifactStore(tmp_path)
    store.write_run(
        status="NO_NEW_SESSION",
        run_slot="primary-0737-kst",
        decision_session=date(2026, 7, 24),
        message="weekend",
        generated_at=datetime(2026, 7, 26, 22, 37, tzinfo=timezone.utc),
    )

    store.write_run(
        status="NO_NEW_SESSION",
        run_slot="retry-0757-kst",
        decision_session=date(2026, 7, 24),
        message="weekend retry",
        preserve_validated_latest=True,
        generated_at=datetime(2026, 7, 26, 22, 57, tzinfo=timezone.utc),
    )

    latest = json.loads((tmp_path / "runs" / "latest_run.json").read_text(encoding="utf-8"))
    assert latest["run_slot"] == "primary-0737-kst"
    assert latest["status"] == "NO_NEW_SESSION"


def test_failed_run_does_not_overwrite_last_validated_signal(tmp_path):
    store = MetaStrategyArtifactStore(tmp_path)
    store.write_validated(_signal())
    before = (tmp_path / "signals" / "latest_validated.json").read_bytes()

    store.write_run(
        status="SOURCE_FAILED",
        run_slot="primary-0737-kst",
        decision_session=date(2026, 7, 25),
        message="source unavailable",
    )

    assert (tmp_path / "signals" / "latest_validated.json").read_bytes() == before
