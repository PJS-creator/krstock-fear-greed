"""Read publication health independently from the last validated strategy signal."""
from datetime import datetime, timedelta, timezone
import json
from typing import Mapping
from urllib.request import Request, urlopen


def _timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (ValueError, TypeError):
        return None


def publication_note(signal: Mapping, run: Mapping, *, now=None) -> str:
    current = now or datetime.now(timezone.utc)
    checked = _timestamp(run.get("generated_at_utc"))
    if checked is None:
        return "최신 실행 시각 확인 불가 · 이전 검증값 표시"
    if current - checked > timedelta(hours=36):
        return "최근 36시간 내 실행 확인 불가 · 이전 검증값 표시"
    status = str(run.get("status") or "UNKNOWN")
    if status not in {"VALIDATED", "NO_NEW_SESSION"}:
        return f"최근 실행 {status} · 이전 검증값 표시"
    if str(run.get("decision_session") or "") > str(signal.get("decision_session") or ""):
        return "새 판정 산출물 배포 대기 · 이전 검증값 표시"
    return ""


def with_publication_health(signal: Mapping, *, url: str, opener=urlopen, now=None) -> dict:
    result = dict(signal)
    suffix = "signals/latest_validated.json"
    if not url.endswith(suffix):
        result["freshness_note"] = "사용자 지정 URL · 최신 실행 상태 별도 확인 필요"
        return result
    run_url = url[:-len(suffix)] + "runs/latest_run.json"
    try:
        request = Request(run_url, headers={"Accept": "application/json", "User-Agent": "krstock-fear-greed/1.0"})
        with opener(request, timeout=3.0) as response:
            run = json.loads(response.read(1_000_001))
        if not isinstance(run, dict):
            raise ValueError("run must be an object")
        result["latest_run"] = run
        result["freshness_note"] = publication_note(signal, run, now=now)
    except Exception:
        result["freshness_note"] = "최신 실행 상태 조회 실패 · 이전 검증값 표시"
    return result
