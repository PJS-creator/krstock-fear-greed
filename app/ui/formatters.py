from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
APP_FONT_FAMILY = (
    '"Pretendard Variable", Pretendard, "Noto Sans KR", "Apple SD Gothic Neo", '
    '"Malgun Gothic", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
)


def _is_number(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


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
    if abs_value >= 10_000:
        return f"{sign}{abs_value / 10_000:,.0f}만"
    return f"{value:,.0f}"


def format_number(value: float | None, *, digits: int = 0, trim: bool = False) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    text = f"{float(value):,.{digits}f}"
    if trim and "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def compact_krw(value: float | None) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    numeric = float(value)
    if numeric == 0:
        return "0원"
    abs_value = abs(numeric)
    sign = "-" if numeric < 0 else ""
    if abs_value >= 100_000_000:
        total_man = int(round(abs_value / 10_000))
        eok, man = divmod(total_man, 10_000)
        if man:
            return f"{sign}{eok:,}억 {man:,}만 원"
        return f"{sign}{eok:,}억 원"
    return f"{compact_number(numeric)} 원"


def eok_man_krw(value: float | None) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    numeric = float(value)
    sign = "-" if numeric < 0 else ""
    total_man = int(round(abs(numeric) / 10_000))
    if total_man == 0:
        return "0원"
    eok, man = divmod(total_man, 10_000)
    if eok == 0:
        return f"{sign}{man:,}만 원"
    padded_man = f"{man:04d}"
    man_text = f"{padded_man[:-3]},{padded_man[-3:]}"
    return f"{sign}{eok:,}억 {man_text}만 원"


def full_krw(value: float | None) -> str:
    if value is None or not _is_number(value):
        return "미산정"
    return f"₩{float(value):,.0f}"


def format_price(value: float | None, currency: object = "") -> str:
    if value is None or not _is_number(value):
        return "미산정"
    currency_text = str(currency or "").upper()
    if currency_text == "KRW":
        return f"₩{float(value):,.0f}"
    if currency_text == "USD":
        return f"${float(value):,.2f}"
    return format_number(float(value), digits=2, trim=True)


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
        return percentage(0.0, digits=digits)
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


def instrument_label(row: object, *, include_ticker: bool = False) -> str:
    data = row if isinstance(row, dict) else {}
    ticker = str(data.get("ticker") or data.get("symbol") or "").strip()
    display_name = str(data.get("display_name") or data.get("name") or "").strip()
    market = str(data.get("market") or "").strip().upper()
    if not display_name or display_name == ticker:
        return ticker or display_name or "-"
    if include_ticker:
        if market == "KR":
            return f"{display_name} · {ticker}"
        return f"{ticker} · {display_name}"
    if market == "KR":
        return display_name
    return f"{ticker} · {display_name}"
