from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .base import PriceProvider, PriceProviderError
from .cache import TTLQuoteCache
from portfolio.manual_input import normalize_portfolio_rows

FMP_TARGET_MARKETS = {"US", "USA"}
DEFAULT_QUOTE_CACHE = TTLQuoteCache(ttl_seconds=600)


@dataclass(frozen=True)
class PriceUpdateStatus:
    symbol: str
    market: str
    currency: str
    status: str
    message: str


def is_fmp_update_target(row: Mapping[str, Any]) -> bool:
    market = str(row.get("market", "")).strip().upper()
    currency = str(row.get("currency", "")).strip().upper()
    return currency == "USD" and market in FMP_TARGET_MARKETS


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

        if not is_fmp_update_target(row):
            statuses.append(
                PriceUpdateStatus(
                    symbol=symbol,
                    market=market,
                    currency=currency,
                    status="manual",
                    message="수동 입력 유지: v0.3은 미국 USD 종목만 자동 업데이트합니다.",
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
                    message="FMP API key가 없어 수동 입력 가격을 유지했습니다.",
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
                    message=f"FMP 업데이트 실패: {exc}. 기존 입력 가격을 유지했습니다.",
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
                message="FMP 가격으로 current_price와 previous_close를 업데이트했습니다.",
            )
        )
        updated_rows.append(updated_row)

    return updated_rows, statuses
