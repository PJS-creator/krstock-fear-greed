from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from portfolio.chart_analysis import AnalysisInstrument, analyze_daily_history, validate_daily_bars
from portfolio.chart_analysis_data import (
    KIS_DAILY_PROVIDER,
    fetch_daily_histories,
    fetch_yfinance_daily_histories,
    holdings_to_analysis_instruments,
    standardize_kis_daily_rows,
    standardize_yfinance_daily_frame,
)


def _source_frame(index: pd.DatetimeIndex, close: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.01,
            "Low": close * 0.98,
            "Close": close,
            "Volume": np.full(len(index), 1_000_000.0),
            "Stock Splits": np.zeros(len(index)),
        },
        index=index,
    )


def _kis_rows(market: str, index: pd.DatetimeIndex) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for offset, timestamp in enumerate(index):
        close = 100.0 + offset
        if market == "KR":
            rows.append(
                {
                    "stck_bsop_date": timestamp.strftime("%Y%m%d"),
                    "stck_oprc": str(close - 1.0),
                    "stck_hgpr": str(close + 2.0),
                    "stck_lwpr": str(close - 2.0),
                    "stck_clpr": str(close),
                    "acml_vol": str(1_000 + offset),
                    "acml_tr_pbmn": str(100_000_000 + offset),
                }
            )
        else:
            rows.append(
                {
                    "xymd": timestamp.strftime("%Y%m%d"),
                    "open": str(close - 1.0),
                    "high": str(close + 2.0),
                    "low": str(close - 2.0),
                    "clos": str(close),
                    "tvol": str(1_000 + offset),
                    "tamt": str(1_000_000 + offset),
                }
            )
    return rows


def test_holdings_conversion_keeps_positive_supported_positions_and_deduplicates():
    rows = [
        {"market": "KR", "ticker": "5930", "display_name": "삼성전자", "quantity": 10},
        {"market": "KR", "ticker": "005930", "display_name": "중복", "quantity": 2},
        {"market": "US", "ticker": "qure", "display_name": "QURE", "quantity": 1},
        {"market": "US", "ticker": "NONE", "display_name": "없음", "quantity": 0},
        {"market": "JP", "ticker": "7203", "display_name": "미지원", "quantity": 1},
    ]

    instruments = holdings_to_analysis_instruments(rows)

    assert [(item.market, item.symbol, item.display_name) for item in instruments] == [
        ("KR", "005930", "삼성전자"),
        ("US", "QURE", "QURE"),
    ]


def test_split_adjustment_uses_post_split_price_basis_and_inverse_volume():
    index = pd.date_range("2020-01-02", periods=4, freq="D")
    frame = _source_frame(index, np.array([400.0, 420.0, 105.0, 110.0]))
    frame["Stock Splits"] = [0.0, 0.0, 4.0, 0.0]
    instrument = AnalysisInstrument(market="US", symbol="TEST", display_name="테스트")

    standardized, mode, warnings = standardize_yfinance_daily_frame(
        frame,
        instrument=instrument,
        source_symbol="TEST",
        now=datetime(2020, 1, 10, tzinfo=timezone.utc),
    )

    assert mode == "SPLIT_ADJUSTED_OHLCV"
    assert warnings == ()
    assert standardized["close"].tolist() == [100.0, 105.0, 105.0, 110.0]
    assert standardized["volume"].tolist()[:2] == [4_000_000.0, 4_000_000.0]


def test_incomplete_current_us_session_is_excluded():
    index = pd.DatetimeIndex(["2026-08-05", "2026-08-06"])
    frame = _source_frame(index, np.array([100.0, 101.0]))
    instrument = AnalysisInstrument(market="US", symbol="TEST", display_name="테스트")

    standardized, _, _ = standardize_yfinance_daily_frame(
        frame,
        instrument=instrument,
        source_symbol="TEST",
        now=datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc),
    )

    assert standardized["timestamp"].dt.date.astype(str).tolist() == ["2026-08-05"]


def test_kis_domestic_rows_preserve_actual_traded_value():
    index = pd.bdate_range("2024-01-02", periods=310)
    instrument = AnalysisInstrument(market="KR", symbol="005930", display_name="삼성전자")

    standardized = standardize_kis_daily_rows(
        _kis_rows("KR", index),
        instrument=instrument,
        now=datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc),
    )
    validated, warnings = validate_daily_bars(standardized)

    assert len(validated) == 310
    assert validated["traded_value"].iloc[-1] == 100_000_309
    assert "APPROXIMATED_TRADED_VALUE" not in warnings


