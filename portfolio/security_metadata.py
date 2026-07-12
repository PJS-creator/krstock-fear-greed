from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Protocol


YFINANCE_METADATA_PROVIDER_NAME = "yfinance"
DEFAULT_METADATA_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_METADATA_FAILURE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_METADATA_MAX_AGE_DAYS = 30
DEFAULT_METADATA_FAILURE_RETRY_HOURS = 24
DEFAULT_METADATA_MAX_LOOKUPS_PER_RUN = 2
DEFAULT_METADATA_REQUEST_TIMEOUT_SECONDS = 4.0

KNOWN_SECTOR_BY_TICKER = {
    "000660": "반도체·전자",
    "005930": "반도체·전자",
    "005935": "반도체·전자",
    "009540": "조선·산업재",
    "071050": "금융",
    "239890": "디스플레이 소재",
    "AYA": "귀금속·광업",
    "AVR": "바이오·헬스케어",
    "CCCC": "바이오·헬스케어",
    "CGEM": "바이오·헬스케어",
    "CMPS": "바이오·헬스케어",
    "CTMX": "바이오·헬스케어",
    "EXK": "귀금속·광업",
    "GHRS": "바이오·헬스케어",
    "MAKO": "귀금속·광업",
    "PSNL": "바이오·헬스케어",
    "QURE": "바이오·헬스케어",
    "VOR": "바이오·헬스케어",
}

KNOWN_SECTOR_BY_NAME = {
    "HD한국조선해양": "조선·산업재",
    "SK하이닉스": "반도체·전자",
    "삼성전자": "반도체·전자",
    "삼성전자우": "반도체·전자",
    "삼성전자우선주": "반도체·전자",
    "피엔에이치테크": "디스플레이 소재",
    "한국금융지주": "금융",
}

_BROAD_SECTOR_LABELS = {
    "basic-materials": "소재",
    "communication-services": "커뮤니케이션",
    "consumer-cyclical": "경기소비재",
    "consumer-defensive": "필수소비재",
    "energy": "에너지",
    "financial-services": "금융",
    "healthcare": "바이오·헬스케어",
    "industrials": "산업재",
    "real-estate": "부동산",
    "technology": "정보기술",
    "utilities": "유틸리티",
}

_HEALTHCARE_INDUSTRY_TERMS = (
    "biotechnology",
    "diagnostics",
    "drug-manufacturer",
    "health-information",
    "healthcare-plan",
    "medical-care",
    "medical-device",
    "medical-distribution",
    "pharmaceutical",
)
_ELECTRONICS_INDUSTRY_TERMS = (
    "consumer-electronics",
    "electronic-components",
    "electronics-computer-distribution",
    "semiconductor",
)
_PRECIOUS_METALS_INDUSTRY_TERMS = ("gold", "silver", "precious-metal")
_SHIPBUILDING_INDUSTRY_TERMS = ("marine-shipping", "shipbuilding")


class SecurityMetadataError(RuntimeError):
    """Raised when a security metadata provider cannot resolve a symbol."""


@dataclass(frozen=True)
class SecurityMetadata:
    symbol: str
    market: str
    sector: str
    sector_key: str | None
    industry: str | None
    industry_key: str | None
    quote_type: str | None
    provider: str
    fetched_at: datetime

    @classmethod
    def now(
        cls,
        *,
        symbol: str,
        market: str,
        sector: str,
        sector_key: str | None,
        industry: str | None,
        industry_key: str | None,
        quote_type: str | None,
        provider: str,
        now: datetime | None = None,
    ) -> "SecurityMetadata":
        fetched_at = now or datetime.now(timezone.utc)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        return cls(
            symbol=str(symbol or "").strip().upper(),
            market=str(market or "").strip().upper(),
            sector=sector,
            sector_key=_clean_text(sector_key) or None,
            industry=_clean_text(industry) or None,
            industry_key=_clean_text(industry_key) or None,
            quote_type=_clean_text(quote_type).upper() or None,
            provider=provider,
            fetched_at=fetched_at.astimezone(timezone.utc),
        )


