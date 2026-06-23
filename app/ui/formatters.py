from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def compact_number(value: float | None, *, digits: int = 1) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    abs_value = abs(float(value))
    sign = "-" if value < 0 else ""
    if abs_value >= 100_000_000:
        text = f"{abs_value / 100_000_000:.{digits}f}".rstrip("0").rstrip(".")
        return f"{sign}{text}억"
    if abs_value >= 10_000:
        return f"{sign}{abs_value / 10_000:,.0f}만"
    return f"{value:,.0f}"


def compact_krw(value: float | None) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    if float(value) == 0:
        return "0원"
    return f"{compact_number(float(value))} 원"


def full_krw(value: float | None) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    return f"₩{float(value):,.0f}"


def signed_krw(value: float | None) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    if float(value) == 0:
        return "0원"
    sign = "+" if value > 0 else ""
    return f"{sign}{compact_krw(float(value))}"


def percentage(value: float | None, *, digits: int = 1) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    return f"{float(value) * 100:.{digits}f}%"


def signed_percentage(value: float | None, *, digits: int = 1) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    if float(value) == 0:
        return f"0.{''.join('0' for _ in range(digits - 1))}%" if digits > 0 else "0%"
    sign = "+" if value > 0 else ""
    return f"{sign}{percentage(float(value), digits=digits)}"


def format_kst(value: object, *, compact: bool = False) -> str:
    dt = _coerce_datetime(value)
    if dt is None:
        return "미조회"
    return dt.strftime("%m-%d %H:%M KST" if compact else "%Y-%m-%d %H:%M KST")


def format_relative_time(value: object, *, now: datetime | None = None) -> str:
    dt = _coerce_datetime(value)
    if dt is None:
        return "미조회"
    base = (now or datetime.now(timezone.utc)).astimezone(KST)
    seconds = int((base - dt).total_seconds())
    if seconds < 0:
        return "방금 후"
    if seconds < 60:
        return "방금 전"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    days = hours // 24
    if days < 30:
        return f"{days}일 전"
    months = days // 30
    return f"{months}개월 전"
