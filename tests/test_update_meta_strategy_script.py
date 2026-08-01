from datetime import date, datetime, timedelta, timezone
import json

from portfolio.meta_strategy import DatedValue
from portfolio.meta_strategy_artifacts import MetaStrategyArtifactStore
from portfolio.meta_strategy_sources import OfficialSourceBundle
from scripts import update_meta_strategy
from scripts.update_meta_strategy import main


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
        source_metadata={"source_hashes": {"official": source_digest}},
    )


def _validated_signal(decision_session: date) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pipeline_version": update_meta_strategy.PIPELINE_VERSION,
        "ruleset_version": update_meta_strategy.RULESET_VERSION,
        "status": "VALIDATED",
        "generated_at_utc": "2026-08-01T00:00:00+00:00",
        "decision_session": decision_session.isoformat(),
        "planned_execution_session": (decision_session + timedelta(days=1)).isoformat(),
        "liquidity": {},
    }


def test_script_records_configuration_failure_without_overwriting_signal(tmp_path, monkeypatch):
    monkeypatch.delenv("TIINGO_API_TOKEN", raising=False)
    output = tmp_path / "data"

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


def test_composite_input_hash_is_stable_for_source_hash_order():
    decision_session = date(2026, 7, 31)

    first = update_meta_strategy._composite_input_hash(
        decision_session=decision_session,
        source_hashes={"qqq": "a", "fred": "b"},
    )
    second = update_meta_strategy._composite_input_hash(
        decision_session=decision_session,
        source_hashes={"fred": "b", "qqq": "a"},
    )

    assert first == second


def test_same_session_refetches_but_skips_when_official_inputs_are_unchanged(tmp_path, monkeypatch):
    decision_session = date(2026, 7, 31)
    bundle = _bundle(decision_session, "same-source")
    composite_hash = update_meta_strategy._composite_input_hash(
        decision_session=decision_session,
        source_hashes={"official": "same-source"},
    )
    store = MetaStrategyArtifactStore(tmp_path / "data")
    store.write_validated(
        _validated_signal(decision_session),
        normalized_inputs={"composite_input_hash": composite_hash},
    )
    fetches = []

    class _Client:
        def __init__(self, *, tiingo_token):
            assert tiingo_token == "token"

        def fetch_bundle(self, **kwargs):
            fetches.append(kwargs)
            return bundle

    monkeypatch.setattr(update_meta_strategy, "OfficialMetaStrategySourceClient", _Client)
    monkeypatch.setattr(
        update_meta_strategy,
        "build_official_meta_strategy_signal",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("unchanged inputs must not rebuild")),
    )

    exit_code = update_meta_strategy.run_update(
        output_root=tmp_path / "data",
        audit_dir=tmp_path / "audit",
        run_slot="manual",
        now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        tiingo_token="token",
        calendar=_Calendar(),
        decision_session=decision_session,
    )

    assert exit_code == 0
    assert len(fetches) == 1
    assert store.read_latest_run()["status"] == "NO_NEW_SESSION"
    assert (tmp_path / "audit" / "manifest.json").exists()


def test_same_session_rebuilds_when_official_source_hash_changes(tmp_path, monkeypatch):
    decision_session = date(2026, 7, 31)
    bundle = _bundle(decision_session, "revised-source")
    store = MetaStrategyArtifactStore(tmp_path / "data")
    store.write_validated(
        _validated_signal(decision_session),
        normalized_inputs={"composite_input_hash": "old-input"},
    )
    builds = []

    class _Client:
        def __init__(self, *, tiingo_token):
            assert tiingo_token == "token"

        def fetch_bundle(self, **kwargs):
            return bundle

    def _build(**kwargs):
        builds.append(kwargs)
        return _validated_signal(decision_session)

    monkeypatch.setattr(update_meta_strategy, "OfficialMetaStrategySourceClient", _Client)
    monkeypatch.setattr(update_meta_strategy, "build_official_meta_strategy_signal", _build)

    exit_code = update_meta_strategy.run_update(
        output_root=tmp_path / "data",
        audit_dir=tmp_path / "audit",
        run_slot="manual",
        now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        tiingo_token="token",
        calendar=_Calendar(),
        decision_session=decision_session,
    )

    assert exit_code == 0
    assert len(builds) == 1
    assert builds[0]["source_metadata"]["composite_input_hash"]
    assert store.read_latest_run()["status"] == "VALIDATED"
    latest_inputs = store.read_latest_inputs()
    assert latest_inputs["composite_input_hash"] != "old-input"
    assert latest_inputs["source_hashes"] == {"official": "revised-source"}