class SecurityMetadataProvider(Protocol):
    provider_name: str

    def get_metadata(self, symbol: str, *, market: str) -> SecurityMetadata:
        """Return sector and industry metadata or raise SecurityMetadataError."""


def _clean_text(value: object | None) -> str:
    return str(value or "").strip()


def _metadata_key(value: object | None) -> str:
    text = _clean_text(value).lower().replace("_", "-").replace(" ", "-")
    return re.sub(r"-+", "-", text).strip("-")


def classify_sector(
    *,
    sector_key: object | None = None,
    industry_key: object | None = None,
    sector_name: object | None = None,
    industry_name: object | None = None,
    quote_type: object | None = None,
) -> str:
    quote = _metadata_key(quote_type)
    if quote in {"etf", "mutualfund", "money-market"}:
        return "ETF·펀드"
    if quote in {"index", "future", "option"}:
        return "지수·파생"
    if quote in {"cryptocurrency", "crypto"}:
        return "가상자산"

    industry = _metadata_key(industry_key) or _metadata_key(industry_name)
    sector = _metadata_key(sector_key) or _metadata_key(sector_name)
    if any(term in industry for term in _HEALTHCARE_INDUSTRY_TERMS):
        return "바이오·헬스케어"
    if any(term in industry for term in _ELECTRONICS_INDUSTRY_TERMS):
        return "반도체·전자"
    if any(term in industry for term in _PRECIOUS_METALS_INDUSTRY_TERMS):
        return "귀금속·광업"
    if any(term in industry for term in _SHIPBUILDING_INDUSTRY_TERMS):
        return "조선·산업재"
    return _BROAD_SECTOR_LABELS.get(sector, "기타")


def known_sector_for_holding(holding: Mapping[str, Any]) -> str | None:
    ticker = _clean_text(holding.get("ticker") or holding.get("symbol")).upper()
    if ticker in KNOWN_SECTOR_BY_TICKER:
        return KNOWN_SECTOR_BY_TICKER[ticker]
    display_name = _clean_text(holding.get("display_name") or holding.get("name"))
    return KNOWN_SECTOR_BY_NAME.get(display_name)


def resolve_holding_sector(holding: Mapping[str, Any]) -> str:
    explicit = _clean_text(holding.get("sector") or holding.get("sector_name"))
    if explicit and explicit != "기타":
        return explicit
    return known_sector_for_holding(holding) or explicit or "기타"


def _candidate_symbols(symbol: object, market: object) -> tuple[str, ...]:
    normalized_symbol = _clean_text(symbol).upper()
    normalized_market = _clean_text(market).upper()
    if not normalized_symbol:
        raise SecurityMetadataError("종목코드가 비어 있습니다.")
    if normalized_market in {"KR", "KRX", "KOSPI", "KOSDAQ"}:
        for suffix in (".KS", ".KQ"):
            if normalized_symbol.endswith(suffix):
                normalized_symbol = normalized_symbol[: -len(suffix)]
                break
        if not re.fullmatch(r"\d{6}", normalized_symbol):
            raise SecurityMetadataError("국내 종목코드는 6자리 숫자여야 합니다.")
        return (f"{normalized_symbol}.KS", f"{normalized_symbol}.KQ")
    if normalized_market in {"US", "USA", "NASDAQ", "NYSE", "AMEX"}:
        return (normalized_symbol,)
    raise SecurityMetadataError(f"지원하지 않는 시장입니다: {normalized_market or '-'}")