def test_kis_overseas_rows_preserve_actual_traded_value():
    index = pd.bdate_range("2024-01-02", periods=310)
    instrument = AnalysisInstrument(market="US", symbol="QURE", display_name="QURE")

    standardized = standardize_kis_daily_rows(
        _kis_rows("US", index),
        instrument=instrument,
        now=datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc),
    )
    result = analyze_daily_history(
        fetch_daily_histories(
            (instrument,),
            kis_provider=_FakeKisHistoryProvider({instrument.key: _kis_rows("US", index)}),
            now=datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc),
        )[0]
    )

    assert standardized["traded_value"].iloc[-1] == 1_000_309
    assert result.provider == KIS_DAILY_PROVIDER
    assert result.quality_status == "PASS"
    assert "APPROXIMATED_TRADED_VALUE" not in result.warnings


class _FakeKisHistoryProvider:
    def __init__(self, rows_by_key: dict[str, list[dict[str, str]]]) -> None:
        self.rows_by_key = rows_by_key
        self.calls: list[str] = []

    def get_daily_history_rows(self, market, symbol, *, max_rows=500, end_date=None):
        key = f"{market}:{symbol}"
        self.calls.append(key)
        if key not in self.rows_by_key:
            raise RuntimeError("KIS unavailable")
        return self.rows_by_key[key][-max_rows:], f"{symbol}@KIS"


def test_kis_first_fetch_falls_back_only_for_failed_symbols_and_preserves_order():
    index = pd.bdate_range("2024-01-02", periods=310)
    kis_instrument = AnalysisInstrument(market="US", symbol="QURE", display_name="QURE")
    fallback_instrument = AnalysisInstrument(market="US", symbol="AAPL", display_name="Apple")
    provider = _FakeKisHistoryProvider({kis_instrument.key: _kis_rows("US", index)})
    fallback = _source_frame(index, np.linspace(100.0, 150.0, len(index)))
    loader_calls: list[dict[str, object]] = []

    def loader(**kwargs):
        loader_calls.append(kwargs)
        return fallback

    histories = fetch_daily_histories(
        (kis_instrument, fallback_instrument),
        kis_provider=provider,
        loader=loader,
        now=datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc),
    )

    assert provider.calls == [kis_instrument.key, fallback_instrument.key]
    assert len(loader_calls) == 1
    assert loader_calls[0]["tickers"] == ["AAPL"]
    assert [history.instrument.key for history in histories] == [kis_instrument.key, fallback_instrument.key]
    assert histories[0].provider == KIS_DAILY_PROVIDER
    assert histories[0].warnings == ()
    assert histories[1].provider == "Yahoo Finance (yfinance)"
    assert "KIS_DAILY_FALLBACK" in histories[1].warnings


def test_batch_fetch_selects_available_korean_exchange_candidate():
    index = pd.bdate_range("2024-01-02", periods=310)
    aapl = _source_frame(index, np.linspace(100.0, 150.0, len(index)))
    samsung = _source_frame(index, np.linspace(60_000.0, 90_000.0, len(index)))
    raw = pd.concat({"AAPL": aapl, "005930.KS": samsung}, axis=1)
    calls: list[dict[str, object]] = []

    def loader(**kwargs):
        calls.append(kwargs)
        return raw

    histories = fetch_yfinance_daily_histories(
        (
            AnalysisInstrument(market="US", symbol="AAPL", display_name="Apple"),
            AnalysisInstrument(market="KR", symbol="005930", display_name="삼성전자"),
        ),
        loader=loader,
        now=datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc),
    )

    assert len(calls) == 1
    assert set(calls[0]["tickers"]) == {"AAPL", "005930.KS", "005930.KQ"}
    assert [history.source_symbol for history in histories] == ["AAPL", "005930.KS"]
    assert all(history.frame is not None and len(history.frame) == 310 for history in histories)


def test_invalid_korean_yahoo_ohlc_uses_validated_finance_datareader_fallback():
    index = pd.bdate_range("2024-01-02", periods=310)
    invalid = _source_frame(index, np.linspace(60_000.0, 90_000.0, len(index)))
    invalid.loc[index[20], "Low"] = invalid.loc[index[20], "Close"] + 100.0
    raw = pd.concat({"005930.KS": invalid}, axis=1)
    fallback = _source_frame(index, np.linspace(60_000.0, 90_000.0, len(index))).drop(columns=["Stock Splits"])

    history = fetch_yfinance_daily_histories(
        (AnalysisInstrument(market="KR", symbol="005930", display_name="삼성전자"),),
        loader=lambda **_: raw,
        korea_fallback_reader=lambda symbol, start, end: fallback,
        now=datetime(2026, 8, 6, 23, 0, tzinfo=timezone.utc),
    )[0]

    assert history.error is None
    assert history.provider == "FinanceDataReader"
    assert history.source_symbol == "005930"
    assert history.adjustment_mode == "PROVIDER_OHLCV_UNVERIFIED"
    assert "PROVIDER_ADJUSTMENT_UNVERIFIED" in history.warnings
