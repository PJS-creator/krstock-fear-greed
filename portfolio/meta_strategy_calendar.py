from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


class TradingCalendarUnavailable(RuntimeError):
    pass


class XNYSCalendar:
    def __init__(self):
        try:
            import exchange_calendars as exchange_calendars
            import pandas as pd
        except ImportError as exc:
            raise TradingCalendarUnavailable(
                "메타전략 실행에는 exchange-calendars가 필요합니다."
            ) from exc
        self._pd = pd
        self._calendar = exchange_calendars.get_calendar("XNYS")

    def latest_completed_session(self, now: datetime | None = None) -> date:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        current_utc = current.astimezone(timezone.utc)
        end = self._pd.Timestamp(current_utc.date())
        start = end - self._pd.Timedelta("14D")
        sessions = self._calendar.sessions_in_range(start, end)
        completed: list[object] = []
        now_timestamp = self._pd.Timestamp(current_utc)
        for session in sessions:
            close = self._calendar.session_close(session)
            if close <= now_timestamp:
                completed.append(session)
        if not completed:
            raise TradingCalendarUnavailable("최근 완료된 XNYS 거래일을 찾을 수 없습니다.")
        return completed[-1].date()

    def next_session_after(self, value: date) -> date:
        timestamp = self._pd.Timestamp(value)
        if self._calendar.is_session(timestamp):
            return self._calendar.next_session(timestamp).date()
        return self._calendar.date_to_session(timestamp, direction="next").date()

    def session_offset(self, value: date, offset: int) -> date:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if offset == 0:
            return value
        timestamp = self._pd.Timestamp(value)
        if not self._calendar.is_session(timestamp):
            timestamp = self._calendar.date_to_session(timestamp, direction="next")
        return self._calendar.session_offset(timestamp, offset).date()

    def is_session(self, value: date) -> bool:
        timestamp = self._pd.Timestamp(value)
        return bool(self._calendar.is_session(timestamp))


def conservative_weekday_next_session(value: date) -> date:
    """Test-friendly fallback that does not claim holiday awareness."""

    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate
