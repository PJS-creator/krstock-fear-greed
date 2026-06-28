from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict
from datetime import date
from typing import Any

from .models import (
    CashSnapshotRow,
    DailyValuationRow,
    HistoricalPriceProviderError,
    HistoricalReconstructionError,
    HoldingSnapshotRow,
    HoldingValuationRow,
    ReconstructionResult,
    ReconstructionWarning,
)
from .normalization import normalize_cash_snapshots, normalize_holding_snapshots, parse_date
from .price_provider import HistoricalPriceProvider


PriceMap = dict[date, float]
PriceMaps = dict[tuple[str, str], PriceMap]


def _group_holdings_by_date(rows: Iterable[HoldingSnapshotRow]) -> dict[date, list[HoldingSnapshotRow]]:
    grouped: dict[date, list[HoldingSnapshotRow]] = defaultdict(list)
    for row in rows:
        grouped[row.as_of_date].append(row)
    return dict(grouped)


def _latest_date_on_or_before(candidates: list[date], current: date) -> date | None:
    latest = None
    for candidate in candidates:
        if candidate <= current:
            latest = candidate
        else:
            break
    return latest


def _next_date_on_or_after(candidates: list[date], current: date) -> date | None:
    for candidate in candidates:
        if candidate >= current:
            return candidate
    return None


def _date_range_from_inputs(
    holdings: list[HoldingSnapshotRow],
    *,
    start_date: date | str | None,
    end_date: date | str | None,
) -> tuple[date, date]:
    first_snapshot = min(row.as_of_date for row in holdings)
    start = parse_date(start_date, field_name="start_date") if start_date is not None else first_snapshot
    end = parse_date(end_date, field_name="end_date") if end_date is not None else date.today()
    if end < start:
        raise HistoricalReconstructionError("end_date must be on or after start_date")
    return start, end


