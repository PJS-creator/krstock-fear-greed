from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import io
import json
import time
from typing import Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from portfolio.meta_strategy import DatedValue, MetaStrategyError


TIINGO_DAILY_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
HY_OAS_ARCHIVE_URL = (
    "https://web.archive.org/web/20251104204105id_/"
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
)
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; krstock-fear-greed-meta-strategy/1.0; "
        "+https://github.com/PJS-creator/krstock-fear-greed)"
    ),
    "Accept": "application/json,text/csv,*/*",
}
FRED_LIQUIDITY_SERIES_IDS = ("WALCL", "WDTGAL", "RRPONTSYD")
FRED_ROUTER_SERIES_IDS = ("VIXCLS", "BAMLH0A0HYM2", "DFII10", "DTWEXBGS")


@dataclass(frozen=True)
class RawSource:
    name: str
    url: str
    content: bytes
    fetched_at: datetime

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class OfficialSourceBundle:
    prices: Mapping[str, list[DatedValue]]
    fred_series: Mapping[str, list[DatedValue]]
    raw_sources: tuple[RawSource, ...]
    source_metadata: Mapping[str, object]


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _parse_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_tiingo_adjusted_prices(payload: bytes | str) -> list[DatedValue]:
    try:
        decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        rows = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetaStrategyError("Tiingo JSON을 읽을 수 없습니다.") from exc
    if not isinstance(rows, list):
        raise MetaStrategyError("Tiingo 일봉 응답이 배열이 아닙니다.")
    points: dict[date, DatedValue] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        as_of_date = _parse_iso_date(row.get("date"))
        adjusted_close = _finite(row.get("adjClose"))
        if as_of_date is None or adjusted_close is None:
            continue
        points[as_of_date] = DatedValue(as_of_date, adjusted_close)
    if not points:
        raise MetaStrategyError("Tiingo 응답에 유효한 조정종가가 없습니다.")
    return [points[key] for key in sorted(points)]


def parse_fred_series_csv(payload: bytes | str) -> dict[str, list[DatedValue]]:
    try:
        decoded = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    except UnicodeDecodeError as exc:
        raise MetaStrategyError("FRED CSV 인코딩을 읽을 수 없습니다.") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise MetaStrategyError("FRED CSV 헤더가 없습니다.")
    date_field = next(
        (field for field in reader.fieldnames if field.strip().lower() in {"date", "observation_date"}),
        None,
    )
    if date_field is None:
        raise MetaStrategyError("FRED CSV에 날짜 열이 없습니다.")
    series_names = [field for field in reader.fieldnames if field != date_field]
    parsed: dict[str, dict[date, DatedValue]] = {name: {} for name in series_names}
    for row in reader:
        as_of_date = _parse_iso_date(row.get(date_field))
        if as_of_date is None:
            continue
        for name in series_names:
            value = _finite(row.get(name))
            if value is not None:
                parsed[name][as_of_date] = DatedValue(as_of_date, value)
    return {
        name: [dated[key] for key in sorted(dated)]
        for name, dated in parsed.items()
        if dated
    }


def merge_series(
    historical: list[DatedValue],
    current: list[DatedValue],
) -> list[DatedValue]:
    merged = {point.as_of_date: point for point in historical}
    merged.update({point.as_of_date: point for point in current})
    return [merged[key] for key in sorted(merged)]


