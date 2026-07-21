from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen


QQQ_HISTORY_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/QQQ"
    "?range=10y&interval=1d&events=history&includeAdjustedClose=true"
)
FRED_LIQUIDITY_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv"
    "?id=WALCL%2CWDTGAL%2CRRPONTSYD&cosd={start_date}"
)
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; krstock-fear-greed/1.0; +https://github.com/PJS-creator/krstock-fear-greed)",
    "Accept": "application/json,text/csv,application/zip,*/*",
}

LIQUIDITY_BULL = "BULL"
LIQUIDITY_MIXED = "MIXED"
LIQUIDITY_BEAR = "BEAR"
TREND_UP = "UP"
TREND_DOWN = "DOWN"
REGIME_BULL = "bull"
REGIME_MIXED = "mixed"
REGIME_BEAR = "bear"


class MetaStrategyError(RuntimeError):
    """Raised when meta-strategy data cannot be fetched or parsed."""


class MetaStrategyInsufficientData(MetaStrategyError):
    """Raised when valid data exists but is too short for the strategy rules."""


@dataclass(frozen=True)
class DatedValue:
    as_of_date: date
    value: float


@dataclass(frozen=True)
class LiquiditySignal:
    as_of_date: date
    percentile: float
    state: str
    net_liquidity_billions: float


@dataclass(frozen=True)
class TechnicalSnapshot:
    as_of_date: date
    close: float
    sma20: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    trend200: str | None
    recovery: bool
    comparison1_ticker: str
    comparison3_ticker: str


@dataclass(frozen=True)
class MetaStrategyResult:
    status: str
    market_regime: str | None
    market_regime_label: str
    active_strategy: str | None
    active_strategy_label: str
    applied_ticker: str | None
    qqq_as_of_date: date | None
    liquidity_as_of_date: date | None
    liquidity_percentile: float | None
    liquidity_state: str | None
    trend200: str | None
    recovery: bool | None
    qqq_close: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    source: str
    fetched_at: datetime
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "updated" and self.applied_ticker is not None


class MetaStrategyProvider(Protocol):
    def get_qqq_history(self) -> list[DatedValue]: ...

    def get_liquidity_series(self) -> dict[str, list[DatedValue]]: ...


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _deduplicate_points(points: list[DatedValue]) -> list[DatedValue]:
    by_date = {point.as_of_date: point for point in points}
    return [by_date[key] for key in sorted(by_date)]


def parse_yahoo_qqq_history(payload: Any) -> list[DatedValue]:
    if not isinstance(payload, dict):
        raise MetaStrategyError("Yahoo QQQ 응답 형식이 올바르지 않습니다.")
    chart = payload.get("chart")
    if not isinstance(chart, dict) or chart.get("error"):
        raise MetaStrategyError(f"Yahoo QQQ 응답 오류: {chart.get('error') if isinstance(chart, dict) else 'chart 없음'}")
    results = chart.get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise MetaStrategyError("Yahoo QQQ 응답에 시계열이 없습니다.")

    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") if isinstance(result.get("indicators"), dict) else {}
    adjusted_rows = indicators.get("adjclose") if isinstance(indicators, dict) else None
    adjusted = adjusted_rows[0].get("adjclose") if isinstance(adjusted_rows, list) and adjusted_rows and isinstance(adjusted_rows[0], dict) else None
    quote_rows = indicators.get("quote") if isinstance(indicators, dict) else None
    closes = quote_rows[0].get("close") if isinstance(quote_rows, list) and quote_rows and isinstance(quote_rows[0], dict) else []
    values = adjusted if isinstance(adjusted, list) else closes
    if not isinstance(timestamps, list) or not isinstance(values, list):
        raise MetaStrategyError("Yahoo QQQ 종가 배열이 올바르지 않습니다.")

    points: list[DatedValue] = []
    for index, raw_timestamp in enumerate(timestamps):
        if index >= len(values):
            break
        value = _finite_float(values[index])
        if value is None:
            continue
        try:
            point_date = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc).date()
        except (TypeError, ValueError, OSError):
            continue
        points.append(DatedValue(point_date, value))
    points = _deduplicate_points(points)
    if not points:
        raise MetaStrategyError("Yahoo QQQ 응답에 유효한 조정종가가 없습니다.")
    return points


