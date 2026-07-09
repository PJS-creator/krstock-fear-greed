from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


YAHOO_CHART_INDEX_PROVIDER = "yahoo-chart"
YAHOO_CHART_INDEX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
YAHOO_CHART_WARNING_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=60d&interval=60m"
MARKET_WARNING_MA_PERIOD = 5
MARKET_WARNING_BOLLINGER_PERIOD = 180
MARKET_WARNING_BOLLINGER_MULTIPLIER = 2.0
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; krstock-fear-greed/1.0; +https://github.com/PJS-creator/krstock-fear-greed)",
    "Accept": "application/json",
}


@dataclass(frozen=True)
class MarketIndexSpec:
    label: str
    symbol: str
    display_symbol: str | None = None
    fallback_symbols: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class MarketWarningSpec:
    label: str
    symbol: str
    display_symbol: str | None = None
    kis_symbol: str | None = None
    kis_market_div_code: str = "F"
    requires_kis: bool = False


@dataclass(frozen=True)
class MarketWarningSignal:
    label: str
    symbol: str
    status: str
    trigger: str
    value: float | None
    moving_average: float | None
    upper_band: float | None
    middle_band: float | None
    lower_band: float | None
    source: str
    fetched_at: datetime
    as_of_timestamp: datetime | None = None
    error_message: str | None = None

    @property
    def blocks_buy(self) -> bool:
        return self.status == "buy_blocked"

    @property
    def blocks_sell(self) -> bool:
        return self.status == "sell_blocked"


DEFAULT_MARKET_INDEX_SPECS = (
    MarketIndexSpec("코스피", "^KS11"),
    MarketIndexSpec("코스닥", "^KQ11"),
    MarketIndexSpec("나스닥", "^IXIC"),
    MarketIndexSpec("필라델피아 반도체", "^SOX", "SOX"),
    MarketIndexSpec("미국 바이오", "^SPSIBI", "SPSIBI"),
    MarketIndexSpec("금 지수", "XAUUSD=X", "XAU/USD", ("GC=F", "GLD")),
)

DEFAULT_MARKET_WARNING_SPECS = (
    MarketWarningSpec("KOSPI 200 지수", "^KS200", "^KS200"),
    MarketWarningSpec("NASDAQ 100 선물", "NQ=F", "NQ=F"),
)


class MarketIndexProviderError(RuntimeError):
    """Raised when an index provider cannot return a usable quote."""


class KisFuturesIntradayProvider(Protocol):
    def get_domestic_futures_intraday_closes(
        self,
        symbol: str,
        *,
        market_div_code: str = "F",
    ) -> list[tuple[datetime | None, float]]: ...


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


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _population_stddev(values: list[float], mean: float) -> float:
    if not values:
        return 0.0
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(max(variance, 0.0))


def _market_warning_signal_from_points(
    spec: MarketWarningSpec,
    points: list[tuple[datetime | None, float]],
    *,
    source: str,
) -> MarketWarningSignal:
    if not points:
        raise MarketIndexProviderError("60분봉 종가 데이터가 없습니다.")

    closes = [point[1] for point in points]
    latest_timestamp, latest_value = points[-1]
    ma_window = closes[-MARKET_WARNING_MA_PERIOD:]
    moving_average = _average(ma_window)
    if len(closes) < MARKET_WARNING_BOLLINGER_PERIOD:
        return MarketWarningSignal(
            label=spec.label,
            symbol=spec.display_symbol or spec.symbol,
            status="insufficient",
            trigger="데이터 부족",
            value=latest_value,
            moving_average=moving_average,
            upper_band=None,
            middle_band=None,
            lower_band=None,
            source=source,
            fetched_at=datetime.now(timezone.utc),
            as_of_timestamp=latest_timestamp,
            error_message=f"60분봉 {MARKET_WARNING_BOLLINGER_PERIOD}개 미만",
        )

    band_window = closes[-MARKET_WARNING_BOLLINGER_PERIOD:]
    middle = _average(band_window) or latest_value
    stddev = _population_stddev(band_window, middle)
    upper = middle + MARKET_WARNING_BOLLINGER_MULTIPLIER * stddev
    lower = middle - MARKET_WARNING_BOLLINGER_MULTIPLIER * stddev
    if latest_value > upper:
        status = "buy_blocked"
        trigger = "상단 이탈"
    elif latest_value < lower:
        status = "sell_blocked"
        trigger = "하단 이탈"
    else:
        status = "clear"
        trigger = "정상 범위"

    return MarketWarningSignal(
        label=spec.label,
        symbol=spec.display_symbol or spec.symbol,
        status=status,
        trigger=trigger,
        value=latest_value,
        moving_average=moving_average,
        upper_band=upper,
        middle_band=middle,
        lower_band=lower,
        source=source,
        fetched_at=datetime.now(timezone.utc),
        as_of_timestamp=latest_timestamp,
    )


def parse_yahoo_chart_market_warning_response(spec: MarketWarningSpec, payload: Any) -> MarketWarningSignal:
    result = _chart_result(payload)
    points = _close_points(result)
    try:
        return _market_warning_signal_from_points(spec, points, source=YAHOO_CHART_INDEX_PROVIDER)
    except MarketIndexProviderError as exc:
        raise MarketIndexProviderError(f"Yahoo chart 경고 지표 계산 실패: {exc}") from exc


