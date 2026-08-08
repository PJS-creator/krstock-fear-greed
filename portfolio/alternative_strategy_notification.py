from __future__ import annotations

from datetime import date
import math
from typing import Mapping

from portfolio.meta_strategy_notification import FAILURE_STATUSES


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
    return f"<!-- alternative-strategy-notification:{':'.join(parts)} -->"


def render_alternative_strategy_notification(
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
    n1 = _mapping(signal_payload.get("n1_overlay"))
    a1 = _mapping(signal_payload.get("a1_overlay"))
    entry = _mapping(signal_payload.get("entry_filter_v4"))
    rsi = _mapping(signal_payload.get("rsi_reference"))
    marker = _notification_marker(
        notification_date=notification_date,
        latest_run=latest_run,
        signal=signal,
    )

    if status == "VALIDATED":
        notice = "새 대안 N1/A1/V4 shadow v3.0 판정이 검증 완료되었습니다."
    elif status == "NO_NEW_SESSION":
        notice = "신규 완료 거래일이 없어 직전 대안 판정을 유지합니다."
    elif status in FAILURE_STATUSES:
        notice = "오늘 대안 판정 갱신에 실패하여 직전 검증 완료 결과를 표시합니다."
    else:
        notice = "실행 상태를 확인하고 마지막 검증 완료 대안 판정을 표시합니다."

    signal_url = (
        f"https://github.com/{repository}/blob/alternative-strategy-data/signals/latest_validated.md"
    )
    run_status_url = (
        f"https://github.com/{repository}/blob/alternative-strategy-data/runs/latest_run.json"
    )
    lines = [
        marker,
        f"@{recipient}",
        "",
        f"## 대안 shadow v3.0 전략 판정 · {_text(notification_date)} KST",
        "",
        f"> {notice}",
        "",
        f"- 실행 상태: **{_status_label(status)}** (`{status}`)",
        f"- 실행 메시지: {_text(latest_run.get('message'))}",
    ]

    if signal_payload:
        lines.extend(
            [
                f"- 판정 거래일: **{_text(signal_payload.get('decision_session'))}**",
                f"- 예정 실행일: {_text(signal_payload.get('planned_execution_session'))}",
                f"- 시장구간: **{_text(signal_payload.get('market_regime_label'))}**",
                f"- N1 전 기준 목표: **{_text(signal_payload.get('base_execution_target'))}**",
                f"- N1 오버레이: **{'적용' if n1.get('applied') is True else '미적용'}**",
                f"- N1 후 목표: **{_text(signal_payload.get('post_n1_execution_target'))}**",
                (
                    f"- A1 래치: **{_text(a1.get('event'))}** · "
                    f"{_text(a1.get('previous_state_subtype'))} → "
                    f"{_text(a1.get('current_state_subtype'))}"
                ),
                f"- A1 활성: **{'예' if a1.get('active') is True else '아니오'}**",
                f"- v3.0 최종 shadow target: **{_text(signal_payload.get('resolved_execution_target'))}**",
                f"- 신규진입 V4: **{'발동' if entry.get('triggered') is True else '미발동'}** · {_text(entry.get('mode'))}",
                (
                    f"- 오늘 시작 가정: {_number(entry.get('immediate_weight_pct'), digits=0, suffix='%')} "
                    f"→ {_text(entry.get('immediate_target'))} · "
                    f"현금 {_number(entry.get('cash_weight_pct'), digits=0, suffix='%')}"
                ),
                f"- 유예 합류 예정일: {_text(entry.get('deferred_due_session'))}",
                f"- 적용 P: {_number(liquidity.get('percentile'), digits=4)}",
                f"- QQQ 종가 / SMA50: {_number(qqq.get('close'))} / {_number(qqq.get('sma50'))}",
                f"- SMA50 상방이격률: {_number(entry.get('qqq_sma50_upper_distance_pct'), suffix='%')}",
                (
                    f"- RSI14 참고: {_number(rsi.get('latest_rsi14'))} · "
                    f"{'경고' if rsi.get('warning') is True else '경고 없음'} · "
                    f"{_text(rsi.get('trend_label'))}"
                ),
            ]
        )
    else:
        lines.append("- 직전 검증 완료 대안 판정: 아직 생성되지 않음")

    lines.extend(
        [
            "",
            f"[상세 대안 판정]({signal_url}) · [실행 상태]({run_status_url}) · [Actions 실행]({run_url})",
            "",
            "> 공식 메타전략 판정은 변경하지 않습니다. v3.0은 별도 shadow 검증이며 자동 매매나 투자 조언이 아닙니다.",
            "",
        ]
    )
    return "\n".join(lines)