def fetch_price_maps(
    holdings: list[HoldingSnapshotRow],
    provider: HistoricalPriceProvider,
    *,
    start_date: date,
    end_date: date,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[PriceMaps, list[str], list[ReconstructionWarning]]:
    tickers = sorted({(row.market, row.ticker) for row in holdings})
    price_maps: PriceMaps = {}
    failed: list[str] = []
    warnings: list[ReconstructionWarning] = []
    for index, (market, ticker) in enumerate(tickers, start=1):
        if on_progress is not None:
            on_progress(index, len(tickers), f"{market}/{ticker}")
        try:
            price_maps[(market, ticker)] = provider.get_close_prices(
                market=market,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
            )
        except HistoricalPriceProviderError as exc:
            failed.append(f"{market}/{ticker}")
            price_maps[(market, ticker)] = {}
            warnings.append(ReconstructionWarning("price_fetch_failed", str(exc), ticker=ticker))
    return price_maps, failed, warnings


def _trading_dates(price_maps: PriceMaps, start_date: date, end_date: date) -> list[date]:
    dates = {
        price_date
        for price_map in price_maps.values()
        for price_date in price_map
        if start_date <= price_date <= end_date
    }
    return sorted(dates)


def _snapshot_application_warnings(snapshot_dates: list[date], trading_dates: list[date]) -> list[ReconstructionWarning]:
    warnings: list[ReconstructionWarning] = []
    trading_set = set(trading_dates)
    for snapshot_date in snapshot_dates:
        if snapshot_date in trading_set:
            continue
        next_trading_date = _next_date_on_or_after(trading_dates, snapshot_date)
        if next_trading_date is not None:
            warnings.append(
                ReconstructionWarning(
                    "snapshot_next_trading_day",
                    f"{snapshot_date.isoformat()} 보유현황은 비거래일 입력으로 {next_trading_date.isoformat()}에 적용됩니다.",
                    date=snapshot_date,
                )
            )
    return warnings


def _cash_for_date(cash_rows: list[CashSnapshotRow], current: date) -> CashSnapshotRow:
    selected: CashSnapshotRow | None = None
    for row in cash_rows:
        if row.as_of_date <= current:
            selected = row
        else:
            break
    return selected or CashSnapshotRow(as_of_date=current)


def _fx_for_date(
    *,
    current: date,
    cash_row: CashSnapshotRow,
    fx_rates: Mapping[date, float],
    current_usd_krw: float | None,
    needs_usd_rate: bool,
) -> float:
    if cash_row.usd_krw is not None:
        return cash_row.usd_krw
    if current in fx_rates:
        return float(fx_rates[current])
    if current_usd_krw is not None and current_usd_krw > 0:
        return float(current_usd_krw)
    if needs_usd_rate:
        raise HistoricalReconstructionError("USD/KRW is required for USD holdings or cash")
    return 1.0


def reconstruct_historical_holdings(
    holding_rows: Iterable[HoldingSnapshotRow | Mapping[str, Any]],
    cash_rows: Iterable[CashSnapshotRow | Mapping[str, Any]],
    provider: HistoricalPriceProvider,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    current_usd_krw: float | None = None,
    use_forward_fill_prices: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> ReconstructionResult:
    raw_holding_rows = list(holding_rows)
    raw_cash_rows = list(cash_rows)
    holdings = (
        raw_holding_rows
        if all(isinstance(row, HoldingSnapshotRow) for row in raw_holding_rows)
        else normalize_holding_snapshots(raw_holding_rows)  # type: ignore[arg-type]
    )
    cash_snapshots = (
        raw_cash_rows
        if all(isinstance(row, CashSnapshotRow) for row in raw_cash_rows)
        else normalize_cash_snapshots(raw_cash_rows)  # type: ignore[arg-type]
    )
    start, end = _date_range_from_inputs(holdings, start_date=start_date, end_date=end_date)
    price_maps, failed_tickers, warnings = fetch_price_maps(holdings, provider, start_date=start, end_date=end, on_progress=on_progress)
    try:
        fx_rates = provider.get_usd_krw_rates(start_date=start, end_date=end)
    except HistoricalPriceProviderError as exc:
        fx_rates = {}
        warnings.append(ReconstructionWarning("fx_fetch_failed", str(exc)))

    trading_dates = _trading_dates(price_maps, start, end)
    if not trading_dates:
        warnings.append(ReconstructionWarning("no_trading_dates", "평가 가능한 거래일 가격 데이터가 없습니다."))
        return ReconstructionResult([], [], warnings, failed_tickers, sorted({row.as_of_date for row in holdings}))

    grouped = _group_holdings_by_date(holdings)
    snapshot_dates = sorted(grouped)
    cash_snapshots = sorted(cash_snapshots, key=lambda row: row.as_of_date)
    warnings.extend(_snapshot_application_warnings(snapshot_dates, trading_dates))
    if cash_snapshots:
        warnings.extend(_snapshot_application_warnings([row.as_of_date for row in cash_snapshots], trading_dates))

    daily_rows: list[DailyValuationRow] = []
    holding_valuations: list[HoldingValuationRow] = []
    last_known_price: dict[tuple[str, str], tuple[float, date]] = {}

    for current in trading_dates:
        snapshot_date = _latest_date_on_or_before(snapshot_dates, current)
        if snapshot_date is None:
            continue
        active_holdings = grouped[snapshot_date]
        cash_row = _cash_for_date(cash_snapshots, current)
        needs_usd_rate = cash_row.cash_usd > 0 or any(row.currency == "USD" for row in active_holdings)
        usd_krw = _fx_for_date(
            current=current,
            cash_row=cash_row,
            fx_rates=fx_rates,
            current_usd_krw=current_usd_krw,
            needs_usd_rate=needs_usd_rate,
        )
        cash_total = cash_row.cash_krw + cash_row.cash_usd * usd_krw
        position_total = 0.0
        priced_count = 0
        missing_count = 0
        for holding in active_holdings:
            key = (holding.market, holding.ticker)
            price_map = price_maps.get(key, {})
            price = price_map.get(current)
            status = "priced"
            if price is None and use_forward_fill_prices:
                previous = last_known_price.get(key)
                if previous is not None:
                    price = previous[0]
                    status = "forward_filled"
            if price is not None and status == "priced":
                last_known_price[key] = (price, current)

            if price is None:
                missing_count += 1
                holding_valuations.append(
                    HoldingValuationRow(
                        date=current,
                        market=holding.market,
                        ticker=holding.ticker,
                        display_name=holding.display_name,
                        quantity=holding.quantity,
                        close_price=None,
                        currency=holding.currency,
                        fx_rate=usd_krw if holding.currency == "USD" else 1.0,
                        market_value_krw=None,
                        price_status="missing_price",
                        applied_snapshot_date=snapshot_date,
                    )
                )
                continue
            fx_rate = usd_krw if holding.currency == "USD" else 1.0
            value_krw = holding.quantity * price * fx_rate
            position_total += value_krw
            priced_count += 1
            holding_valuations.append(
                HoldingValuationRow(
                    date=current,
                    market=holding.market,
                    ticker=holding.ticker,
                    display_name=holding.display_name,
                    quantity=holding.quantity,
                    close_price=price,
                    currency=holding.currency,
                    fx_rate=fx_rate,
                    market_value_krw=value_krw,
                    price_status=status,
                    applied_snapshot_date=snapshot_date,
                )
            )
        daily_rows.append(
            DailyValuationRow(
                date=current,
                total_value_krw=position_total + cash_total,
                position_value_krw=position_total,
                cash_total_krw=cash_total,
                cash_krw=cash_row.cash_krw,
                cash_usd=cash_row.cash_usd,
                usd_krw=usd_krw,
                holdings_count=len(active_holdings),
                priced_count=priced_count,
                missing_price_count=missing_count,
                applied_snapshot_date=snapshot_date,
            )
        )
    return ReconstructionResult(daily_rows, holding_valuations, warnings, failed_tickers, snapshot_dates)


def daily_rows_as_dicts(rows: Iterable[DailyValuationRow]) -> list[dict[str, object]]:
    return [{**asdict(row), "date": row.date.isoformat(), "applied_snapshot_date": row.applied_snapshot_date.isoformat()} for row in rows]


def holding_rows_as_dicts(rows: Iterable[HoldingValuationRow]) -> list[dict[str, object]]:
    return [
        {**asdict(row), "date": row.date.isoformat(), "applied_snapshot_date": row.applied_snapshot_date.isoformat()}
        for row in rows
    ]


def build_snapshot_marker_rows(result: ReconstructionResult) -> list[dict[str, object]]:
    evaluated_dates = [row.date for row in result.daily_rows]
    return [
        {"snapshot_date": snapshot_date.isoformat(), "applied_date": (_next_date_on_or_after(evaluated_dates, snapshot_date) or snapshot_date).isoformat()}
        for snapshot_date in result.snapshot_dates
    ]


def build_ticker_value_series(result: ReconstructionResult, *, top_n: int = 8) -> list[dict[str, object]]:
    totals: dict[str, float] = defaultdict(float)
    for row in result.holding_rows:
        if row.market_value_krw is not None:
            totals[row.ticker] += row.market_value_krw
    top = {ticker for ticker, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:top_n]}
    series: dict[tuple[date, str], float] = defaultdict(float)
    labels: dict[str, str] = {}
    for row in result.holding_rows:
        if row.market_value_krw is None:
            continue
        ticker = row.ticker if row.ticker in top else "기타"
        labels[ticker] = row.display_name if ticker != "기타" else "상위 외 종목"
        series[(row.date, ticker)] += row.market_value_krw
    return [
        {"date": current.isoformat(), "ticker": ticker, "display_name": labels[ticker], "market_value_krw": value}
        for (current, ticker), value in sorted(series.items())
    ]