def market_warning_signal_from_kis_points(
    spec: MarketWarningSpec,
    points: list[tuple[datetime | None, float]],
) -> MarketWarningSignal:
    return _market_warning_signal_from_points(spec, points, source="korea_investment")


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
        encoded_symbol = quote(spec.symbol, safe="=")
        request = Request(YAHOO_CHART_INDEX_URL.format(symbol=encoded_symbol), headers=HTTP_HEADERS)
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise MarketIndexProviderError(f"Yahoo chart 지수 조회 실패: {spec.display_symbol or spec.symbol}") from exc
        return parse_yahoo_chart_market_index_response(spec, payload)


class YahooChartMarketWarningProvider:
    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        opener=urlopen,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def get_signal(self, spec: MarketWarningSpec) -> MarketWarningSignal:
        encoded_symbol = quote(spec.symbol, safe="=")
        request = Request(YAHOO_CHART_WARNING_URL.format(symbol=encoded_symbol), headers=HTTP_HEADERS)
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise MarketIndexProviderError(f"Yahoo chart 경고 지표 조회 실패: {spec.display_symbol or spec.symbol}") from exc
        return parse_yahoo_chart_market_warning_response(spec, payload)


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


def failed_market_warning_signal(spec: MarketWarningSpec, error: object) -> MarketWarningSignal:
    return MarketWarningSignal(
        label=spec.label,
        symbol=spec.display_symbol or spec.symbol,
        status="failed",
        trigger="조회 실패",
        value=None,
        moving_average=None,
        upper_band=None,
        middle_band=None,
        lower_band=None,
        source=YAHOO_CHART_INDEX_PROVIDER,
        fetched_at=datetime.now(timezone.utc),
        error_message=str(error),
    )


def failed_kis_market_warning_signal(spec: MarketWarningSpec, error: object) -> MarketWarningSignal:
    return MarketWarningSignal(
        label=spec.label,
        symbol=spec.display_symbol or spec.symbol,
        status="failed",
        trigger="KIS 조회 실패",
        value=None,
        moving_average=None,
        upper_band=None,
        middle_band=None,
        lower_band=None,
        source="korea_investment",
        fetched_at=datetime.now(timezone.utc),
        error_message=str(error),
    )


def configuration_required_market_warning_signal(spec: MarketWarningSpec, message: str) -> MarketWarningSignal:
    return MarketWarningSignal(
        label=spec.label,
        symbol=spec.display_symbol or spec.symbol,
        status="configuration_required",
        trigger="KIS 설정 필요",
        value=None,
        moving_average=None,
        upper_band=None,
        middle_band=None,
        lower_band=None,
        source="korea_investment",
        fetched_at=datetime.now(timezone.utc),
        error_message=message,
    )


def _fetch_market_index_with_fallback(
    spec: MarketIndexSpec,
    provider: YahooChartMarketIndexProvider,
) -> MarketIndexQuote:
    errors: list[str] = []
    candidate_specs = [spec]
    candidate_specs.extend(MarketIndexSpec(spec.label, symbol, spec.display_symbol) for symbol in spec.fallback_symbols)
    for candidate in candidate_specs:
        try:
            return provider.get_quote(candidate)
        except MarketIndexProviderError as exc:
            errors.append(f"{candidate.symbol}: {exc}")
    raise MarketIndexProviderError("; ".join(errors) or f"지수 조회 실패: {spec.display_symbol or spec.symbol}")


def fetch_market_indices(
    specs: Iterable[MarketIndexSpec] = DEFAULT_MARKET_INDEX_SPECS,
    *,
    provider: YahooChartMarketIndexProvider | None = None,
) -> list[MarketIndexQuote]:
    active_provider = provider or YahooChartMarketIndexProvider()
    quotes: list[MarketIndexQuote] = []
    for spec in specs:
        try:
            quotes.append(_fetch_market_index_with_fallback(spec, active_provider))
        except MarketIndexProviderError as exc:
            quotes.append(failed_market_index_quote(spec, exc))
    return quotes


def fetch_market_warning_signals(
    specs: Iterable[MarketWarningSpec] = DEFAULT_MARKET_WARNING_SPECS,
    *,
    provider: YahooChartMarketWarningProvider | None = None,
    kis_provider: KisFuturesIntradayProvider | None = None,
) -> list[MarketWarningSignal]:
    active_provider = provider or YahooChartMarketWarningProvider()
    signals: list[MarketWarningSignal] = []
    for spec in specs:
        if spec.requires_kis and (not spec.kis_symbol or kis_provider is None):
            signals.append(
                configuration_required_market_warning_signal(
                    spec,
                    f"{spec.label} 경고에는 KIS 앱키와 KIS 선물 종목코드 설정이 필요합니다.",
                )
            )
            continue
        if spec.kis_symbol and kis_provider is not None:
            try:
                points = kis_provider.get_domestic_futures_intraday_closes(
                    spec.kis_symbol,
                    market_div_code=spec.kis_market_div_code,
                )
                signals.append(market_warning_signal_from_kis_points(spec, points))
                continue
            except Exception as exc:
                if spec.requires_kis:
                    signals.append(failed_kis_market_warning_signal(spec, exc))
                    continue
                try:
                    signals.append(active_provider.get_signal(spec))
                    continue
                except MarketIndexProviderError as fallback_exc:
                    signals.append(failed_market_warning_signal(spec, f"KIS: {exc}; Yahoo fallback: {fallback_exc}"))
                    continue
        try:
            signals.append(active_provider.get_signal(spec))
        except MarketIndexProviderError as exc:
            signals.append(failed_market_warning_signal(spec, exc))
    return signals

