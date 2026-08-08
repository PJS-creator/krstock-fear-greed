from __future__ import annotations

import json
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from portfolio.meta_strategy_alternative import STRATEGY_ID


DEFAULT_ALTERNATIVE_SIGNAL_URL = (
    "https://raw.githubusercontent.com/PJS-creator/krstock-fear-greed/"
    "alternative-strategy-data/signals/latest_validated.json"
)


class AlternativeSnapshotError(RuntimeError):
    pass


def parse_alternative_snapshot(payload: bytes | str | Mapping[str, object]) -> dict[str, object]:
    if isinstance(payload, Mapping):
        decoded: Any = dict(payload)
    else:
        try:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
            decoded = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AlternativeSnapshotError("쉐도우 전략 JSON을 읽을 수 없습니다.") from exc
    if not isinstance(decoded, dict):
        raise AlternativeSnapshotError("쉐도우 전략 산출물이 객체가 아닙니다.")
    if decoded.get("status") != "VALIDATED":
        raise AlternativeSnapshotError("쉐도우 전략 산출물이 검증 완료 상태가 아닙니다.")
    if decoded.get("strategy_kind") != "ALTERNATIVE_SHADOW":
        raise AlternativeSnapshotError("쉐도우 전략 산출물 종류가 올바르지 않습니다.")
    if decoded.get("strategy_id") != STRATEGY_ID:
        raise AlternativeSnapshotError("아직 v3.0 쉐도우 전략 산출물이 준비되지 않았습니다.")
    if not isinstance(decoded.get("a1_overlay"), Mapping):
        raise AlternativeSnapshotError("v3.0 산출물에 A1 상태가 없습니다.")
    if not str(decoded.get("resolved_execution_target") or "").strip():
        raise AlternativeSnapshotError("v3.0 산출물에 최종 shadow target이 없습니다.")
    return decoded


def fetch_alternative_snapshot(
    *,
    url: str = DEFAULT_ALTERNATIVE_SIGNAL_URL,
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
        raise AlternativeSnapshotError(f"쉐도우 전략 산출물 조회 실패: {exc}") from exc
    return parse_alternative_snapshot(payload)