def _fred_csv_texts(payload: bytes | str) -> list[str]:
    if isinstance(payload, str):
        return [payload]
    if payload.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not csv_names:
                    raise MetaStrategyError("FRED 압축 파일에 CSV가 없습니다.")
                return [archive.read(name).decode("utf-8-sig") for name in csv_names]
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
            raise MetaStrategyError("FRED 압축 데이터를 읽을 수 없습니다.") from exc
    try:
        return [payload.decode("utf-8-sig")]
    except UnicodeDecodeError as exc:
        raise MetaStrategyError("FRED CSV 인코딩을 읽을 수 없습니다.") from exc


def parse_fred_liquidity_csv(payload: bytes | str) -> dict[str, list[DatedValue]]:
    series_ids = ("WALCL", "WDTGAL", "RRPONTSYD")
    result = {series_id: [] for series_id in series_ids}
    for csv_text in _fred_csv_texts(payload):
        reader = csv.DictReader(io.StringIO(csv_text))
        if not reader.fieldnames:
            continue
        date_field = next((name for name in reader.fieldnames if name.strip().lower() in {"date", "observation_date"}), None)
        if date_field is None:
            continue
        available_series = [series_id for series_id in series_ids if series_id in reader.fieldnames]
        for row in reader:
            try:
                point_date = date.fromisoformat(str(row.get(date_field) or "").strip())
            except ValueError:
                continue
            for series_id in available_series:
                value = _finite_float(row.get(series_id))
                if value is not None:
                    result[series_id].append(DatedValue(point_date, value))
    result = {series_id: _deduplicate_points(points) for series_id, points in result.items()}
    missing = [series_id for series_id, points in result.items() if not points]
    if missing:
        raise MetaStrategyError("FRED CSV에 필요한 지표가 없습니다: " + ", ".join(missing))
    return result


