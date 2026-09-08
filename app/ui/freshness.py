"""Session-local refresh bookkeeping; failed attempts also respect the retry interval."""
import math
import time


def refresh_due(state, key: str, *, ttl_seconds: float, now: float | None = None) -> bool:
    current = time.time() if now is None else now
    try:
        previous = float(state[key])
    except (KeyError, TypeError, ValueError):
        return True
    return not math.isfinite(previous) or current < previous or current - previous >= ttl_seconds


def mark_checked(state, key: str, *, now: float | None = None) -> None:
    state[key] = time.time() if now is None else now
