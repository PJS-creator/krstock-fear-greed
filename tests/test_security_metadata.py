from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ui.holdings import _preserve_holding_metadata
from portfolio.holdings import normalize_holding_rows
from portfolio.security_metadata import (
    SecurityMetadata,
    SecurityMetadataError,
    TTLSecurityMetadataCache,
    YFinanceSecurityMetadataProvider,
    classify_sector,
    enrich_holding_metadata,
)
from portfolio.storage import deserialize_portfolio_payload_v2, serialize_portfolio_payload


UTC = timezone.utc
NOW = datetime(2026, 7, 11, 1, 0, tzinfo=UTC)


class FakeMetadataProvider:
    provider_name = "fake-metadata"

    def __init__(self, *, sector: str = "정보기술", fail: bool = False) -> None:
        self.sector = sector
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def get_metadata(self, symbol: str, *, market: str) -> SecurityMetadata:
        self.calls.append((symbol, market))
        if self.fail:
            raise SecurityMetadataError("metadata unavailable")
        return SecurityMetadata.now(
            symbol=symbol,
            market=market,
            sector=self.sector,
            sector_key="technology",
            industry="Software - Application",
            industry_key="software-application",
            quote_type="EQUITY",
            provider=self.provider_name,
            now=NOW,
        )


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"sector_key": "healthcare", "industry_key": "biotechnology"}, "바이오·헬스케어"),
        ({"sector_key": "technology", "industry_key": "semiconductors"}, "반도체·전자"),
        ({"sector_key": "basic-materials", "industry_key": "gold"}, "귀금속·광업"),
        ({"sector_key": "technology", "industry_key": "software-application"}, "정보기술"),
        ({"quote_type": "ETF"}, "ETF·펀드"),
        ({"quote_type": "INDEX"}, "지수·파생"),
        ({"quote_type": "CRYPTOCURRENCY"}, "가상자산"),
    ],
)
def test_classify_sector_uses_provider_metadata(metadata, expected):
    assert classify_sector(**metadata) == expected


def test_yfinance_provider_reads_us_metadata():
    provider = YFinanceSecurityMetadataProvider(
        info_loader=lambda symbol: {
            "sectorKey": "healthcare",
            "industryKey": "biotechnology",
            "sector": "Healthcare",
            "industry": "Biotechnology",
            "quoteType": "EQUITY",
        }
    )

    metadata = provider.get_metadata("QURE", market="US")

    assert metadata.symbol == "QURE"
    assert metadata.market == "US"
    assert metadata.sector == "바이오·헬스케어"
    assert metadata.industry_key == "biotechnology"


def test_yfinance_provider_tries_kosdaq_after_kospi_candidate_fails():
    calls: list[str] = []

    def load_info(symbol: str):
        calls.append(symbol)
        if symbol.endswith(".KS"):
            raise RuntimeError("not listed on KOSPI")
        return {
            "sectorKey": "technology",
            "industryKey": "electronic-components",
            "quoteType": "EQUITY",
        }

    metadata = YFinanceSecurityMetadataProvider(info_loader=load_info).get_metadata("123456", market="KR")

    assert calls == ["123456.KS", "123456.KQ"]
    assert metadata.sector == "반도체·전자"


def test_builtin_sector_enrichment_does_not_call_provider():
    provider = FakeMetadataProvider()

    rows = enrich_holding_metadata(
        [{"market": "KR", "ticker": "005930", "display_name": "삼성전자", "quantity": 1}],
        provider,
        cache=TTLSecurityMetadataCache(),
        now=NOW,
    )

    assert provider.calls == []
    assert rows[0]["sector"] == "반도체·전자"
    assert rows[0]["metadata_source"] == "built_in"