class YFinanceSecurityMetadataProvider:
    provider_name = YFINANCE_METADATA_PROVIDER_NAME

    def __init__(
        self,
        *,
        info_loader: Callable[[str], Mapping[str, Any]] | None = None,
        timeout_seconds: float = DEFAULT_METADATA_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("metadata request timeout must be positive")
        self._info_loader = info_loader
        self._timeout_seconds = float(timeout_seconds)

    def _load_info_sync(self, symbol: str) -> Mapping[str, Any]:
        if self._info_loader is not None:
            payload = self._info_loader(symbol)
        else:
            try:
                import yfinance as yf
            except ImportError as exc:
                raise SecurityMetadataError("yfinance 패키지가 설치되어 있지 않습니다.") from exc
            payload = yf.Ticker(symbol).get_info()
        if not isinstance(payload, Mapping):
            raise SecurityMetadataError(f"yfinance 메타데이터 응답 형식이 올바르지 않습니다: {symbol}")
        return payload

    def _load_info(self, symbol: str) -> Mapping[str, Any]:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="security-metadata")
        future = executor.submit(self._load_info_sync, symbol)
        try:
            return future.result(timeout=self._timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise SecurityMetadataError(f"yfinance 메타데이터 조회 시간 초과: {symbol}") from exc
        except SecurityMetadataError:
            raise
        except Exception as exc:
            raise SecurityMetadataError(f"yfinance 메타데이터 조회 실패: {symbol}") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def get_metadata(self, symbol: str, *, market: str) -> SecurityMetadata:
        candidates = _candidate_symbols(symbol, market)
        errors: list[str] = []
        fallback: SecurityMetadata | None = None
        for candidate in candidates:
            try:
                info = self._load_info(candidate)
            except SecurityMetadataError as exc:
                errors.append(str(exc))
                continue
            sector_key = _clean_text(info.get("sectorKey")) or None
            industry_key = _clean_text(info.get("industryKey")) or None
            sector_name = _clean_text(info.get("sector")) or None
            industry_name = _clean_text(info.get("industry")) or None
            quote_type = _clean_text(info.get("quoteType")) or None
            metadata = SecurityMetadata.now(
                symbol=symbol,
                market=market,
                sector=classify_sector(
                    sector_key=sector_key,
                    industry_key=industry_key,
                    sector_name=sector_name,
                    industry_name=industry_name,
                    quote_type=quote_type,
                ),
                sector_key=sector_key,
                industry=industry_name,
                industry_key=industry_key,
                quote_type=quote_type,
                provider=self.provider_name,
            )
            fallback = metadata
            if metadata.sector != "기타" or sector_key or industry_key:
                return metadata
        if fallback is not None:
            return fallback
        detail = "; ".join(errors) if errors else "유효한 섹터 정보가 없습니다."
        raise SecurityMetadataError(detail)


@dataclass(frozen=True)
class _MetadataCacheEntry:
    metadata: SecurityMetadata
    stored_at: float


@dataclass(frozen=True)
class _MetadataFailureEntry:
    message: str
    stored_at: float


class TTLSecurityMetadataCache:
    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_METADATA_CACHE_TTL_SECONDS,
        failure_ttl_seconds: int = DEFAULT_METADATA_FAILURE_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0 or failure_ttl_seconds <= 0:
            raise ValueError("metadata cache TTL values must be positive")
        self.ttl_seconds = ttl_seconds
        self.failure_ttl_seconds = failure_ttl_seconds
        self._entries: dict[tuple[str, str], _MetadataCacheEntry] = {}
        self._failures: dict[tuple[str, str], _MetadataFailureEntry] = {}

    @staticmethod
    def _key(symbol: object, market: object) -> tuple[str, str]:
        return (_clean_text(market).upper(), _clean_text(symbol).upper())

    def get(self, symbol: object, market: object) -> SecurityMetadata | None:
        key = self._key(symbol, market)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if monotonic() - entry.stored_at > self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry.metadata

    def get_failure(self, symbol: object, market: object) -> str | None:
        key = self._key(symbol, market)
        entry = self._failures.get(key)
        if entry is None:
            return None
        if monotonic() - entry.stored_at > self.failure_ttl_seconds:
            self._failures.pop(key, None)
            return None
        return entry.message

    def set(self, metadata: SecurityMetadata) -> None:
        key = self._key(metadata.symbol, metadata.market)
        self._entries[key] = _MetadataCacheEntry(metadata=metadata, stored_at=monotonic())
        self._failures.pop(key, None)

    def set_failure(self, symbol: object, market: object, message: object) -> None:
        key = self._key(symbol, market)
        self._failures[key] = _MetadataFailureEntry(message=_clean_text(message), stored_at=monotonic())


DEFAULT_SECURITY_METADATA_CACHE = TTLSecurityMetadataCache()


def _as_utc_datetime(value: object | None) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _metadata_refresh_due(
    row: Mapping[str, Any],
    *,
    now: datetime,
    max_age_days: int,
    failure_retry_hours: int,
) -> bool:
    sector = _clean_text(row.get("sector"))
    source = _clean_text(row.get("metadata_source")).lower()
    if sector and sector != "기타" and source in {"built_in", "manual"}:
        return False
    fetched_at = _as_utc_datetime(row.get("metadata_fetched_at"))
    if fetched_at is None:
        return not bool(sector and sector != "기타")
    if _clean_text(row.get("metadata_error")):
        return now - fetched_at >= timedelta(hours=failure_retry_hours)
    return now - fetched_at >= timedelta(days=max_age_days)


def _apply_metadata(row: Mapping[str, Any], metadata: SecurityMetadata) -> dict[str, object]:
    updated = dict(row)
    updated.update(
        {
            "sector": metadata.sector,
            "sector_key": metadata.sector_key,
            "industry": metadata.industry,
            "industry_key": metadata.industry_key,
            "quote_type": metadata.quote_type,
            "metadata_source": metadata.provider,
            "metadata_fetched_at": metadata.fetched_at.isoformat(),
            "metadata_error": None,
        }
    )
    return updated


def enrich_holding_metadata(
    rows: Iterable[Mapping[str, Any]],
    provider: SecurityMetadataProvider | None,
    *,
    cache: TTLSecurityMetadataCache | None = None,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_METADATA_MAX_AGE_DAYS,
    failure_retry_hours: int = DEFAULT_METADATA_FAILURE_RETRY_HOURS,
    max_lookups: int = DEFAULT_METADATA_MAX_LOOKUPS_PER_RUN,
) -> list[dict[str, object]]:
    if max_age_days <= 0 or failure_retry_hours <= 0 or max_lookups < 0:
        raise ValueError("metadata refresh limits are invalid")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    metadata_cache = cache or DEFAULT_SECURITY_METADATA_CACHE
    output: list[dict[str, object]] = []
    lookups = 0

    for source_row in rows:
        row: dict[str, object] = dict(source_row)
        explicit_sector = _clean_text(row.get("sector"))
        known_sector = known_sector_for_holding(row)
        if (not explicit_sector or explicit_sector == "기타") and known_sector:
            row.update(
                {
                    "sector": known_sector,
                    "metadata_source": "built_in",
                    "metadata_fetched_at": row.get("metadata_fetched_at") or current_time.isoformat(),
                    "metadata_error": None,
                }
            )
            output.append(row)
            continue
        if explicit_sector and explicit_sector != "기타" and not _clean_text(row.get("metadata_source")):
            row["metadata_source"] = "manual"
        if not _metadata_refresh_due(
            row,
            now=current_time,
            max_age_days=max_age_days,
            failure_retry_hours=failure_retry_hours,
        ):
            output.append(row)
            continue

        symbol = _clean_text(row.get("ticker") or row.get("symbol")).upper()
        market = _clean_text(row.get("market")).upper()
        cached = metadata_cache.get(symbol, market)
        if cached is not None:
            output.append(_apply_metadata(row, cached))
            continue
        cached_failure = metadata_cache.get_failure(symbol, market)
        if cached_failure is not None:
            row["metadata_error"] = cached_failure
            output.append(row)
            continue
        if provider is None or lookups >= max_lookups:
            output.append(row)
            continue

        lookups += 1
        try:
            metadata = provider.get_metadata(symbol, market=market)
        except SecurityMetadataError as exc:
            message = str(exc)
            metadata_cache.set_failure(symbol, market, message)
            row.update(
                {
                    "sector": explicit_sector or "기타",
                    "metadata_source": getattr(provider, "provider_name", provider.__class__.__name__),
                    "metadata_fetched_at": current_time.isoformat(),
                    "metadata_error": message,
                }
            )
            output.append(row)
            continue
        metadata_cache.set(metadata)
        output.append(_apply_metadata(row, metadata))
    return output


def build_yfinance_security_metadata_provider() -> YFinanceSecurityMetadataProvider:
    return YFinanceSecurityMetadataProvider()
