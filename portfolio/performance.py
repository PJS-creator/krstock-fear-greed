from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from portfolio.cash_ledger import calculate_cash_balances, normalize_cash_ledger_rows
from portfolio.holdings import normalize_holding_rows
from portfolio.transactions import normalize_transaction_row


EXTERNAL_FLOW_TYPES = {"opening_balance", "deposit", "withdrawal", "manual_adjustment"}
INCOME_TYPES = {"dividend", "interest"}
FEE_TAX_TYPES = {"fee", "tax"}


@dataclass
class _PositionState:
    market: str
    ticker: str
    display_name: str
    currency: str
    quantity: float = 0.0
    cost_local: float = 0.0
    cost_krw_at_entry_fx: float = 0.0
    realized_pnl_krw: float = 0.0
    realized_price_effect_krw: float = 0.0
    realized_fx_effect_krw: float = 0.0
    fees_taxes_krw: float = 0.0
    dividend_interest_krw: float = 0.0
    estimated_fx: bool = False


@dataclass(frozen=True)
class SymbolPerformance:
    market: str
    ticker: str
    display_name: str
    currency: str
    quantity: float
    avg_price: float | None
    current_price: float | None
    realized_pnl_krw: float
    unrealized_pnl_krw: float
    dividend_interest_krw: float
    fees_taxes_krw: float
    total_pnl_krw: float
    price_effect_krw: float
    fx_effect_krw: float
    estimated_fx: bool


@dataclass(frozen=True)
class MonthlyPerformance:
    month: str
    realized_pnl_krw: float
    dividend_interest_krw: float
    fees_taxes_krw: float
    external_flow_krw: float
    buy_amount_krw: float
    sell_amount_krw: float

    @property
    def net_investment_result_krw(self) -> float:
        return self.realized_pnl_krw + self.dividend_interest_krw - self.fees_taxes_krw


@dataclass(frozen=True)
class PerformanceAnalysis:
    total_profit_krw: float
    realized_pnl_krw: float
    unrealized_pnl_krw: float
    dividend_interest_krw: float
    fees_taxes_krw: float
    fx_effect_krw: float
    price_effect_krw: float
    net_deposit_krw: float
    flow_adjusted_asset_change_krw: float | None
    simple_return: float | None
    twr_base_return: float | None
    mwr_irr: float | None
    current_total_value_krw: float | None
    estimated_fx: bool
    rows: list[SymbolPerformance]
    monthly_rows: list[MonthlyPerformance]


def _to_float(value: object, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("value must be finite")
    return number


def _positive_fx_rate(currency: str, row: Mapping[str, Any], usd_krw: float) -> tuple[float, bool]:
    if currency == "KRW":
        return 1.0, False
    raw = row.get("fx_rate_to_krw")
    if raw not in (None, ""):
        rate = _to_float(raw)
        if rate <= 0:
            raise ValueError("fx_rate_to_krw must be positive")
        return rate, False
    return usd_krw, True


def _amount_to_krw(amount: float, currency: str, row: Mapping[str, Any], usd_krw: float) -> tuple[float, bool]:
    rate, estimated = _positive_fx_rate(currency, row, usd_krw)
    return amount * rate, estimated


def _transaction_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(row["occurred_at"]), str(row["market"]), str(row["ticker"]))


