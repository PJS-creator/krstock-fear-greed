from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from portfolio.chart_analysis import AnalysisInstrument
from portfolio.chart_analysis_data import (
    fetch_yfinance_daily_histories,
    holdings_to_analysis_instruments,
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
