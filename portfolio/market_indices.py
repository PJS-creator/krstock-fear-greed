from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


YAHOO_CHART_INDEX_PROVIDER = "yahoo-chart"
YAHOO_CHART_INDEX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; krstock-fear-greed/1.0; +https://github.com/PJS-creator/krstock-fear-greed)",
    "Accept": "application/json",
}


@dataclass(frozen=True)
class MarketIndexSpec:
    label: str
    symbol: str
    display_symbol: str | None = None


@dataclass(frozen=True)
class MarketIndexQuote:
    label: str
    symbol: str
    value: float | None
    previous_close: float | None
    change: float | None
    change_pct: float | None
    status: str
    source: str
    fetched_at: datetime
    as_of_timestamp: datetime | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "updated" and self.value is not None


DEFAULT_MARKET_INDEX_SPECS = (
    MarketIndexSpec("코스피", "^KS11"),
    MarketIndexSpec("코스닥", "^KQ11"),
    MarketIndexSpec("나스닥", "^IXIC"),
    MarketIndexSpec("필라델피아 반도체", "^SOX", "SOX"),
    MarketIndexSpec("미국 바이오", "^SPSIBI", "SPSIBI"),
)


class MarketIndexProviderError(RuntimeError):
    """Raised when an index provider cannot return a usable quote."""


def _as_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _timestamp(value: object) -> datetime | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def _chart_result(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MarketIndexProviderError("Yahoo chart 응답 형식이 올바르지 않습니다.")
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise MarketIndexProviderError("Yahoo chart 응답에 chart 데이터가 없습니다.")
    error = chart.get("error")
    if error:
        raise MarketIndexProviderError(f"Yahoo chart 오류: {error}")
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        raise MarketIndexProviderError("Yahoo chart 응답에 result 데이터가 없습니다.")
    result = results[0]
    if not isinstance(result, dict):
        raise MarketIndexProviderError("Yahoo chart result 형식이 올바르지 않습니다.")
    return result


def _close_points(result: dict[str, Any]) -> list[tuple[datetime | None, float]]:
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    quote_payload = quotes[0] if isinstance(quotes, list) and quotes else {}
    closes = quote_payload.get("close") if isinstance(quote_payload, dict) else []
    points: list[tuple[datetime | None, float]] = []
    if not isinstance(closes, list):
        return points
    for index, raw_close in enumerate(closes):
        close = _as_float(raw_close)
        if close is None:
            continue
        raw_timestamp = timestamps[index] if isinstance(timestamps, list) and index < len(timestamps) else None
        points.append((_timestamp(raw_timestamp), close))
    return points


def parse_yahoo_chart_market_index_response(spec: MarketIndexSpec, payload: Any) -> MarketIndexQuote:
    result = _chart_result(payload)
    meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
    points = _close_points(result)

    price = _as_float(meta.get("regularMarketPrice"))
    if price is None and points:
        price = points[-1][1]
    if price is None:
        raise MarketIndexProviderError("Yahoo chart 응답에 현재 지수 값이 없습니다.")

    previous_close = _as_float(meta.get("regularMarketPreviousClose"))
    if previous_close is None and len(points) >= 2:
        previous_close = points[-2][1]
    if previous_close is None:
        previous_close = _as_float(meta.get("chartPreviousClose"))
    if previous_close is None:
        previous_close = price

    as_of = points[-1][0] if points else _timestamp(meta.get("regularMarketTime"))
    change = price - previous_close
    change_pct = change / previous_close if previous_close else None
    return MarketIndexQuote(
        label=spec.label,
        symbol=spec.display_symbol or spec.symbol,
        value=price,
        previous_close=previous_close,
        change=change,
        change_pct=change_pct,
        status="updated",
        source=YAHOO_CHART_INDEX_PROVIDER,
        fetched_at=datetime.now(timezone.utc),
        as_of_timestamp=as_of,
    )


class YahooChartMarketIndexProvider:
    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        opener=urlopen,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def get_quote(self, spec: MarketIndexSpec) -> MarketIndexQuote:
        encoded_symbol = quote(spec.symbol, safe="")
        request = Request(YAHOO_CHART_INDEX_URL.format(symbol=encoded_symbol), headers=HTTP_HEADERS)
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise MarketIndexProviderError(f"Yahoo chart 지수 조회 실패: {spec.display_symbol or spec.symbol}") from exc
        return parse_yahoo_chart_market_index_response(spec, payload)


def failed_market_index_quote(spec: MarketIndexSpec, error: object) -> MarketIndexQuote:
    return MarketIndexQuote(
        label=spec.label,
        symbol=spec.display_symbol or spec.symbol,
        value=None,
        previous_close=None,
        change=None,
        change_pct=None,
        status="failed",
        source=YAHOO_CHART_INDEX_PROVIDER,
        fetched_at=datetime.now(timezone.utc),
        error_message=str(error),
    )


def fetch_market_indices(
    specs: Iterable[MarketIndexSpec] = DEFAULT_MARKET_INDEX_SPECS,
    *,
    provider: YahooChartMarketIndexProvider | None = None,
) -> list[MarketIndexQuote]:
    active_provider = provider or YahooChartMarketIndexProvider()
    quotes: list[MarketIndexQuote] = []
    for spec in specs:
        try:
            quotes.append(active_provider.get_quote(spec))
        except MarketIndexProviderError as exc:
            quotes.append(failed_market_index_quote(spec, exc))
    return quotes