def _normalized_transactions_with_fx(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        try:
            transaction = normalize_transaction_row(row)
        except ValueError as exc:
            raise ValueError(f"Transaction row {index}: {exc}") from exc
        for key in ("id", "transaction_id", "linked_transaction_id", "fx_rate_to_krw"):
            if row.get(key) not in (None, ""):
                transaction[key] = row.get(key)
        normalized.append(transaction)
    return sorted(normalized, key=_transaction_sort_key)


def _normalized_cash_ledger_with_symbols(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        try:
            clean_rows = normalize_cash_ledger_rows([row])
        except ValueError as exc:
            raise ValueError(f"Cash ledger row {index}: {exc}") from exc
        if not clean_rows:
            continue
        clean = dict(clean_rows[0])
        for key in ("market", "ticker", "symbol"):
            if row.get(key) not in (None, ""):
                clean[key] = row.get(key)
        normalized.append(clean)
    return sorted(normalized, key=lambda row: (str(row["event_date"]), str(row["currency"]), str(row["event_type"])))


def _state_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["market"]), str(row["ticker"])


def _average_entry_fx(state: _PositionState, usd_krw: float) -> tuple[float, bool]:
    if state.currency == "KRW":
        return 1.0, state.estimated_fx
    if state.cost_local > 0:
        return state.cost_krw_at_entry_fx / state.cost_local, state.estimated_fx
    return usd_krw, True


def _month(value: object) -> str:
    return str(value)[:7]


def _blank_month_row(month: str) -> dict[str, float | str]:
    return {
        "month": month,
        "realized_pnl_krw": 0.0,
        "dividend_interest_krw": 0.0,
        "fees_taxes_krw": 0.0,
        "external_flow_krw": 0.0,
        "buy_amount_krw": 0.0,
        "sell_amount_krw": 0.0,
    }


def _xirr(cashflows: list[tuple[date, float]]) -> float | None:
    if len(cashflows) < 2:
        return None
    if not any(amount < 0 for _, amount in cashflows) or not any(amount > 0 for _, amount in cashflows):
        return None
    start = min(day for day, _ in cashflows)

    def npv(rate: float) -> float:
        total = 0.0
        for day, amount in cashflows:
            years = (day - start).days / 365.0
            total += amount / ((1.0 + rate) ** years)
        return total

    low = -0.9999
    high = 10.0
    low_value = npv(low)
    high_value = npv(high)
    if low_value * high_value > 0:
        return None
    for _ in range(100):
        mid = (low + high) / 2.0
        mid_value = npv(mid)
        if abs(mid_value) < 1e-7:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2.0


def calculate_performance_metrics(
    *,
    transactions: Iterable[Mapping[str, Any]],
    holdings: Iterable[Mapping[str, Any]],
    cash_ledger: Iterable[Mapping[str, Any]],
    usd_krw: float,
    current_total_value_krw: float | None = None,
) -> PerformanceAnalysis:
    """Calculate portfolio performance using average-cost accounting.

    The v1 model separates gross realized/unrealized price and FX effects from
    user-entered fees/taxes. Total profit subtracts fees/taxes once.
    """

    if usd_krw <= 0:
        raise ValueError("usd_krw must be positive")

    normalized_transactions = _normalized_transactions_with_fx(transactions)
    normalized_holdings = normalize_holding_rows(holdings)
    holdings_by_key = {_state_key(row): row for row in normalized_holdings}
    states: dict[tuple[str, str], _PositionState] = {}
    monthly: dict[str, dict[str, float | str]] = defaultdict(lambda: _blank_month_row(""))
    xirr_flows: list[tuple[date, float]] = []

    def month_row(month: str) -> dict[str, float | str]:
        row = monthly[month]
        if row["month"] == "":
            row["month"] = month
        return row

    for transaction in normalized_transactions:
        key = _state_key(transaction)
        state = states.setdefault(
            key,
            _PositionState(
                market=str(transaction["market"]),
                ticker=str(transaction["ticker"]),
                display_name=str(transaction["display_name"]),
                currency=str(transaction["currency"]),
            ),
        )
        state.display_name = str(transaction["display_name"])
        quantity = _to_float(transaction["quantity"])
        unit_price = _to_float(transaction["unit_price"])
        fee = _to_float(transaction.get("fee"))
        tax = _to_float(transaction.get("tax"))
        gross_local = unit_price * quantity
        fx_rate, estimated_fx = _positive_fx_rate(state.currency, transaction, usd_krw)
        state.estimated_fx = state.estimated_fx or estimated_fx
        fee_tax_krw = (fee + tax) * fx_rate
        state.fees_taxes_krw += fee_tax_krw
        row = month_row(_month(transaction["occurred_at"]))
        row["fees_taxes_krw"] = float(row["fees_taxes_krw"]) + fee_tax_krw

        if transaction["transaction_type"] == "buy":
            state.quantity += quantity
            state.cost_local += gross_local
            state.cost_krw_at_entry_fx += gross_local * fx_rate
            row["buy_amount_krw"] = float(row["buy_amount_krw"]) + gross_local * fx_rate
            continue

        if quantity - state.quantity > 1e-9:
            raise ValueError(f"{state.market}/{state.ticker} sell quantity exceeds current holdings")
        average_cost = state.cost_local / state.quantity if state.quantity else 0.0
        average_entry_fx, average_fx_estimated = _average_entry_fx(state, usd_krw)
        state.estimated_fx = state.estimated_fx or average_fx_estimated
        sold_cost_local = average_cost * quantity
        price_effect = (unit_price - average_cost) * quantity * average_entry_fx
        fx_effect = unit_price * quantity * (fx_rate - average_entry_fx) if state.currency == "USD" else 0.0
        realized = price_effect + fx_effect
        state.realized_price_effect_krw += price_effect
        state.realized_fx_effect_krw += fx_effect
        state.realized_pnl_krw += realized
        state.quantity = 0.0 if abs(state.quantity - quantity) < 1e-9 else state.quantity - quantity
        state.cost_local = 0.0 if state.quantity == 0 else max(state.cost_local - sold_cost_local, 0.0)
        state.cost_krw_at_entry_fx = 0.0 if state.quantity == 0 else max(state.cost_krw_at_entry_fx - sold_cost_local * average_entry_fx, 0.0)
        row["sell_amount_krw"] = float(row["sell_amount_krw"]) + gross_local * fx_rate
        row["realized_pnl_krw"] = float(row["realized_pnl_krw"]) + realized

    normalized_ledger = _normalized_cash_ledger_with_symbols(cash_ledger)
    net_deposit_krw = 0.0
    portfolio_income_krw = 0.0
    portfolio_fee_tax_krw = 0.0
    estimated_fx = False
    for ledger_row in normalized_ledger:
        currency = str(ledger_row["currency"])
        amount = _to_float(ledger_row["amount"])
        amount_krw, row_estimated_fx = _amount_to_krw(amount, currency, ledger_row, usd_krw)
        estimated_fx = estimated_fx or row_estimated_fx
        event_type = str(ledger_row["event_type"])
        row = month_row(_month(ledger_row["event_date"]))
        if event_type in EXTERNAL_FLOW_TYPES:
            net_deposit_krw += amount_krw
            row["external_flow_krw"] = float(row["external_flow_krw"]) + amount_krw
            xirr_flows.append((date.fromisoformat(str(ledger_row["event_date"])), -amount_krw))
        elif event_type in INCOME_TYPES:
            row["dividend_interest_krw"] = float(row["dividend_interest_krw"]) + amount_krw
            key = (str(ledger_row.get("market") or ""), str(ledger_row.get("ticker") or ledger_row.get("symbol") or ""))
            if key in states:
                states[key].dividend_interest_krw += amount_krw
            else:
                portfolio_income_krw += amount_krw
        elif event_type in FEE_TAX_TYPES:
            fee_tax_krw = abs(amount_krw)
            portfolio_fee_tax_krw += fee_tax_krw
            row["fees_taxes_krw"] = float(row["fees_taxes_krw"]) + fee_tax_krw

    symbol_rows: list[SymbolPerformance] = []
    key_union = set(states) | set(holdings_by_key)
    for key in sorted(key_union):
        holding = holdings_by_key.get(key, {})
        state = states.get(key)
        if state is None:
            currency = str(holding["currency"])
            quantity = _to_float(holding["quantity"])
            avg_price = holding.get("avg_price")
            current_price = holding.get("current_price")
            avg_price_float = _to_float(avg_price) if avg_price is not None else None
            current_price_float = _to_float(current_price) if current_price is not None else None
            entry_fx = usd_krw if currency == "USD" else 1.0
            estimated_entry_fx = currency == "USD"
            cost_local = (avg_price_float or 0.0) * quantity
            state = _PositionState(
                market=str(holding["market"]),
                ticker=str(holding["ticker"]),
                display_name=str(holding["display_name"]),
                currency=currency,
                quantity=quantity,
                cost_local=cost_local,
                cost_krw_at_entry_fx=cost_local * entry_fx,
                estimated_fx=estimated_entry_fx,
            )
        else:
            quantity = state.quantity
            avg_price_float = state.cost_local / state.quantity if state.quantity else None
            current_price_float = _to_float(holding.get("current_price")) if holding.get("current_price") is not None else None

        avg_entry_fx, avg_fx_estimated = _average_entry_fx(state, usd_krw)
        row_estimated_fx = state.estimated_fx or avg_fx_estimated
        unrealized_pnl = 0.0
        unrealized_price_effect = 0.0
        unrealized_fx_effect = 0.0
        if quantity > 0 and current_price_float is not None and avg_price_float is not None:
            current_fx = usd_krw if state.currency == "USD" else 1.0
            unrealized_price_effect = (current_price_float - avg_price_float) * quantity * avg_entry_fx
            unrealized_fx_effect = current_price_float * quantity * (current_fx - avg_entry_fx) if state.currency == "USD" else 0.0
            unrealized_pnl = unrealized_price_effect + unrealized_fx_effect

        price_effect = state.realized_price_effect_krw + unrealized_price_effect
        fx_effect = state.realized_fx_effect_krw + unrealized_fx_effect
        fees_taxes = state.fees_taxes_krw
        if portfolio_fee_tax_krw and key not in states:
            fees_taxes += 0.0
        total_pnl = state.realized_pnl_krw + unrealized_pnl + state.dividend_interest_krw - fees_taxes
        symbol_rows.append(
            SymbolPerformance(
                market=state.market,
                ticker=state.ticker,
                display_name=state.display_name,
                currency=state.currency,
                quantity=quantity,
                avg_price=avg_price_float,
                current_price=current_price_float,
                realized_pnl_krw=state.realized_pnl_krw,
                unrealized_pnl_krw=unrealized_pnl,
                dividend_interest_krw=state.dividend_interest_krw,
                fees_taxes_krw=fees_taxes,
                total_pnl_krw=total_pnl,
                price_effect_krw=price_effect,
                fx_effect_krw=fx_effect,
                estimated_fx=row_estimated_fx,
            )
        )

    realized_pnl = sum(row.realized_pnl_krw for row in symbol_rows)
    unrealized_pnl = sum(row.unrealized_pnl_krw for row in symbol_rows)
    symbol_income = sum(row.dividend_interest_krw for row in symbol_rows)
    dividend_interest = symbol_income + portfolio_income_krw
    transaction_fee_tax = sum(row.fees_taxes_krw for row in symbol_rows)
    fees_taxes = transaction_fee_tax + portfolio_fee_tax_krw
    price_effect = sum(row.price_effect_krw for row in symbol_rows)
    fx_effect = sum(row.fx_effect_krw for row in symbol_rows)
    total_profit = realized_pnl + unrealized_pnl + dividend_interest - fees_taxes

    if current_total_value_krw is None:
        current_total_value_krw = 0.0
        for holding in normalized_holdings:
            if holding.get("current_price") is None:
                continue
            rate = usd_krw if holding["currency"] == "USD" else 1.0
            current_total_value_krw += _to_float(holding["current_price"]) * _to_float(holding["quantity"]) * rate
        cash_balances = calculate_cash_balances(normalized_ledger)
        current_total_value_krw += float(cash_balances["KRW"]) + float(cash_balances["USD"]) * usd_krw

    flow_adjusted_asset_change = current_total_value_krw - net_deposit_krw if current_total_value_krw is not None else None
    denominator = abs(net_deposit_krw) if net_deposit_krw else None
    simple_return = total_profit / denominator if denominator else None
    twr_base_return = flow_adjusted_asset_change / denominator if denominator and flow_adjusted_asset_change is not None else None
    if current_total_value_krw is not None:
        xirr_flows.append((date.today(), current_total_value_krw))
    mwr_irr = _xirr(xirr_flows)

    monthly_rows = [
        MonthlyPerformance(
            month=str(row["month"]),
            realized_pnl_krw=float(row["realized_pnl_krw"]),
            dividend_interest_krw=float(row["dividend_interest_krw"]),
            fees_taxes_krw=float(row["fees_taxes_krw"]),
            external_flow_krw=float(row["external_flow_krw"]),
            buy_amount_krw=float(row["buy_amount_krw"]),
            sell_amount_krw=float(row["sell_amount_krw"]),
        )
        for _, row in sorted(monthly.items())
        if row["month"]
    ]

    return PerformanceAnalysis(
        total_profit_krw=total_profit,
        realized_pnl_krw=realized_pnl,
        unrealized_pnl_krw=unrealized_pnl,
        dividend_interest_krw=dividend_interest,
        fees_taxes_krw=fees_taxes,
        fx_effect_krw=fx_effect,
        price_effect_krw=price_effect,
        net_deposit_krw=net_deposit_krw,
        flow_adjusted_asset_change_krw=flow_adjusted_asset_change,
        simple_return=simple_return,
        twr_base_return=twr_base_return,
        mwr_irr=mwr_irr,
        current_total_value_krw=current_total_value_krw,
        estimated_fx=estimated_fx or any(row.estimated_fx for row in symbol_rows),
        rows=symbol_rows,
        monthly_rows=monthly_rows,
    )