def simple_moving_average(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    result: list[float | None] = [None] * len(values)
    running_sum = 0.0
    for index, value in enumerate(values):
        running_sum += value
        if index >= window:
            running_sum -= values[index - window]
        if index >= window - 1:
            result[index] = running_sum / window
    return result


def wilder_rsi(values: list[float], period: int = 14) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    gains = [max(values[index] - values[index - 1], 0.0) for index in range(1, len(values))]
    losses = [max(values[index - 1] - values[index], 0.0) for index in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def score(gain: float, loss: float) -> float:
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        relative_strength = gain / loss
        return 100.0 - 100.0 / (1.0 + relative_strength)

    result[period] = score(avg_gain, avg_loss)
    for value_index in range(period + 1, len(values)):
        change_index = value_index - 1
        avg_gain = ((avg_gain * (period - 1)) + gains[change_index]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[change_index]) / period
        result[value_index] = score(avg_gain, avg_loss)
    return result


def classify_liquidity_state(previous_state: str, percentile: float) -> str:
    previous = previous_state if previous_state in {LIQUIDITY_BULL, LIQUIDITY_MIXED, LIQUIDITY_BEAR} else LIQUIDITY_MIXED
    if previous == LIQUIDITY_BULL:
        if percentile <= 25:
            return LIQUIDITY_BEAR
        if percentile < 65:
            return LIQUIDITY_MIXED
        return LIQUIDITY_BULL
    if previous == LIQUIDITY_BEAR:
        if percentile >= 75:
            return LIQUIDITY_BULL
        if percentile > 35:
            return LIQUIDITY_MIXED
        return LIQUIDITY_BEAR
    if percentile >= 75:
        return LIQUIDITY_BULL
    if percentile <= 25:
        return LIQUIDITY_BEAR
    return LIQUIDITY_MIXED


def _last_value_on_or_before(points: list[DatedValue], target_date: date, start_index: int = 0) -> tuple[float | None, int]:
    index = start_index
    latest: float | None = None
    while index < len(points) and points[index].as_of_date <= target_date:
        latest = points[index].value
        index += 1
    return latest, max(index - 1, 0)


def calculate_liquidity_signals(series: dict[str, list[DatedValue]]) -> list[LiquiditySignal]:
    walcl = _deduplicate_points(list(series.get("WALCL") or []))
    wdtgal = _deduplicate_points(list(series.get("WDTGAL") or []))
    rrp = _deduplicate_points(list(series.get("RRPONTSYD") or []))
    if not walcl or not wdtgal or not rrp:
        raise MetaStrategyInsufficientData("유동성 지표 3종의 유효한 관측치가 필요합니다.")

    weekly: list[tuple[date, float]] = []
    w_index = 0
    r_index = 0
    for fed_point in walcl:
        treasury, w_index = _last_value_on_or_before(wdtgal, fed_point.as_of_date, w_index)
        reverse_repo, r_index = _last_value_on_or_before(rrp, fed_point.as_of_date, r_index)
        if treasury is None or reverse_repo is None:
            continue
        net_liquidity = fed_point.value / 1000.0 - treasury / 1000.0 - reverse_repo
        if net_liquidity > 0:
            weekly.append((fed_point.as_of_date + timedelta(days=2), net_liquidity))
    if len(weekly) < 300:
        raise MetaStrategyInsufficientData(f"유동성 판정에는 최소 300주가 필요합니다. 현재 {len(weekly)}주입니다.")

    growth: list[float | None] = [None] * len(weekly)
    for index in range(26, len(weekly)):
        current = weekly[index][1]
        previous = weekly[index - 26][1]
        if current > 0 and previous > 0:
            growth[index] = math.log(current / previous)

    smooth: list[float | None] = [None] * len(weekly)
    for index in range(12, len(weekly)):
        window = growth[index - 12 : index + 1]
        if all(value is not None for value in window):
            smooth[index] = sum(float(value) for value in window) / 13.0

    raw_percentiles: list[float | None] = [None] * len(weekly)
    for index, current in enumerate(smooth):
        if current is None or index < 260:
            continue
        history = smooth[index - 260 : index]
        if any(value is None for value in history):
            continue
        lower = sum(1 for value in history if float(value) < current)
        equal = sum(1 for value in history if float(value) == current)
        raw_percentiles[index] = 100.0 * (lower + 0.5 * equal) / 260.0

    state = LIQUIDITY_MIXED
    signals: list[LiquiditySignal] = []
    for index in range(1, len(weekly)):
        applied_percentile = raw_percentiles[index - 1]
        if applied_percentile is None:
            continue
        state = classify_liquidity_state(state, applied_percentile)
        signals.append(
            LiquiditySignal(
                as_of_date=weekly[index][0],
                percentile=applied_percentile,
                state=state,
                net_liquidity_billions=weekly[index][1],
            )
        )
    if not signals:
        raise MetaStrategyInsufficientData("유동성 백분위를 계산할 수 있는 기간이 부족합니다.")
    return signals


def advance_comparison3(
    current_ticker: str,
    *,
    close: float,
    sma200: float | None,
    previous_rsi: float | None,
    current_rsi: float | None,
) -> str:
    ticker = current_ticker if current_ticker in {"QLD", "TQQQ"} else "QLD"
    if sma200 is None or previous_rsi is None or current_rsi is None:
        return ticker
    if ticker == "QLD" and close < sma200 and previous_rsi <= 40 < current_rsi:
        return "TQQQ"
    if ticker == "TQQQ" and previous_rsi <= 80 < current_rsi:
        return "QLD"
    return ticker


def advance_comparison1(
    confirmed_ticker: str,
    candidate_ticker: str | None,
    candidate_count: int,
    raw_ticker: str,
) -> tuple[str, str | None, int]:
    confirmed = confirmed_ticker if confirmed_ticker in {"QQQ", "QLD", "TQQQ"} else "QLD"
    if raw_ticker == confirmed:
        return confirmed, None, 0
    if raw_ticker == candidate_ticker:
        candidate_count += 1
    else:
        candidate_ticker = raw_ticker
        candidate_count = 1
    if candidate_count >= 2:
        return str(candidate_ticker), None, 0
    return confirmed, candidate_ticker, candidate_count


def classify_market_regime(trend200: str | None, recovery: bool, liquidity_state: str) -> str:
    if trend200 == TREND_DOWN and not recovery:
        return REGIME_BEAR
    if trend200 == TREND_UP and liquidity_state == LIQUIDITY_BULL:
        return REGIME_BULL
    return REGIME_MIXED


def analyze_qqq_technicals(points: list[DatedValue]) -> TechnicalSnapshot:
    prices = _deduplicate_points(points)
    if len(prices) < 205:
        raise MetaStrategyInsufficientData(f"QQQ 기술 판정에는 최소 205거래일이 필요합니다. 현재 {len(prices)}일입니다.")
    closes = [point.value for point in prices]
    sma20 = simple_moving_average(closes, 20)
    sma50 = simple_moving_average(closes, 50)
    sma200 = simple_moving_average(closes, 200)
    rsi14 = wilder_rsi(closes, 14)

    week_end_indices: set[int] = set()
    previous_week: tuple[int, int] | None = None
    previous_index: int | None = None
    for index, point in enumerate(prices):
        week = (point.as_of_date.isocalendar().year, point.as_of_date.isocalendar().week)
        if previous_week is not None and week != previous_week and previous_index is not None:
            week_end_indices.add(previous_index)
        previous_week = week
        previous_index = index
    if previous_index is not None:
        week_end_indices.add(previous_index)

    trend: str | None = None
    trend_candidate: str | None = None
    trend_candidate_count = 0
    recovery = False
    above_sma20_count = 0
    below_sma20_count = 0
    comparison1 = "QLD"
    comparison1_candidate: str | None = None
    comparison1_count = 0
    comparison3 = "QLD"

    for index, close in enumerate(closes):
        transition_to_down = False
        if index in week_end_indices and sma200[index] is not None:
            side = TREND_UP if close > float(sma200[index]) else TREND_DOWN if close < float(sma200[index]) else None
            if side is None:
                trend_candidate = None
                trend_candidate_count = 0
            elif side == trend_candidate:
                trend_candidate_count += 1
            else:
                trend_candidate = side
                trend_candidate_count = 1
            if side is not None and trend_candidate_count >= 2 and side != trend:
                transition_to_down = side == TREND_DOWN
                trend = side
                trend_candidate = None
                trend_candidate_count = 0

        if transition_to_down:
            recovery = False
            above_sma20_count = 0
            below_sma20_count = 0
        elif trend == TREND_DOWN and sma20[index] is not None:
            if close > float(sma20[index]):
                above_sma20_count += 1
                below_sma20_count = 0
            else:
                below_sma20_count += 1
                above_sma20_count = 0
            if below_sma20_count >= 2:
                recovery = False
            if (
                above_sma20_count >= 5
                and index >= 5
                and sma20[index - 5] is not None
                and float(sma20[index]) > float(sma20[index - 5])
            ):
                recovery = True
        elif trend != TREND_DOWN:
            recovery = False
            above_sma20_count = 0
            below_sma20_count = 0

        if sma50[index] is not None and sma200[index] is not None:
            if close > float(sma50[index]) and close > float(sma200[index]):
                raw_ticker = "TQQQ"
            elif close < float(sma50[index]) and close < float(sma200[index]):
                raw_ticker = "QQQ"
            else:
                raw_ticker = "QLD"
            comparison1, comparison1_candidate, comparison1_count = advance_comparison1(
                comparison1,
                comparison1_candidate,
                comparison1_count,
                raw_ticker,
            )
        comparison3 = advance_comparison3(
            comparison3,
            close=close,
            sma200=sma200[index],
            previous_rsi=rsi14[index - 1] if index else None,
            current_rsi=rsi14[index],
        )

    latest = prices[-1]
    return TechnicalSnapshot(
        as_of_date=latest.as_of_date,
        close=latest.value,
        sma20=sma20[-1],
        sma50=sma50[-1],
        sma200=sma200[-1],
        rsi14=rsi14[-1],
        trend200=trend,
        recovery=recovery,
        comparison1_ticker=comparison1,
        comparison3_ticker=comparison3,
    )


def build_meta_strategy_result(
    qqq_points: list[DatedValue],
    liquidity_series: dict[str, list[DatedValue]],
    *,
    fetched_at: datetime | None = None,
) -> MetaStrategyResult:
    technical = analyze_qqq_technicals(qqq_points)
    liquidity = calculate_liquidity_signals(liquidity_series)[-1]
    regime = classify_market_regime(technical.trend200, technical.recovery, liquidity.state)
    labels = {
        REGIME_BULL: "강세장",
        REGIME_MIXED: "혼재장",
        REGIME_BEAR: "약세장",
    }
    if regime == REGIME_BEAR:
        strategy = "comparison1"
        strategy_label = "비교1 · 추세 확인"
        ticker = technical.comparison1_ticker
    else:
        strategy = "comparison3"
        strategy_label = "비교3 · RSI 전환"
        ticker = technical.comparison3_ticker
    return MetaStrategyResult(
        status="updated",
        market_regime=regime,
        market_regime_label=labels[regime],
        active_strategy=strategy,
        active_strategy_label=strategy_label,
        applied_ticker=ticker,
        qqq_as_of_date=technical.as_of_date,
        liquidity_as_of_date=liquidity.as_of_date,
        liquidity_percentile=liquidity.percentile,
        liquidity_state=liquidity.state,
        trend200=technical.trend200,
        recovery=technical.recovery,
        qqq_close=technical.close,
        sma20=technical.sma20,
        sma50=technical.sma50,
        sma200=technical.sma200,
        rsi14=technical.rsi14,
        source="FRED + Yahoo chart",
        fetched_at=fetched_at or datetime.now(timezone.utc),
    )


def unavailable_meta_strategy_result(error: object, *, status: str = "failed") -> MetaStrategyResult:
    return MetaStrategyResult(
        status=status,
        market_regime=None,
        market_regime_label="판정 불가" if status == "failed" else "데이터 부족",
        active_strategy=None,
        active_strategy_label="-",
        applied_ticker=None,
        qqq_as_of_date=None,
        liquidity_as_of_date=None,
        liquidity_percentile=None,
        liquidity_state=None,
        trend200=None,
        recovery=None,
        qqq_close=None,
        sma20=None,
        sma50=None,
        sma200=None,
        rsi14=None,
        source="FRED + Yahoo chart",
        fetched_at=datetime.now(timezone.utc),
        error_message=str(error),
    )


class PublicMetaStrategyProvider:
    def __init__(self, *, timeout_seconds: float = 6.0, opener=urlopen):
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def _read(self, url: str) -> bytes:
        request = Request(url, headers=HTTP_HEADERS)
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                return response.read()
        except Exception as exc:
            raise MetaStrategyError(f"외부 지표 조회 실패: {exc}") from exc

    def get_qqq_history(self) -> list[DatedValue]:
        try:
            payload = json.loads(self._read(QQQ_HISTORY_URL).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MetaStrategyError("Yahoo QQQ JSON을 읽을 수 없습니다.") from exc
        return parse_yahoo_qqq_history(payload)

    def get_liquidity_series(self) -> dict[str, list[DatedValue]]:
        start_date = (date.today() - timedelta(days=3653)).isoformat()
        return parse_fred_liquidity_csv(self._read(FRED_LIQUIDITY_URL.format(start_date=quote(start_date))))


def fetch_meta_strategy(provider: MetaStrategyProvider | None = None) -> MetaStrategyResult:
    active_provider = provider or PublicMetaStrategyProvider()
    try:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="meta-strategy") as executor:
            qqq_future = executor.submit(active_provider.get_qqq_history)
            liquidity_future = executor.submit(active_provider.get_liquidity_series)
            qqq_points = qqq_future.result()
            liquidity_series = liquidity_future.result()
        return build_meta_strategy_result(qqq_points, liquidity_series)
    except MetaStrategyInsufficientData as exc:
        return unavailable_meta_strategy_result(exc, status="insufficient")
    except Exception as exc:
        return unavailable_meta_strategy_result(exc, status="failed")


def retain_previous_meta_strategy_result(
    previous: MetaStrategyResult | None,
    current: MetaStrategyResult,
) -> MetaStrategyResult:
    if current.ok or previous is None or previous.applied_ticker is None:
        return current
    return replace(
        previous,
        status="previous",
        fetched_at=current.fetched_at,
        error_message=current.error_message,
    )
