from __future__ import annotations

from datetime import datetime, timezone

from .models import Position, Quote

SAMPLE_USD_KRW = 1380.0
SAMPLE_CASH_KRW = 1_000_000.0


def sample_portfolio() -> tuple[list[Position], dict[tuple[str, str], Quote], float, float]:
    fetched_at = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)
    positions = [
        Position("KR", "005930", "삼성전자", 10, 72000, "KRW", 0.25, "Core"),
        Position("KR", "000660", "SK하이닉스", 3, 210000, "KRW", 0.20, "Core"),
        Position("US", "AAPL", "Apple", 4, 180, "USD", 0.25, "Global Core"),
        Position("US", "NVDA", "NVIDIA", 2, 900, "USD", 0.20, "Satellite"),
    ]
    quotes = {
        ("KR", "005930"): Quote("KR", "005930", 78000, 77000, "KRW", fetched_at=fetched_at),
        ("KR", "000660"): Quote("KR", "000660", 235000, 230000, "KRW", fetched_at=fetched_at),
        ("US", "AAPL"): Quote("US", "AAPL", 195, 192, "USD", fetched_at=fetched_at),
        ("US", "NVDA"): Quote("US", "NVDA", 980, 970, "USD", fetched_at=fetched_at),
    }
    return positions, quotes, SAMPLE_USD_KRW, SAMPLE_CASH_KRW
