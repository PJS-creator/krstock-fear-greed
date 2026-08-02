from datetime import date, datetime, timedelta, timezone
import json

from portfolio.meta_strategy import DatedValue
from portfolio.meta_strategy_artifacts import MetaStrategyArtifactStore
from portfolio.meta_strategy_sources import OfficialSourceBundle
from scripts import update_alternative_strategy
from scripts.update_alternative_strategy import main


class _Calendar:
    @staticmethod
    def next_session_after(value):
        return value + timedelta(days=1)

    @staticmethod
    def session_offset(value, offset):
        return value + timedelta(days=offset)


def _bundle(decision_session: date, source_digest: str) -> OfficialSourceBundle:
    return OfficialSourceBundle(
        prices={
            "QQQ": [DatedValue(decision_session, 500.0)],
            "GLD": [DatedValue(decision_session, 200.0)],
        },
        fred_series={},
        raw_sources=(),
        source_metadata={"source_hashes": {"shared": source_digest}},
    )


def _validated_signal(decision_session: date) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pipeline_version": update_alternative_strategy.ALTERNATIVE_PIPELINE_VERSION,
        "ruleset_version": update_alternative_strategy.ALTERNATIVE_RULESET_VERSION,
        "strategy_id": update_alternative_strategy.STRATEGY_ID,
        "status": "VALIDATED",
        "generated_at_utc": "2026-08-01T00:00:00+00:00",
        "decision_session": decision_session.isoformat(),
        "planned_execution_session": (decision_session + timedelta(days=1)).isoformat(),
        "base_execution_target": "QLD",
        "resolved_execution_target": "QQQ",
        "overall_execution_target": "QQQ",
        "n1_overlay": {"applied": True},
        "entry_filter_v4": {"triggered": True},
        "liquidity": {},
    }


def test_alternative_script_records_missing_secret_in_its_own_root(tmp_path, monkeypatch):
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    output = tmp_path / "alternative-data"

    exit_code = main(
        [
            "--output-root",
            str(output),
            "--audit-dir",
            str(tmp_path / "audit"),
            "--run-slot",
            "manual",
            "--now",
            "2026-07-26T00:00:00Z",
        ]
    )

    run = json.loads((output / "runs" / "latest_run.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert run["status"] == "CONFIG_FAILED"
    assert not (output / "signals" / "latest_validated.json").exists()


def test_alternative_input_hash_includes_its_strategy_contract():
    digest = update_alternative_strategy._composite_input_hash(
        decision_session=date(2026, 7, 31),
        source_hashes={"shared": "abc"},
    )
    reordered = update_alternative_strategy._composite_input_hash(
        decision_session=date(2026, 7, 31),
        source_hashes={"shared": "abc"},
    )

    assert digest == reordered
    assert digest
    assert update_alternative_strategy.STRATEGY_SPEC_PATH.exists()


def test_same_session_skips_only_when_alternative_inputs_are_unchanged(tmp_path, monkeypatch):
    decision_session = date(2026, 7, 31)
    bundle = _bundle(decision_session, "same")
    composite_hash = update_alternative_strategy._composite_input_hash(
        decision_session=decision_session,
        source_hashes={"shared": "same"},
    )
    store = MetaStrategyArtifactStore(tmp_path / "alternative-data")
    store.write_validated(
        _validated_signal(decision_session),
        normalized_inputs={"composite_input_hash": composite_hash},
    )

    class _Client:
        def __init__(self, *, tiingo_token):
            assert tiingo_token == "token"

        def fetch_bundle(self, **kwargs):
            return bundle

    monkeypatch.setattr(update_alternative_strategy, "OfficialMetaStrategySourceClient", _Client)
    monkeypatch.setattr(
        update_alternative_strategy,
        "build_alternative_meta_strategy_signal",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("unchanged inputs must not rebuild")),
    )

    exit_code = update_alternative_strategy.run_update(
        output_root=tmp_path / "alternative-data",
        audit_dir=tmp_path / "audit",
        run_slot="manual",
        now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        tiingo_token="token",
        calendar=_Calendar(),
        decision_session=decision_session,
    )

    assert exit_code == 0
    assert update_alternative_strategy._store(tmp_path / "alternative-data").read_latest_run()[
        "status"
    ] == "NO_NEW_SESSION"


def test_changed_source_rebuilds_and_records_resolved_target(tmp_path, monkeypatch):
    decision_session = date(2026, 7, 31)
    bundle = _bundle(decision_session, "revised")

    class _Client:
        def __init__(self, *, tiingo_token):
            assert tiingo_token == "token"

        def fetch_bundle(self, **kwargs):
            return bundle

    monkeypatch.setattr(update_alternative_strategy, "OfficialMetaStrategySourceClient", _Client)
    monkeypatch.setattr(
        update_alternative_strategy,
        "build_alternative_meta_strategy_signal",
        lambda **kwargs: _validated_signal(decision_session),
    )

    exit_code = update_alternative_strategy.run_update(
        output_root=tmp_path / "alternative-data",
        audit_dir=tmp_path / "audit",
        run_slot="manual",
        now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        tiingo_token="token",
        calendar=_Calendar(),
        decision_session=decision_session,
    )

    assert exit_code == 0
    store = update_alternative_strategy._store(tmp_path / "alternative-data")
    assert store.read_latest_signal()["resolved_execution_target"] == "QQQ"
    assert store.read_latest_run()["details"]["n1_applied"] is True
    assert store.read_latest_inputs()["strategy_id"] == update_alternative_strategy.STRATEGY_ID
    assert len(store.read_latest_inputs()["strategy_spec_sha256"]) == 64
