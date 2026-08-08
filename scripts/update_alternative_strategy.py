from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from portfolio.meta_strategy import MetaStrategyError, MetaStrategyInsufficientData
from portfolio.meta_strategy_alternative import (
    ALTERNATIVE_PIPELINE_VERSION,
    ALTERNATIVE_RULESET_VERSION,
    STRATEGY_ID,
    build_alternative_meta_strategy_signal,
    render_alternative_signal_markdown,
)
from portfolio.meta_strategy_artifacts import MetaStrategyArtifactStore, canonical_json_bytes
from portfolio.meta_strategy_calendar import TradingCalendarUnavailable, XNYSCalendar
from portfolio.meta_strategy_sources import OfficialMetaStrategySourceClient, OfficialSourceBundle


HISTORY_START_DATE = date(2010, 1, 1)
PRICE_START_DATE = date(2005, 3, 28)
STRATEGY_SPEC_PATH = (
    PROJECT_ROOT
    / "config"
    / "strategies"
    / "qqq_meta_v1_red_router_s1_n1_a1_v4_shadow_v3_0.kis.yaml"
)


def _store(root: Path) -> MetaStrategyArtifactStore:
    return MetaStrategyArtifactStore(root, markdown_renderer=render_alternative_signal_markdown)


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _write_raw_audit(bundle: OfficialSourceBundle, audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "strategy_id": STRATEGY_ID,
        "pipeline_version": ALTERNATIVE_PIPELINE_VERSION,
        "sources": [],
    }
    sources = manifest["sources"]
    assert isinstance(sources, list)
    for source in bundle.raw_sources:
        suffix = ".json" if source.name.startswith("tiingo_") else ".csv"
        path = audit_dir / f"{source.name}{suffix}"
        path.write_bytes(source.content)
        sources.append(
            {
                "name": source.name,
                "url": source.url,
                "sha256": source.sha256,
                "fetched_at_utc": source.fetched_at.isoformat(),
                "file": path.name,
            }
        )
    (audit_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _latest_date(bundle: OfficialSourceBundle, symbol: str) -> date | None:
    points = list(bundle.prices.get(symbol) or [])
    return points[-1].as_of_date if points else None


def _normalized_source_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(name): str(digest)
        for name, digest in sorted(value.items(), key=lambda item: str(item[0]))
    }


