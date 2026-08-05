from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from portfolio.chart_analysis import (
    AnalysisInstrument,
    ChartAnalysisError,
    DailyHistoryInput,
    RECOMMENDED_INPUT_ROWS,
    validate_daily_bars,
)


YFINANCE_PROVIDER = "Yahoo Finance (yfinance)"
FINANCE_DATAREADER_PROVIDER = "FinanceDataReader"
HISTORY_PERIOD = "3y"
HISTORY_INTERVAL = "1d"
_MARKET_TIMEZONES = {
    "KR": ZoneInfo("Asia/Seoul"),
    "US": ZoneInfo("America/New_York"),
}
_REGULAR_SESSION_FINALIZED_AT = {
    "KR": time(15, 45),
    "US": time(16, 15),
}


def holdings_to_analysis_instruments(rows: Iterable[Mapping[str, object]]) -> tuple[AnalysisInstrument, ...]:
    instruments: list[AnalysisInstrument] = []
    seen: set[str] = set()
    for row in rows:
        market = str(row.get("market") or "").strip().upper()
        if market not in {"KR", "US"}:
            continue
        try:
            quantity = float(row.get("quantity") or 0.0)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(quantity) or quantity <= 0:
            continue
        symbol = _normalize_portfolio_symbol(row.get("ticker"), market)
        if not symbol:
            continue
        key = f"{market}:{symbol}"
        if key in seen:
            continue
        seen.add(key)
        display_name = str(row.get("display_name") or row.get("name") or symbol).strip() or symbol
        instruments.append(AnalysisInstrument(market=market, symbol=symbol, display_name=display_name))
    return tuple(instruments)


def _normalize_portfolio_symbol(value: object, market: str) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        return ""
    if market == "KR":
        symbol = symbol.removesuffix(".KS").removesuffix(".KQ")
        return symbol.zfill(6) if symbol.isdigit() and len(symbol) <= 6 else symbol
    return symbol


def yahoo_symbol_candidates(instrument: AnalysisInstrument) -> tuple[str, ...]:
    if instrument.market == "KR":
        return (f"{instrument.symbol}.KS", f"{instrument.symbol}.KQ")
    return (instrument.symbol,)


