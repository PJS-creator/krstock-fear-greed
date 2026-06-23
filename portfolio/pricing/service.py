from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Any, Mapping

from .base import FxProvider, PriceProvider, PriceProviderError, ProviderQuote
from .cache import TTLFxCache, TTLQuoteCache
from portfolio.holdings import (
    QUOTE_STATUS_CACHED,
    QUOTE_STATUS_FAILED,
    QUOTE_STATUS_MANUAL,
    QUOTE_STATUS_MISSING,
    QUOTE_STATUS_STALE,
    QUOTE_STATUS_UPDATED,
    normalize_holding_rows,
)
from portfolio.manual_input import normalize_portfolio_rows

AUTO_UPDATE_TARGET_MARKETS = {"US", "USA"}
ALPHA_VANTAGE_REQUEST_INTERVAL_SECONDS = 1.1
DEFAULT_QUOTE_CACHE = TTLQuoteCache(ttl_seconds=600)
DEFAULT_FX_CACHE = TTLFxCache(ttl_seconds=600)


@dataclass(frozen=True)
class PriceUpdateStatus:
    symbol: str
    market: str
    currency: str
    status: str
    message: str
    fetched_at: str | None = None


@dataclass(frozen=True)
class FxUpdateStatus:
    status: str
    message: str
    fetched_at: str | None = None


class _ProviderRequestPacer:
    def __init__(
        self,
        *,
        min_interval_seconds: float,
        sleep_fn: Callable[[float], None],
        now_fn: Callable[[], float],
    ) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.sleep_fn = sleep_fn
        self.now_fn = now_fn
        self.last_request_started_at: float | None = None

    def wait_before_request(self) -> None:
        now = self.now_fn()
        if self.last_request_started_at is not None:
            elapsed = now - self.last_request_started_at
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                self.sleep_fn(remaining)
                now = self.now_fn()
        self.last_request_started_at = now


def is_auto_update_target(row: Mapping[str, Any]) -> bool:
    market = str(row.get("market", "")).strip().upper()
    currency = str(row.get("currency", "")).strip().upper()
    return currency == "USD" and market in AUTO_UPDATE_TARGET_MARKETS


def update_us_quotes(
    rows: list[Mapping[str, Any]],
    provider: PriceProvider | None,
    *,
    cache: TTLQuoteCache | None = None,
) -> tuple[list[dict[str, object]], list[PriceUpdateStatus]]:
    normalized_rows = normalize_portfolio_rows(rows)
    quote_cache = cache or DEFAULT_QUOTE_CACHE
    updated_rows: list[dict[str, object]] = []
    statuses: list[PriceUpdateStatus] = []

    for row in normalized_rows:
        updated_row = dict(row)
        symbol = str(row["symbol"])
        market = str(row["market"])
        currency = str(row["currency"])

        if not is_auto_update_target(row):
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status="manual",
                    message="수동 입력 유지: 미국 USD 종목만 자동 업데이트합니다.",
                )
            )
            updated_rows.append(updated_row)
            continue

        if provider is None:
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status="missing_api_key",
                    message="Alpha Vantage API key가 없어 수동 입력 가격을 유지했습니다.",
                )
            )
            updated_rows.append(updated_row)
            continue

        try:
            quote = quote_cache.get_or_fetch(symbol, provider.get_quote)
        except PriceProviderError as exc:
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status="failed",
                    message=f"Alpha Vantage 업데이트 실패: {exc}. 기존 입력 가격을 유지했습니다.",
                )
            )
            updated_rows.append(updated_row)
            continue

        updated_row["current_price"] = quote.price
        updated_row["previous_close"] = quote.previous_close
        statuses.append(
            PriceUpdateStatus(
                symbol=symbol,
                market=market,
                currency=currency,
                status="updated",
                message="Alpha Vantage 가격으로 current_price와 previous_close를 업데이트했습니다.",
                fetched_at=quote.fetched_at.isoformat(),
            )
        )
        updated_rows.append(updated_row)

    return updated_rows, statuses


def _report_progress(
    on_progress: Callable[[int, int, str], None] | None,
    completed: int,
    total: int,
    symbol: str,
) -> None:
    if on_progress is not None:
        on_progress(completed, total, symbol)


def _get_quote_with_cache_and_pacing(
    symbol: str,
    provider: PriceProvider,
    quote_cache: TTLQuoteCache,
    pacer: _ProviderRequestPacer,
) -> tuple[ProviderQuote, bool]:
    cached_quote = quote_cache.get(symbol)
    if cached_quote is not None:
        return cached_quote, True
    pacer.wait_before_request()
    quote = provider.get_quote(symbol)
    quote_cache.set(symbol, quote)
    return quote, False


