from datetime import datetime, timezone

from app.ui.formatters import (
    compact_krw,
    format_number,
    format_price,
    format_kst,
    format_relative_time,
    full_krw,
    instrument_label,
    percentage,
    signed_krw,
    signed_percentage,
)


def test_compact_and_full_krw_formatting():
    assert compact_krw(84_190_000) == "8,419만 원"
    assert compact_krw(100_000_000) == "1억 원"
    assert compact_krw(120_000_000) == "1억 2,000만 원"
    assert compact_krw(199_145_337) == "1억 9,915만 원"
    assert compact_krw(0) == "0원"
    assert full_krw(84_190_000) == "₩84,190,000"


def test_signed_amount_and_percentage_formatting():
    assert signed_krw(320_000) == "+32만 원"
    assert signed_krw(-4_100_000) == "-410만 원"
    assert signed_krw(120_000_000) == "+1억 2,000만 원"
    assert signed_krw(0) == "0원"
    assert percentage(0.1234) == "12.3%"
    assert signed_percentage(0.0123) == "+1.2%"
    assert signed_percentage(-0.0456) == "-4.6%"
    assert signed_percentage(0) == "0.0%"


def test_number_price_and_instrument_label_formatting():
    assert format_number(1_234_567.89, digits=2) == "1,234,567.89"
    assert format_number(1_000.5000, digits=4, trim=True) == "1,000.5"
    assert format_price(72_000, "KRW") == "₩72,000"
    assert format_price(1234.5, "USD") == "$1,234.50"
    assert instrument_label({"market": "KR", "ticker": "005930", "display_name": "삼성전자"}) == "삼성전자"
    assert instrument_label({"market": "KR", "ticker": "005930", "display_name": "삼성전자"}, include_ticker=True) == "삼성전자 · 005930"
    assert instrument_label({"market": "US", "ticker": "MU", "display_name": "Micron"}) == "MU · Micron"


def test_kst_and_relative_time_formatting():
    captured = "2026-06-23T03:58:00+00:00"
    assert format_kst(captured) == "2026-06-23 12:58 KST"
    assert format_kst(captured, compact=True) == "06-23 12:58 KST"
    assert format_kst(None, compact=True) == "미조회"
    now = datetime(2026, 6, 23, 4, 1, tzinfo=timezone.utc)
    assert format_relative_time(captured, now=now) == "3분 전"