def fetch_yfinance_daily_histories(
    instruments: Iterable[AnalysisInstrument],
    *,
    loader: Callable[..., pd.DataFrame] | None = None,
    korea_fallback_reader: Callable[..., pd.DataFrame] | None = None,
    now: datetime | None = None,
    timeout_seconds: float = 12.0,
) -> tuple[DailyHistoryInput, ...]:
    requested = tuple(instruments)
    if not requested:
        return ()
    all_symbols = tuple(
        dict.fromkeys(symbol for instrument in requested for symbol in yahoo_symbol_candidates(instrument))
    )
    if loader is None:
        import yfinance as yf

        loader = yf.download
    try:
        raw = loader(
            tickers=list(all_symbols),
            period=HISTORY_PERIOD,
            interval=HISTORY_INTERVAL,
            auto_adjust=False,
            actions=True,
            group_by="ticker",
            threads=True,
            progress=False,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        message = f"일봉 배치 조회 실패: {type(exc).__name__}: {exc}"
        return tuple(
            DailyHistoryInput(instrument=instrument, frame=None, provider=YFINANCE_PROVIDER, error=message)
            for instrument in requested
        )

    results: list[DailyHistoryInput] = []
    for instrument in requested:
        candidates: list[DailyHistoryInput] = []
        candidate_errors: list[str] = []
        for source_symbol in yahoo_symbol_candidates(instrument):
            source_frame = _extract_symbol_frame(raw, source_symbol, single_symbol=len(all_symbols) == 1)
            if source_frame is None or source_frame.empty:
                candidate_errors.append(f"{source_symbol}: 데이터 없음")
                continue
            try:
                frame, adjustment_mode, warnings = standardize_yfinance_daily_frame(
                    source_frame,
                    instrument=instrument,
                    source_symbol=source_symbol,
                    now=now,
                )
                validate_daily_bars(frame)
            except (ChartAnalysisError, TypeError, ValueError) as exc:
                candidate_errors.append(f"{source_symbol}: {exc}")
                continue
            if frame.empty:
                candidate_errors.append(f"{source_symbol}: 완료 일봉 없음")
                continue
            candidates.append(
                DailyHistoryInput(
                    instrument=instrument,
                    frame=frame,
                    provider=YFINANCE_PROVIDER,
                    adjustment_mode=adjustment_mode,
                    source_symbol=source_symbol,
                    warnings=warnings,
                )
            )
        if not candidates and instrument.market == "KR":
            fallback, fallback_error = _fetch_finance_datareader_history(
                instrument,
                reader=korea_fallback_reader,
                now=now,
            )
            if fallback is not None:
                candidates.append(fallback)
            elif fallback_error:
                candidate_errors.append(f"FinanceDataReader: {fallback_error}")
        if candidates:
            results.append(max(candidates, key=lambda item: len(item.frame) if item.frame is not None else 0))
        else:
            detail = "; ".join(candidate_errors) or "조회 결과 없음"
            results.append(
                DailyHistoryInput(
                    instrument=instrument,
                    frame=None,
                    provider=YFINANCE_PROVIDER,
                    error=f"{instrument.display_name} 일봉을 확인하지 못했습니다. {detail}",
                )
            )
    return tuple(results)


def _extract_symbol_frame(raw: pd.DataFrame, symbol: str, *, single_symbol: bool) -> pd.DataFrame | None:
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        for level in range(raw.columns.nlevels):
            matching = next(
                (value for value in raw.columns.get_level_values(level).unique() if str(value) == symbol),
                None,
            )
            if matching is not None:
                extracted = raw.xs(matching, axis=1, level=level, drop_level=True).copy()
                if isinstance(extracted.columns, pd.MultiIndex):
                    extracted.columns = [str(column[-1]) for column in extracted.columns]
                return extracted
        return None
    if single_symbol or _has_ohlcv_columns(raw.columns):
        return raw.copy()
    return None


def _has_ohlcv_columns(columns: Iterable[object]) -> bool:
    normalized = {_normalize_column_name(column) for column in columns}
    return {"open", "high", "low", "close", "volume"}.issubset(normalized)


def _normalize_column_name(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_")


def standardize_yfinance_daily_frame(
    frame: pd.DataFrame,
    *,
    instrument: AnalysisInstrument,
    source_symbol: str,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, str, tuple[str, ...]]:
    if frame.empty:
        return pd.DataFrame(), "", ()
    source = frame.copy()
    if isinstance(source.columns, pd.MultiIndex):
        source.columns = [str(column[-1]) for column in source.columns]
    column_by_name = {_normalize_column_name(column): column for column in source.columns}
    missing = [column for column in ("open", "high", "low", "close", "volume") if column not in column_by_name]
    if missing:
        raise ValueError("필수 OHLCV 열 누락: " + ", ".join(missing))
    selected = pd.DataFrame(index=pd.to_datetime(source.index, errors="coerce"))
    for column in ("open", "high", "low", "close", "volume"):
        selected[column] = pd.to_numeric(source[column_by_name[column]], errors="coerce").to_numpy()
    selected = selected[~selected.index.isna()].sort_index(kind="stable")
    selected = selected[~selected.index.duplicated(keep="last")]
    selected = selected.dropna(subset=["open", "high", "low", "close", "volume"], how="all")

    warnings: list[str] = []
    split_column = column_by_name.get("stock_splits")
    if split_column is None:
        adjustment_mode = "RAW_OHLCV"
        warnings.append("SPLIT_EVENTS_UNAVAILABLE")
    else:
        split_values = pd.to_numeric(source[split_column], errors="coerce").fillna(0.0)
        split_values.index = pd.to_datetime(source.index, errors="coerce")
        split_values = split_values[~split_values.index.isna()].sort_index(kind="stable")
        split_values = split_values[~split_values.index.duplicated(keep="last")]
        split_values = split_values.reindex(selected.index).fillna(0.0)
        split_ratios = split_values.where(split_values > 0.0, 1.0)
        future_factor = split_ratios.iloc[::-1].cumprod().iloc[::-1] / split_ratios
        for column in ("open", "high", "low", "close"):
            selected[column] = selected[column] / future_factor
        selected["volume"] = selected["volume"] * future_factor
        adjustment_mode = "SPLIT_ADJUSTED_OHLCV"

    selected = _completed_regular_sessions(selected, market=instrument.market, now=now)
    if len(selected) > RECOMMENDED_INPUT_ROWS:
        selected = selected.tail(RECOMMENDED_INPUT_ROWS)
    selected = selected.reset_index(names="timestamp")
    selected["timestamp"] = pd.to_datetime(selected["timestamp"]).dt.tz_localize(None)
    if selected.empty:
        warnings.append("NO_COMPLETED_SESSION")
    return selected, adjustment_mode, tuple(warnings)


def _completed_regular_sessions(frame: pd.DataFrame, *, market: str, now: datetime | None) -> pd.DataFrame:
    timezone_info = _MARKET_TIMEZONES.get(market, timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(timezone_info)
    session_dates = pd.Index([timestamp.date() for timestamp in frame.index])
    completed = session_dates < local_now.date()
    if local_now.time() >= _REGULAR_SESSION_FINALIZED_AT.get(market, time(23, 59)):
        completed = completed | (session_dates == local_now.date())
    return frame.loc[np.asarray(completed, dtype=bool)].copy()


def _fetch_finance_datareader_history(
    instrument: AnalysisInstrument,
    *,
    reader: Callable[..., pd.DataFrame] | None,
    now: datetime | None,
) -> tuple[DailyHistoryInput | None, str | None]:
    if reader is None:
        try:
            import FinanceDataReader as fdr
        except ImportError:
            return None, "패키지가 설치되어 있지 않습니다."
        reader = fdr.DataReader
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_date = current.astimezone(_MARKET_TIMEZONES["KR"]).date()
    start = (local_date - timedelta(days=3 * 366 + 30)).isoformat()
    end = (local_date + timedelta(days=1)).isoformat()
    try:
        source = reader(instrument.symbol, start, end)
        frame, _, warnings = standardize_yfinance_daily_frame(
            source,
            instrument=instrument,
            source_symbol=instrument.symbol,
            now=now,
        )
        validate_daily_bars(frame)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    warnings = tuple(dict.fromkeys((*warnings, "PROVIDER_ADJUSTMENT_UNVERIFIED")))
    return (
        DailyHistoryInput(
            instrument=instrument,
            frame=frame,
            provider=FINANCE_DATAREADER_PROVIDER,
            adjustment_mode="PROVIDER_OHLCV_UNVERIFIED",
            source_symbol=instrument.symbol,
            warnings=warnings,
        ),
        None,
    )
