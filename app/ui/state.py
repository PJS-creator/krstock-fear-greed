from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum


class AppDataState(StrEnum):
    NO_DATA = "NO_DATA"
    SAMPLE_MODE = "SAMPLE_MODE"
    PARTIAL_DATA = "PARTIAL_DATA"
    READY = "READY"
    ERROR_STATE = "ERROR_STATE"


def _has_rows(rows: Iterable[object] | None) -> bool:
    if rows is None:
        return False
    try:
        return any(True for _ in rows)
    except TypeError:
        return False


def _positive_number(value: object) -> bool:
    try:
        return float(value or 0.0) > 0
    except (TypeError, ValueError):
        return False


def get_app_data_state(
    *,
    holdings: Iterable[Mapping[str, object]] | None = None,
    transactions: Iterable[Mapping[str, object]] | None = None,
    cash_ledger: Iterable[Mapping[str, object]] | None = None,
    snapshots: Iterable[object] | None = None,
    prices: Iterable[object] | None = None,
    fx_rate: object | None = None,
    sample_mode: bool = False,
    error: object | None = None,
) -> AppDataState:
    if error is not None:
        return AppDataState.ERROR_STATE
    if sample_mode:
        return AppDataState.SAMPLE_MODE

    holdings_list = list(holdings or [])
    transactions_list = list(transactions or [])
    cash_ledger_list = list(cash_ledger or [])
    has_holdings = bool(holdings_list)
    has_transactions = bool(transactions_list)
    has_cash_ledger = bool(cash_ledger_list)
    has_snapshots = _has_rows(snapshots)
    has_prices = _has_rows(prices) or any(row.get("current_price") not in (None, "") for row in holdings_list)
    has_fx = _positive_number(fx_rate)

    if not any((has_holdings, has_transactions, has_cash_ledger, has_snapshots)):
        return AppDataState.NO_DATA
    if has_holdings and has_prices and has_fx:
        return AppDataState.READY
    if has_transactions and has_holdings and has_fx:
        return AppDataState.READY
    return AppDataState.PARTIAL_DATA