class OfficialMetaStrategySourceClient:
    def __init__(
        self,
        *,
        tiingo_token: str,
        timeout_seconds: float = 20.0,
        opener: Callable[..., object] = urlopen,
    ):
        token = str(tiingo_token or "").strip()
        if not token:
            raise MetaStrategyError("TIINGO_API_TOKEN이 설정되지 않았습니다.")
        self._tiingo_token = token
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def _read(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        attempts: int = 3,
    ) -> RawSource:
        request_headers = dict(DEFAULT_HEADERS)
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers)
        last_error: Exception | None = None
        content: bytes | None = None
        for attempt in range(max(1, attempts)):
            try:
                with self._opener(request, timeout=self._timeout_seconds) as response:
                    content = response.read()
                break
            except Exception as exc:
                last_error = exc
                if attempt < attempts - 1:
                    time.sleep(1.5 * (attempt + 1))
        if content is None:
            raise MetaStrategyError(f"공식 원자료 조회 실패: {url} ({last_error})") from last_error
        return RawSource(
            name="",
            url=url,
            content=content,
            fetched_at=datetime.now(timezone.utc),
        )

    def fetch_tiingo(
        self,
        symbol: str,
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[list[DatedValue], RawSource]:
        query = urlencode(
            {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "format": "json",
                "resampleFreq": "daily",
            }
        )
        url = f"{TIINGO_DAILY_URL.format(symbol=symbol)}?{query}"
        source = self._read(
            url,
            headers={"Authorization": f"Token {self._tiingo_token}"},
        )
        source = RawSource(
            name=f"tiingo_{symbol.lower()}_adjusted",
            url=source.url,
            content=source.content,
            fetched_at=source.fetched_at,
        )
        return parse_tiingo_adjusted_prices(source.content), source

    def fetch_fred_group(
        self,
        *,
        series_ids: tuple[str, ...],
        source_name: str,
        start_date: date,
        end_date: date,
    ) -> tuple[dict[str, list[DatedValue]], tuple[RawSource, ...]]:
        def fetch_one(series_id: str) -> tuple[str, list[DatedValue], RawSource]:
            query = urlencode(
                {
                    "id": series_id,
                    "cosd": start_date.isoformat(),
                    "coed": end_date.isoformat(),
                }
            )
            source = self._read(f"{FRED_GRAPH_URL}?{query}")
            named = RawSource(
                name=f"{source_name}_{series_id.lower()}",
                url=source.url,
                content=source.content,
                fetched_at=source.fetched_at,
            )
            parsed = parse_fred_series_csv(named.content)
            return series_id, list(parsed.get(series_id) or []), named

        parsed_group: dict[str, list[DatedValue]] = {}
        raw_sources: list[RawSource] = []
        for series_id in series_ids:
            resolved_id, points, source = fetch_one(series_id)
            if points:
                parsed_group[resolved_id] = points
            raw_sources.append(source)
        return parsed_group, tuple(raw_sources)

    def fetch_fred(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[dict[str, list[DatedValue]], tuple[RawSource, ...]]:
        liquidity, liquidity_sources = self.fetch_fred_group(
            series_ids=FRED_LIQUIDITY_SERIES_IDS,
            source_name="fred_liquidity",
            start_date=start_date,
            end_date=end_date,
        )
        router, router_sources = self.fetch_fred_group(
            series_ids=FRED_ROUTER_SERIES_IDS,
            source_name="fred_router_current",
            start_date=max(start_date, date(2005, 3, 28)),
            end_date=end_date,
        )
        merged = dict(liquidity)
        merged.update(router)
        return merged, (*liquidity_sources, *router_sources)

    def fetch_hy_oas_archive(self) -> tuple[list[DatedValue], RawSource] | None:
        try:
            source = self._read(HY_OAS_ARCHIVE_URL, attempts=1)
            parsed = parse_fred_series_csv(source.content)
            points = parsed.get("BAMLH0A0HYM2") or []
            if not points:
                return None
            return (
                points,
                RawSource(
                    name="fred_hy_oas_archive_20251104204105",
                    url=source.url,
                    content=source.content,
                    fetched_at=source.fetched_at,
                ),
            )
        except MetaStrategyError:
            return None

    def fetch_bundle(
        self,
        *,
        price_start_date: date,
        fred_start_date: date,
        end_date: date,
    ) -> OfficialSourceBundle:
        qqq, qqq_source = self.fetch_tiingo("QQQ", start_date=price_start_date, end_date=end_date)
        gld, gld_source = self.fetch_tiingo("GLD", start_date=price_start_date, end_date=end_date)
        fred, fred_sources = self.fetch_fred(start_date=fred_start_date, end_date=end_date)
        raw_sources = [qqq_source, gld_source, *fred_sources]
        archive = self.fetch_hy_oas_archive()
        if archive is not None:
            historical_hy, archive_source = archive
            fred["BAMLH0A0HYM2"] = merge_series(
                historical_hy,
                list(fred.get("BAMLH0A0HYM2") or []),
            )
            raw_sources.append(archive_source)
            hy_source = "Internet Archive 2025-11-04 + FRED current wins"
        else:
            hy_source = "FRED current history (archive unavailable)"
        metadata = {
            "price_provider": "Tiingo",
            "price_adjustment": "adjusted",
            "liquidity_provider": "FRED",
            "hy_oas_source": hy_source,
            "source_hashes": {source.name: source.sha256 for source in raw_sources},
            "source_fetched_at_utc": {
                source.name: source.fetched_at.isoformat() for source in raw_sources
            },
        }
        return OfficialSourceBundle(
            prices={"QQQ": qqq, "GLD": gld},
            fred_series=fred,
            raw_sources=tuple(raw_sources),
            source_metadata=metadata,
        )