def test_unknown_holding_is_enriched_and_memory_cache_avoids_duplicate_lookup():
    provider = FakeMetadataProvider()
    cache = TTLSecurityMetadataCache()
    holding = {"market": "US", "ticker": "NEW", "quantity": 1}

    first = enrich_holding_metadata([holding], provider, cache=cache, now=NOW)
    second = enrich_holding_metadata([holding], provider, cache=cache, now=NOW)

    assert provider.calls == [("NEW", "US")]
    assert first[0]["sector"] == "정보기술"
    assert second[0]["industry_key"] == "software-application"
    assert second[0]["metadata_source"] == "fake-metadata"


def test_fresh_persisted_metadata_skips_provider_lookup():
    provider = FakeMetadataProvider()
    row = {
        "market": "US",
        "ticker": "NEW",
        "quantity": 1,
        "sector": "정보기술",
        "metadata_source": "yfinance",
        "metadata_fetched_at": (NOW - timedelta(days=5)).isoformat(),
    }

    result = enrich_holding_metadata([row], provider, cache=TTLSecurityMetadataCache(), now=NOW)

    assert provider.calls == []
    assert result == [row]


def test_failed_persisted_lookup_retries_after_24_hours():
    provider = FakeMetadataProvider(fail=True)
    first = enrich_holding_metadata(
        [{"market": "US", "ticker": "UNKNOWN", "quantity": 1}],
        provider,
        cache=TTLSecurityMetadataCache(),
        now=NOW,
    )
    before_retry = enrich_holding_metadata(
        first,
        provider,
        cache=TTLSecurityMetadataCache(),
        now=NOW + timedelta(hours=23),
    )
    after_retry = enrich_holding_metadata(
        before_retry,
        provider,
        cache=TTLSecurityMetadataCache(),
        now=NOW + timedelta(hours=25),
    )

    assert provider.calls == [("UNKNOWN", "US"), ("UNKNOWN", "US")]
    assert after_retry[0]["metadata_error"] == "metadata unavailable"


def test_lookup_budget_limits_new_network_requests_per_run():
    provider = FakeMetadataProvider()
    rows = enrich_holding_metadata(
        [
            {"market": "US", "ticker": "ONE", "quantity": 1},
            {"market": "US", "ticker": "TWO", "quantity": 1},
            {"market": "US", "ticker": "THREE", "quantity": 1},
        ],
        provider,
        cache=TTLSecurityMetadataCache(),
        now=NOW,
        max_lookups=2,
    )

    assert provider.calls == [("ONE", "US"), ("TWO", "US")]
    assert rows[0]["sector"] == "정보기술"
    assert rows[1]["sector"] == "정보기술"
    assert rows[2].get("sector") is None


def test_holding_normalization_and_payload_round_trip_preserve_metadata():
    row = {
        "market": "US",
        "ticker": "NEW",
        "quantity": 1,
        "sector": "정보기술",
        "sector_key": "technology",
        "industry": "Software - Application",
        "industry_key": "software-application",
        "quote_type": "EQUITY",
        "metadata_source": "yfinance",
        "metadata_fetched_at": NOW.isoformat(),
    }

    normalized = normalize_holding_rows([row])[0]
    payload = serialize_portfolio_payload([normalized], usd_krw=1300, cash_krw=0)
    restored = deserialize_portfolio_payload_v2(payload)["holdings"][0]

    assert restored["sector"] == "정보기술"
    assert restored["industry_key"] == "software-application"
    assert restored["metadata_source"] == "yfinance"
    assert restored["metadata_fetched_at"] == NOW.isoformat()


def test_advanced_editor_preserves_hidden_metadata_for_unchanged_ticker():
    existing = [
        {
            "market": "US",
            "ticker": "NEW",
            "quantity": 1,
            "sector": "정보기술",
            "metadata_source": "yfinance",
            "metadata_fetched_at": NOW.isoformat(),
        }
    ]

    merged = _preserve_holding_metadata(
        [{"market": "US", "ticker": "NEW", "quantity": 2}],
        existing,
    )

    assert merged[0]["quantity"] == 2
    assert merged[0]["sector"] == "정보기술"
    assert merged[0]["metadata_source"] == "yfinance"