def _composite_input_hash(
    *,
    decision_session: date,
    source_hashes: Mapping[str, str],
) -> str:
    payload = {
        "decision_session": decision_session.isoformat(),
        "pipeline_version": ALTERNATIVE_PIPELINE_VERSION,
        "ruleset_version": ALTERNATIVE_RULESET_VERSION,
        "strategy_id": STRATEGY_ID,
        "strategy_spec_sha256": hashlib.sha256(STRATEGY_SPEC_PATH.read_bytes()).hexdigest(),
        "source_hashes": dict(source_hashes),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def run_update(
    *,
    output_root: Path,
    audit_dir: Path,
    run_slot: str,
    now: datetime,
    tiingo_token: str,
    calendar: XNYSCalendar | None = None,
    decision_session: date | None = None,
) -> int:
    store = _store(output_root)
    active_calendar = calendar or XNYSCalendar()
    active_decision_session = decision_session or active_calendar.latest_completed_session(now)
    previous = store.read_latest_signal()

    client = OfficialMetaStrategySourceClient(tiingo_token=tiingo_token)
    bundle = client.fetch_bundle(
        price_start_date=PRICE_START_DATE,
        fred_start_date=HISTORY_START_DATE,
        end_date=active_decision_session,
    )
    _write_raw_audit(bundle, audit_dir)
    source_hashes = _normalized_source_hashes(bundle.source_metadata.get("source_hashes"))
    composite_input_hash = _composite_input_hash(
        decision_session=active_decision_session,
        source_hashes=source_hashes,
    )
    previous_inputs = store.read_latest_inputs()
    previous_input_hash = (
        str(previous_inputs.get("composite_input_hash") or "")
        if previous_inputs is not None
        else ""
    )
    if (
        previous is not None
        and previous.get("decision_session") == active_decision_session.isoformat()
        and previous_input_hash == composite_input_hash
    ):
        store.write_run(
            status="NO_NEW_SESSION",
            run_slot=run_slot,
            decision_session=active_decision_session,
            message="같은 완료 거래일의 대안 shadow 원자료와 계산 버전이 변경되지 않았습니다.",
            details={"composite_input_hash": composite_input_hash},
            preserve_validated_latest=run_slot.startswith("retry-"),
            generated_at=now,
        )
        return 0

    qqq_latest = _latest_date(bundle, "QQQ")
    if qqq_latest != active_decision_session:
        raise MetaStrategyInsufficientData(
            f"Tiingo QQQ 최신 거래일 {qqq_latest}이 완료 거래일 {active_decision_session}과 일치하지 않습니다."
        )
    gld_latest = _latest_date(bundle, "GLD")
    if gld_latest is None:
        raise MetaStrategyInsufficientData("Tiingo GLD 조정종가가 없습니다.")

    planned_execution_session = active_calendar.next_session_after(active_decision_session)
    deferred_due_session = active_calendar.session_offset(planned_execution_session, 60)
    source_metadata = dict(bundle.source_metadata)
    source_metadata.update(
        {
            "composite_input_hash": composite_input_hash,
            "strategy_id": STRATEGY_ID,
            "strategy_spec": STRATEGY_SPEC_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "strategy_spec_sha256": hashlib.sha256(STRATEGY_SPEC_PATH.read_bytes()).hexdigest(),
        }
    )
    signal = build_alternative_meta_strategy_signal(
        qqq_points=bundle.prices["QQQ"],
        gld_points=bundle.prices["GLD"],
        liquidity_series=bundle.fred_series,
        router_series=bundle.fred_series,
        decision_session=active_decision_session,
        planned_execution_session=planned_execution_session,
        deferred_due_session=deferred_due_session,
        next_session_after=active_calendar.next_session_after,
        generated_at=now,
        source_metadata=source_metadata,
    )
    liquidity = signal.get("liquidity") if isinstance(signal.get("liquidity"), dict) else {}
    normalized_inputs = {
        "generated_at_utc": now.isoformat(),
        "decision_session": active_decision_session.isoformat(),
        "pipeline_version": ALTERNATIVE_PIPELINE_VERSION,
        "ruleset_version": ALTERNATIVE_RULESET_VERSION,
        "strategy_id": STRATEGY_ID,
        "strategy_spec_sha256": hashlib.sha256(STRATEGY_SPEC_PATH.read_bytes()).hexdigest(),
        "composite_input_hash": composite_input_hash,
        "latest_price_dates": {
            "QQQ": qqq_latest.isoformat() if qqq_latest else None,
            "GLD": gld_latest.isoformat() if gld_latest else None,
        },
        "source_hashes": source_hashes,
        "liquidity_lineage": {
            "observation_date": liquidity.get("observation_date"),
            "percentile_source_observation_date": liquidity.get("percentile_source_observation_date"),
            "percentile_source_label_date": liquidity.get("percentile_source_label_date"),
            "signal_label_date": liquidity.get("signal_label_date"),
            "rank_less": liquidity.get("rank_less"),
            "rank_equal": liquidity.get("rank_equal"),
            "rank_denominator": liquidity.get("rank_denominator"),
            "percentile": liquidity.get("percentile"),
        },
    }
    written = store.write_validated(signal, normalized_inputs=normalized_inputs)
    n1 = written.get("n1_overlay") if isinstance(written.get("n1_overlay"), dict) else {}
    a1 = written.get("a1_overlay") if isinstance(written.get("a1_overlay"), dict) else {}
    entry = written.get("entry_filter_v4") if isinstance(written.get("entry_filter_v4"), dict) else {}
    store.write_run(
        status="VALIDATED",
        run_slot=run_slot,
        decision_session=active_decision_session,
        message="대안 N1/A1/V4 shadow v3.0 판정과 산출물을 갱신했습니다.",
        details={
            "signal_hash": written.get("signal_hash"),
            "planned_execution_session": written.get("planned_execution_session"),
            "base_execution_target": written.get("base_execution_target"),
            "resolved_execution_target": written.get("resolved_execution_target"),
            "n1_applied": n1.get("applied"),
            "a1_event": a1.get("event"),
            "a1_active": a1.get("active"),
            "entry_v4_triggered": entry.get("triggered"),
        },
        generated_at=now,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update the separate N1/A1/V4 alternative shadow v3.0 signal."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--run-slot", default="manual")
    parser.add_argument("--now", help="Optional ISO-8601 UTC timestamp for deterministic runs.")
    args = parser.parse_args(argv)
    now = _parse_datetime(args.now)
    token = str(os.environ.get("TIINGO_API_TOKEN") or "").strip()
    store = _store(args.output_root)
    decision_session: date | None = None
    try:
        if not token:
            store.write_run(
                status="CONFIG_FAILED",
                run_slot=args.run_slot,
                decision_session=None,
                message="TIINGO_API_TOKEN이 설정되지 않았습니다.",
                generated_at=now,
            )
            return 2
        calendar = XNYSCalendar()
        decision_session = calendar.latest_completed_session(now)
        return run_update(
            output_root=args.output_root,
            audit_dir=args.audit_dir,
            run_slot=args.run_slot,
            now=now,
            tiingo_token=token,
            calendar=calendar,
            decision_session=decision_session,
        )
    except (MetaStrategyInsufficientData, TradingCalendarUnavailable) as exc:
        store.write_run(
            status="VALIDATION_FAILED",
            run_slot=args.run_slot,
            decision_session=decision_session,
            message=str(exc),
            details={"error_type": type(exc).__name__},
            generated_at=now,
        )
        return 3
    except MetaStrategyError as exc:
        store.write_run(
            status="SOURCE_FAILED",
            run_slot=args.run_slot,
            decision_session=decision_session,
            message=str(exc),
            details={"error_type": type(exc).__name__},
            generated_at=now,
        )
        return 4
    except Exception as exc:
        store.write_run(
            status="UNEXPECTED_FAILED",
            run_slot=args.run_slot,
            decision_session=decision_session,
            message=str(exc),
            details={
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(limit=8),
            },
            generated_at=now,
        )
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
