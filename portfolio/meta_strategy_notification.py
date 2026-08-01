from __future__ import annotations

from datetime import date
import math
from typing import Mapping


FAILURE_STATUSES = {
    "CONFIG_FAILED",
    "SOURCE_FAILED",
    "VALIDATION_FAILED",
    "UNEXPECTED_FAILED",
}


def should_publish_notification(
    *,
    run_slot: str,
    update_exit_code: int,
    latest_run: Mapping[str, object],
) -> bool:
    if run_slot == "manual":
        return True
    if run_slot.startswith("primary-"):
        return update_exit_code == 0
    if run_slot.startswith("retry-"):
        return latest_run.get("run_slot") == run_slot
    return False


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, *, fallback: str = "-") -> str:
    if value is None:
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def _number(value: object, *, digits: int = 2, suffix: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(number):
        return "-"
    return f"{number:,.{digits}f}{suffix}"


def _status_label(status: str) -> str:
    return {
        "VALIDATED": "검증 완료",
        "NO_NEW_SESSION": "신규 거래일 없음",
        "CONFIG_FAILED": "설정 오류",
        "SOURCE_FAILED": "원자료 조회 실패",
        "VALIDATION_FAILED": "검증 실패",
        "UNEXPECTED_FAILED": "예상하지 못한 오류",
    }.get(status, status or "상태 미확인")


def _notification_marker(
    *,
    notification_date: date | str,
    latest_run: Mapping[str, object],
    signal: Mapping[str, object] | None,
) -> str:
    signal_payload = signal or {}
    parts = (
        _text(notification_date),
        _text(latest_run.get("status"), fallback="UNKNOWN"),
        _text(latest_run.get("decision_session"), fallback="none"),
        _text(signal_payload.get("signal_hash"), fallback="no-signal"),
    )
    return f"<!-- meta-strategy-notification:{':'.join(parts)} -->"


def render_meta_strategy_notification(
    *,
    latest_run: Mapping[str, object],
    signal: Mapping[str, object] | None,
    notification_date: date | str,
    recipient: str,
    repository: str,
    run_url: str,
) -> str:
    status = _text(latest_run.get("status"), fallback="UNKNOWN")
    signal_payload = signal or {}
    liquidity = _mapping(signal_payload.get("liquidity"))
    qqq = _mapping(signal_payload.get("qqq"))
    entry = _mapping(signal_payload.get("entry_advice"))
    rsi = _mapping(signal_payload.get("rsi_reference"))
    marker = _notification_marker(
        notification_date=notification_date,
        latest_run=latest_run,
        signal=signal,
    )

    if status == "VALIDATED":
        notice = "새 공식 판정이 검증 완료되었습니다."
    elif status == "NO_NEW_SESSION":
        notice = "신규 완료 거래일이 없어 직전 검증 완료 판정을 유지합니다."
    elif status in FAILURE_STATUSES:
        notice = "오늘 공식 갱신에 실패하여 직전 검증 완료 판정을 표시합니다."
    else:
        notice = "실행 상태를 확인하고 마지막 검증 완료 판정을 표시합니다."

    signal_url = f"https://github.com/{repository}/blob/meta-strategy-data/signals/latest_validated.md"
    run_status_url = f"https://github.com/{repository}/blob/meta-strategy-data/runs/latest_run.json"
    lines = [
        marker,
        f"@{recipient}",
        "",
        f"## 공식 메타전략 판정 · {_text(notification_date)} KST",
        "",
        f"> {notice}",
        "",
        f"- 실행 상태: **{_status_label(status)}** (`{status}`)",
        f"- 실행 메시지: {_text(latest_run.get('message'))}",
    ]

    if signal_payload:
        warning = rsi.get("warning") is True
        lines.extend(
            [
                f"- 판정 거래일: **{_text(signal_payload.get('decision_session'))}**",
                f"- 예정 실행일: {_text(signal_payload.get('planned_execution_session'))}",
                f"- 시장구간: **{_text(signal_payload.get('market_regime_label'))}**",
                f"- 활성화 전략: **{_text(signal_payload.get('active_strategy_label'))}**",
                f"- 최종 실행 목표자산: **{_text(signal_payload.get('overall_execution_target'))}**",
                f"- Router 목표자산: {_text(signal_payload.get('router_target'))}",
                f"- 적용 P: {_number(liquidity.get('percentile'), digits=4)}",
                f"- QQQ 종가 / SMA50: {_number(qqq.get('close'))} / {_number(qqq.get('sma50'))}",
                f"- 신규 자금 집행 방식: {_text(entry.get('mode'))}",
                (
                    f"- RSI14 참고: {_number(rsi.get('latest_rsi14'))} · "
                    f"{'경고' if warning else '경고 없음'} · {_text(rsi.get('trend_label'))}"
                ),
            ]
        )
    else:
        lines.append("- 직전 검증 완료 판정: 아직 생성되지 않음")

    lines.extend(
        [
            "",
            f"[상세 판정 보기]({signal_url}) · [실행 상태]({run_status_url}) · [Actions 실행]({run_url})",
            "",
            "> 규칙 기반 상태 알림이며 자동 매매나 투자 조언이 아닙니다.",
            "",
        ]
    )
    return "\n".join(lines)
