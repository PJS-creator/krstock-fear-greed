from datetime import datetime, timezone

from portfolio.meta_strategy_calendar import XNYSCalendar


def test_xnys_calendar_uses_completed_session_and_sixty_session_offset():
    calendar = XNYSCalendar()

    decision = calendar.latest_completed_session(
        datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)
    )
    execution = calendar.next_session_after(decision)
    deferred = calendar.session_offset(execution, 60)

    assert decision.isoformat() == "2026-07-24"
    assert execution.isoformat() == "2026-07-27"
    assert deferred.isoformat() == "2026-10-20"
