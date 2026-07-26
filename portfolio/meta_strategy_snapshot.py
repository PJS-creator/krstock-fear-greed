from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from portfolio.meta_strategy import MetaStrategyResult


DEFAULT_OFFICIAL_SIGNAL_URL = (
    "https://raw.githubusercontent.com/PJS-creator/krstock-fear-greed/"
    "meta-strategy-data/signals/latest_validated.json"
)


class OfficialSnapshotError(RuntimeError):
    pass


def parse_official_snapshot(payload: bytes | str | Mapping[str, object]) -> dict[str, object]:
    if isinstance(payload, Mapping):
        decoded: Any = dict(payload)
    else:
        try:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            decoded = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OfficialSnapshotError("공식 메타전략 JSON을 읽을 수 없습니다.") from exc
    if not isinstance(decoded, dict):
        raise OfficialSnapshotError("공식 메타전략 산출물이 객체가 아닙니다.")
    if decoded.get("status") != "VALIDATED":
        raise OfficialSnapshotError("공식 메타전략 산출물이 검증 완료 상태가 아닙니다.")
    legacy = decoded.get("legacy_view")
    if not isinstance(legacy, Mapping):
        raise OfficialSnapshotError("공식 메타전략 산출물에 앱 호환 뷰가 없습니다.")
    if not str(legacy.get("applied_ticker") or "").strip():
        raise OfficialSnapshotError("공식 메타전략 산출물에 최종 목표자산이 없습니다.")
    return decoded


def fetch_official_snapshot(
    *,
    url: str = DEFAULT_OFFICIAL_SIGNAL_URL,
    timeout_seconds: float = 3.0,
    opener: Callable[..., object] = urlopen,
) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "User-Agent": "krstock-fear-greed/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except Exception as exc:
        raise OfficialSnapshotError(f"공식 메타전략 산출물 조회 실패: {exc}") from exc
    return parse_official_snapshot(payload)


def official_snapshot_to_app_view(
    snapshot: Mapping[str, object],
    *,
    preview: MetaStrategyResult | Mapping[str, object] | None = None,
) -> dict[str, object]:
    parsed = parse_official_snapshot(snapshot)
    legacy = dict(parsed["legacy_view"])  # type: ignore[arg-type]
    legacy["data_mode"] = "official"
    legacy["official_status"] = parsed.get("status")
    legacy["signal_hash"] = parsed.get("signal_hash")
    legacy["pipeline_version"] = parsed.get("pipeline_version")
    legacy["ruleset_version"] = parsed.get("ruleset_version")
    legacy["router_target"] = parsed.get("router_target")
    legacy["overall_execution_target"] = parsed.get("overall_execution_target")
    legacy["entry_advice"] = parsed.get("entry_advice")
    legacy["rsi_reference"] = parsed.get("rsi_reference")
    legacy["official_snapshot"] = parsed
    if preview is not None:
        if isinstance(preview, Mapping):
            preview_view = dict(preview)
        elif is_dataclass(preview):
            preview_view = asdict(preview)
        else:
            preview_view = {}
        legacy["preview"] = preview_view
    return legacy