def refresh_holding_quotes(
    rows: list[Mapping[str, Any]],
    provider: PriceProvider | None,
    *,
    cache: TTLQuoteCache | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    request_interval_seconds: float = ALPHA_VANTAGE_REQUEST_INTERVAL_SECONDS,
    sleep_fn: Callable[[float], None] = sleep,
    now_fn: Callable[[], float] = monotonic,
) -> tuple[list[dict[str, object]], list[PriceUpdateStatus]]:
    normalized_rows = normalize_holding_rows(rows)
    quote_cache = cache or DEFAULT_QUOTE_CACHE
    pacer = _ProviderRequestPacer(
        min_interval_seconds=request_interval_seconds,
        sleep_fn=sleep_fn,
        now_fn=now_fn,
    )
    updated_rows: list[dict[str, object]] = []
    statuses: list[PriceUpdateStatus] = []
    total_rows = len(normalized_rows)

    for row in normalized_rows:
        updated_row = dict(row)
        symbol = str(row["ticker"])
        market = str(row["market"])
        currency = str(row["currency"])
        has_last_price = row.get("current_price") is not None

        if not is_auto_update_target({"market": market, "currency": currency}):
            status = QUOTE_STATUS_MANUAL if has_last_price else QUOTE_STATUS_MISSING
            updated_row["quote_status"] = status
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status=status,
                    message="KR/KRW 또는 수동 가격 종목은 마지막 입력 가격을 유지합니다.",
                    fetched_at=updated_row.get("fetched_at"),
                )
            )
            updated_rows.append(updated_row)
            _report_progress(on_progress, len(updated_rows), total_rows, symbol)
            continue

        if provider is None:
            status = QUOTE_STATUS_STALE if has_last_price else QUOTE_STATUS_MISSING
            updated_row["quote_status"] = status
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status=status,
                    message="Alpha Vantage API key가 없어 최근 제공 가격을 갱신하지 못했습니다.",
                    fetched_at=updated_row.get("fetched_at"),
                )
            )
            updated_rows.append(updated_row)
            _report_progress(on_progress, len(updated_rows), total_rows, symbol)
            continue

        try:
            quote, was_cached = _get_quote_with_cache_and_pacing(symbol, provider, quote_cache, pacer)
        except PriceProviderError as exc:
            status = QUOTE_STATUS_STALE if has_last_price else QUOTE_STATUS_FAILED
            updated_row["quote_status"] = status
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status=status,
                    message=f"최근 제공 가격 갱신 실패: {exc}. 마지막 정상 가격을 유지했습니다." if has_last_price else f"최근 제공 가격 갱신 실패: {exc}.",
                    fetched_at=updated_row.get("fetched_at"),
                )
            )
            updated_rows.append(updated_row)
            _report_progress(on_progress, len(updated_rows), total_rows, symbol)
            continue

        status = QUOTE_STATUS_CACHED if was_cached else QUOTE_STATUS_UPDATED
        updated_row["current_price"] = quote.price
        updated_row["previous_close"] = quote.previous_close
        updated_row["quote_status"] = status
        updated_row["fetched_at"] = quote.fetched_at.isoformat()
        updated_row["provider"] = quote.provider
        statuses.append(
            PriceUpdateStatus(
                symbol=symbol,
                market=market,
                currency=currency,
                status=status,
                message="캐시된 최근 제공 가격을 사용했습니다." if was_cached else "최근 제공 가격으로 갱신했습니다.",
                fetched_at=quote.fetched_at.isoformat(),
            )
        )
        updated_rows.append(updated_row)
        _report_progress(on_progress, len(updated_rows), total_rows, symbol)

    return updated_rows, statuses


def refresh_usd_krw(
    provider: FxProvider | None,
    current_usd_krw: float,
    *,
    cache: TTLFxCache | None = None,
) -> tuple[float, FxUpdateStatus]:
    if current_usd_krw <= 0:
        raise ValueError("current_usd_krw must be positive")
    if provider is None:
        return current_usd_krw, FxUpdateStatus(
            status=QUOTE_STATUS_MISSING,
            message="Alpha Vantage API key가 없어 수동 USD/KRW 환율을 유지했습니다.",
        )
    fx_cache = cache or DEFAULT_FX_CACHE
    try:
        rate, was_cached = fx_cache.get_or_fetch_with_status("USD", "KRW", provider.get_exchange_rate)
    except PriceProviderError as exc:
        return current_usd_krw, FxUpdateStatus(
            status=QUOTE_STATUS_FAILED,
            message=f"USD/KRW 환율 갱신 실패: {exc}. 기존 수동 환율을 유지했습니다.",
        )
    status = QUOTE_STATUS_CACHED if was_cached else QUOTE_STATUS_UPDATED
    return rate.rate, FxUpdateStatus(
        status=status,
        message="캐시된 USD/KRW 환율을 사용했습니다." if was_cached else "USD/KRW 환율을 갱신했습니다.",
        fetched_at=rate.fetched_at.isoformat(),
    )
