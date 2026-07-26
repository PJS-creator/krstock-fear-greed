from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping


RUN_STATUSES = {
    "VALIDATED",
    "NO_NEW_SESSION",
    "CONFIG_FAILED",
    "SOURCE_FAILED",
    "VALIDATION_FAILED",
    "UNEXPECTED_FAILED",
}


def canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def signal_hash(payload: Mapping[str, object]) -> str:
    content = dict(payload)
    content.pop("signal_hash", None)
    return hashlib.sha256(canonical_json_bytes(content)).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _markdown_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return str(value)


def render_signal_markdown(payload: Mapping[str, object]) -> str:
    liquidity = payload.get("liquidity") if isinstance(payload.get("liquidity"), Mapping) else {}
    qqq = payload.get("qqq") if isinstance(payload.get("qqq"), Mapping) else {}
    router = payload.get("red_router") if isinstance(payload.get("red_router"), Mapping) else {}
    entry = payload.get("entry_advice") if isinstance(payload.get("entry_advice"), Mapping) else {}
    rsi = payload.get("rsi_reference") if isinstance(payload.get("rsi_reference"), Mapping) else {}
    reason_codes = router.get("reason_codes") if isinstance(router.get("reason_codes"), list) else []
    lines = [
        "# RED Router-S1 일일 판정",
        "",
        f"- 판정 거래일: {_markdown_value(payload.get('decision_session'))}",
        f"- 예정 실행일: {_markdown_value(payload.get('planned_execution_session'))}",
        f"- 시장구간: {_markdown_value(payload.get('market_regime_label'))}",
        f"- 활성화 전략: {_markdown_value(payload.get('active_strategy_label'))}",
        f"- Router 목표자산: {_markdown_value(payload.get('router_target'))}",
        f"- 최종 실행 목표자산: {_markdown_value(payload.get('overall_execution_target'))}",
        "",
        "## 유동성",
        "",
        f"- 적용 P: {_markdown_value(liquidity.get('percentile'))}",
        (
            "- 순위 계보: "
            f"less={_markdown_value(liquidity.get('rank_less'))}, "
            f"equal={_markdown_value(liquidity.get('rank_equal'))}, "
            f"denominator={_markdown_value(liquidity.get('rank_denominator'))}"
        ),
        f"- 원 관측일: {_markdown_value(liquidity.get('observation_date'))}",
        f"- P 원천 관측일: {_markdown_value(liquidity.get('percentile_source_observation_date'))}",
        f"- P 원천 주간: {_markdown_value(liquidity.get('percentile_source_label_date'))}",
        f"- 적용 주간: {_markdown_value(liquidity.get('signal_label_date'))}",
        f"- 적용 시작 거래일: {_markdown_value(liquidity.get('effective_from_session'))}",
        "",
        "## QQQ와 Router",
        "",
        f"- QQQ 종가: {_markdown_value(qqq.get('close'))}",
        f"- SMA50: {_markdown_value(qqq.get('sma50'))}",
        f"- Trend200: {_markdown_value(qqq.get('trend200'))}",
        f"- 회복 상태: {_markdown_value(qqq.get('recovery'))}",
        f"- 비교1 원시/확정: {_markdown_value(qqq.get('comparison1_raw_state'))} / {_markdown_value(qqq.get('comparison1_confirmed_state'))}",
        f"- Router 사유: {', '.join(str(item) for item in reason_codes) or '-'}",
        "",
        "## 신규 자금 유입 시 적용",
        "",
        f"- 집행 방식: {_markdown_value(entry.get('mode'))}",
        f"- QQQ SMA50 상방이격률: {_markdown_value(entry.get('qqq_sma50_upper_distance_pct'))}%",
        f"- 즉시 집행: {_markdown_value(entry.get('immediate_weight_pct'))}% → {_markdown_value(entry.get('immediate_target'))}",
        f"- 유예 집행: {_markdown_value(entry.get('deferred_weight_pct'))}%",
        f"- 유예 예정일: {_markdown_value(entry.get('deferred_due_session'))}",
        "",
        "## RSI 참고 경고",
        "",
        f"- RSI14: {_markdown_value(rsi.get('latest_rsi14'))}",
        f"- 경고 여부: {_markdown_value(rsi.get('warning'))}",
        f"- 최근 추세: {_markdown_value(rsi.get('trend_label'))}",
        f"- 5거래일 누적 수익률: {_markdown_value(rsi.get('five_session_return_pct'))}%",
        "",
        "> 이 결과는 규칙 기반 계산이며 자동 매매나 투자 조언이 아닙니다.",
        "",
    ]
    return "\n".join(lines)


class MetaStrategyArtifactStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    @property
    def latest_signal_path(self) -> Path:
        return self.root / "signals" / "latest_validated.json"

    @property
    def latest_run_path(self) -> Path:
        return self.root / "runs" / "latest_run.json"

    def read_latest_signal(self) -> dict[str, object] | None:
        return _read_json(self.latest_signal_path)

    def read_latest_run(self) -> dict[str, object] | None:
        return _read_json(self.latest_run_path)

    def write_validated(
        self,
        payload: Mapping[str, object],
        *,
        normalized_inputs: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        signal = dict(payload)
        signal["signal_hash"] = signal_hash(signal)
        decision_session = str(signal.get("decision_session") or "unknown")
        json_bytes = canonical_json_bytes(signal)
        markdown_bytes = render_signal_markdown(signal).encode("utf-8")
        _atomic_write(self.latest_signal_path, json_bytes)
        _atomic_write(self.root / "signals" / "latest_validated.md", markdown_bytes)
        _atomic_write(self.root / "signals" / "history" / f"{decision_session}.json", json_bytes)
        _atomic_write(self.root / "signals" / "history" / f"{decision_session}.md", markdown_bytes)
        _atomic_write(self.root / "latest_signal.json", json_bytes)
        _atomic_write(self.root / "latest_signal.md", markdown_bytes)
        if normalized_inputs is not None:
            _atomic_write(
                self.root / "normalized" / "latest_inputs.json",
                canonical_json_bytes(dict(normalized_inputs)),
            )
        state = {
            "schema_version": signal.get("schema_version"),
            "pipeline_version": signal.get("pipeline_version"),
            "ruleset_version": signal.get("ruleset_version"),
            "decision_session": signal.get("decision_session"),
            "market_regime": signal.get("market_regime"),
            "active_strategy": signal.get("active_strategy"),
            "router_target": signal.get("router_target"),
            "overall_execution_target": signal.get("overall_execution_target"),
            "signal_hash": signal["signal_hash"],
            "updated_at_utc": signal.get("generated_at_utc"),
        }
        _atomic_write(
            self.root / "state" / "latest_state.json",
            canonical_json_bytes(state),
        )
        return signal

    def write_run(
        self,
        *,
        status: str,
        run_slot: str,
        decision_session: date | str | None,
        message: str,
        details: Mapping[str, object] | None = None,
        preserve_validated_latest: bool = False,
        generated_at: datetime | None = None,
    ) -> dict[str, object]:
        if status not in RUN_STATUSES:
            raise ValueError(f"unsupported run status: {status}")
        now = generated_at or datetime.now(timezone.utc)
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "status": status,
            "run_slot": run_slot,
            "generated_at_utc": now.isoformat(),
            "decision_session": decision_session.isoformat() if isinstance(decision_session, date) else decision_session,
            "message": message,
            "details": dict(details or {}),
        }
        timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
        history_path = self.root / "runs" / "history" / f"{timestamp}-{run_slot}.json"
        _atomic_write(history_path, canonical_json_bytes(payload))

        current_latest = self.read_latest_run()
        keep_latest = (
            preserve_validated_latest
            and current_latest is not None
            and current_latest.get("status") in {"VALIDATED", "NO_NEW_SESSION"}
            and current_latest.get("decision_session") == payload.get("decision_session")
        )
        if not keep_latest:
            _atomic_write(self.latest_run_path, canonical_json_bytes(payload))
        return payload
