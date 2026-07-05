from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from portfolio.holdings import clean_text, normalize_holding_rows, normalize_korea_ticker, normalize_ticker, parse_non_negative_float

TARGET_ASSET_TYPES = {"stock", "cash"}
TARGET_WEIGHT_TOLERANCE_PCT = 0.1
MIN_REBALANCE_TRADE_VALUE_KRW = 100_000.0
MIN_REBALANCE_WEIGHT_DIFF_PCT = 0.05
CASH_SYMBOL_BY_CURRENCY = {"KRW": "CASH_KRW", "USD": "CASH_USD"}
CASH_DISPLAY_BY_CURRENCY = {"KRW": "원화 현금", "USD": "달러 현금"}
RebalanceMode = Literal["full", "deposit_only", "cash_only"]


@dataclass(frozen=True)
class TargetAllocation:
    asset_type: str
    symbol: str | None
    market: str | None
    currency: str
    display_name: str
    target_weight_pct: float
    is_enabled: bool = True
    current_price: float | None = None


@dataclass(frozen=True)
class RebalanceRow:
    asset_type: str
    symbol: str
    market: str | None
    currency: str
    display_name: str
    current_weight_pct: float
    target_weight_pct: float
    current_value_krw: float
    target_value_krw: float
    delta_krw: float
    current_quantity: float | None
    adjustment_quantity: int | None
    estimated_adjustment_value_krw: float
    post_adjustment_weight_pct: float
    action: str
    data_status: str


@dataclass(frozen=True)
class RebalancePlan:
    rows: list[RebalanceRow]
    total_asset_krw: float
    target_weight_sum_pct: float
    weight_sum_ok: bool
    mode: RebalanceMode
    additional_deposit_krw: float
    cash_budget_krw: float


def _asset_type(value: object) -> str:
    text = clean_text(value).lower()
    mapping = {
        "stock": "stock",
        "종목": "stock",
        "주식": "stock",
        "cash": "cash",
        "현금": "cash",
    }
    if text not in mapping:
        raise ValueError("asset_type must be stock/cash or 종목/현금")
    return mapping[text]


def _market(value: object | None) -> str | None:
    text = clean_text(value).upper()
    if not text:
        return None
    if text in {"KRX", "KOSPI", "KOSDAQ"}:
        return "KR"
    if text == "USA":
        return "US"
    if text not in {"KR", "US"}:
        raise ValueError(f"Unsupported market: {text}")
    return text


def _currency(value: object | None, *, asset_type: str, market: str | None) -> str:
    text = clean_text(value).upper()
    if not text:
        if asset_type == "cash":
            raise ValueError("cash allocation currency is required")
        text = "KRW" if market == "KR" else "USD"
    if text not in {"KRW", "USD"}:
        raise ValueError(f"Unsupported currency: {text}")
    return text


def _bool(value: object, default: bool = True) -> bool:
    if value is None or clean_text(value) == "":
        return default
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"1", "true", "yes", "y", "on", "사용", "활성"}


def _optional_price(value: object | None) -> float | None:
    if value is None or clean_text(value) == "":
        return None
    return parse_non_negative_float("current_price", value)


def _weight_pct(value: object | None) -> float:
    if value is None or clean_text(value) == "":
        return 0.0
    number = parse_non_negative_float("target_weight_pct", value)
    if number > 100:
        raise ValueError("target_weight_pct must be <= 100")
    return number


def _stock_symbol(value: object | None, market: str | None) -> str:
    raw = clean_text(value)
    if not raw:
        raise ValueError("stock allocation symbol is required")
    if market == "KR":
        return normalize_korea_ticker(raw)
    return normalize_ticker(raw)


def normalize_target_allocation_row(row: Mapping[str, Any]) -> dict[str, object]:
    asset_type = _asset_type(row.get("asset_type") or row.get("자산 유형"))
    market = _market(row.get("market") or row.get("시장"))
    currency = _currency(row.get("currency") or row.get("통화"), asset_type=asset_type, market=market)
    if asset_type == "cash":
        symbol = clean_text(row.get("symbol") or row.get("ticker") or row.get("종목명 또는 티커") or row.get("티커")) or CASH_SYMBOL_BY_CURRENCY[currency]
        market = None
        display_name = clean_text(row.get("display_name") or row.get("자산")) or CASH_DISPLAY_BY_CURRENCY[currency]
    else:
        symbol = _stock_symbol(row.get("symbol") or row.get("ticker") or row.get("종목명 또는 티커") or row.get("티커"), market)
        display_name = clean_text(row.get("display_name") or row.get("자산")) or symbol
    return {
        "asset_type": asset_type,
        "symbol": symbol,
        "market": market,
        "currency": currency,
        "display_name": display_name,
        "target_weight_pct": _weight_pct(row.get("target_weight_pct") or row.get("목표 비중 %")),
        "is_enabled": _bool(row.get("is_enabled") if "is_enabled" in row else row.get("사용"), default=True),
        "current_price": _optional_price(row.get("current_price") or row.get("현재가")),
    }


def normalize_target_allocations(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for index, row in enumerate(rows, start=1):
        if not any(clean_text(row.get(field)) for field in ("asset_type", "자산 유형", "symbol", "ticker", "종목명 또는 티커", "target_weight_pct", "목표 비중 %")):
            continue
        try:
            clean = normalize_target_allocation_row(row)
        except ValueError as exc:
            raise ValueError(f"Target allocation row {index}: {exc}") from exc
        key = (str(clean["asset_type"]), str(clean["symbol"]), clean.get("market") if clean["asset_type"] == "stock" else str(clean["currency"]))
        if key in seen:
            raise ValueError(f"Target allocation row {index}: duplicate allocation")
        seen.add(key)
        normalized.append(clean)
    return normalized


def serialize_target_allocations(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, object]]:
    return [dict(row) for row in normalize_target_allocations(rows)]


def target_weight_sum(rows: Iterable[Mapping[str, Any]]) -> float:
    return sum(float(row["target_weight_pct"]) for row in normalize_target_allocations(rows) if bool(row.get("is_enabled", True)))


def is_target_weight_sum_valid(total_pct: float, *, tolerance: float = TARGET_WEIGHT_TOLERANCE_PCT) -> bool:
    return abs(total_pct - 100.0) <= tolerance


def _value_krw(amount: float, currency: str, usd_krw: float) -> float:
    return amount if currency == "KRW" else amount * usd_krw


def default_target_allocations_from_portfolio(
    holdings: Iterable[Mapping[str, Any]],
    *,
    cash_krw: float,
    cash_usd: float,
    usd_krw: float,
    total_asset_krw: float | None = None,
) -> list[dict[str, object]]:
    rows = normalize_holding_rows(holdings)
    total = float(total_asset_krw or 0.0)
    if total <= 0:
        total = sum(
            float(row.get("current_price") or 0.0) * float(row["quantity"]) * (usd_krw if row["currency"] == "USD" else 1.0)
            for row in rows
        ) + cash_krw + cash_usd * usd_krw
    allocations: list[dict[str, object]] = []
    for row in rows:
        value = float(row.get("current_price") or 0.0) * float(row["quantity"]) * (usd_krw if row["currency"] == "USD" else 1.0)
        stored_target = float(row.get("target_weight") or 0.0) * 100.0
        weight = stored_target if stored_target > 0 else (value / total * 100.0 if total else 0.0)
        allocations.append(
            {
                "asset_type": "stock",
                "symbol": row["ticker"],
                "market": row["market"],
                "currency": row["currency"],
                "display_name": row["display_name"],
                "target_weight_pct": weight,
                "is_enabled": True,
                "current_price": row.get("current_price"),
            }
        )
    for currency, value in (("KRW", cash_krw), ("USD", cash_usd * usd_krw)):
        allocations.append(
            {
                "asset_type": "cash",
                "symbol": CASH_SYMBOL_BY_CURRENCY[currency],
                "market": None,
                "currency": currency,
                "display_name": CASH_DISPLAY_BY_CURRENCY[currency],
                "target_weight_pct": value / total * 100.0 if total else 0.0,
                "is_enabled": True,
                "current_price": None,
            }
        )
    return serialize_target_allocations(allocations)


def _stock_key(market: object, symbol: object) -> tuple[str, str]:
    return str(market), str(symbol)


def _cash_key(currency: object) -> tuple[str, str]:
    return "cash", str(currency)


def _cash_adjustment_amount(delta_krw: float, currency: str, usd_krw: float) -> float:
    return delta_krw if currency == "KRW" else delta_krw / usd_krw


def is_negligible_rebalance_delta(delta_krw: float, total_asset_krw: float) -> bool:
    if abs(delta_krw) <= MIN_REBALANCE_TRADE_VALUE_KRW:
        return True
    if total_asset_krw <= 0:
        return False
    return abs(delta_krw) / total_asset_krw * 100.0 <= MIN_REBALANCE_WEIGHT_DIFF_PCT


def calculate_rebalancing_plan(
    *,
    target_allocations: Iterable[Mapping[str, Any]],
    holdings: Iterable[Mapping[str, Any]],
    cash_krw: float,
    cash_usd: float,
    usd_krw: float,
    total_asset_krw: float | None = None,
    mode: RebalanceMode = "full",
    additional_deposit_krw: float = 0.0,
) -> RebalancePlan:
    if usd_krw <= 0:
        raise ValueError("usd_krw must be positive")
    if mode not in {"full", "deposit_only", "cash_only"}:
        raise ValueError("unsupported rebalance mode")
    extra_deposit = parse_non_negative_float("additional_deposit_krw", additional_deposit_krw)
    clean_allocations = [row for row in normalize_target_allocations(target_allocations) if bool(row.get("is_enabled", True))]
    clean_holdings = normalize_holding_rows(holdings)
    current_stock: dict[tuple[str, str], dict[str, object]] = {}
    current_values: dict[tuple[str, str], float] = {}
    current_quantities: dict[tuple[str, str], float] = {}
    unit_values: dict[tuple[str, str], float | None] = {}

    for row in clean_holdings:
        key = _stock_key(row["market"], row["ticker"])
        current_stock[key] = row
        quantity = float(row["quantity"])
        current_quantities[key] = quantity
        price = row.get("current_price")
        if price is None:
            current_values[key] = 0.0
            unit_values[key] = None
        else:
            unit_krw = float(price) * (usd_krw if row["currency"] == "USD" else 1.0)
            current_values[key] = unit_krw * quantity
            unit_values[key] = unit_krw

    current_cash_krw = float(cash_krw) + (extra_deposit if mode in {"deposit_only", "cash_only"} else 0.0)
    cash_values = {
        _cash_key("KRW"): current_cash_krw,
        _cash_key("USD"): float(cash_usd) * usd_krw,
    }
    total = float(total_asset_krw) if total_asset_krw is not None else sum(current_values.values()) + float(cash_krw) + float(cash_usd) * usd_krw
    if mode in {"deposit_only", "cash_only"}:
        total += extra_deposit
    if total < 0:
        raise ValueError("total_asset_krw must be non-negative")

    allocations_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for row in clean_allocations:
        if row["asset_type"] == "cash":
            key = _cash_key(row["currency"])
        else:
            key = _stock_key(row.get("market"), row.get("symbol"))
        allocations_by_key[key] = row

    all_keys = set(allocations_by_key) | set(current_stock) | set(cash_values)
    preliminary: list[dict[str, object]] = []
    for key in sorted(all_keys):
        allocation = allocations_by_key.get(key)
        if key[0] == "cash":
            currency = key[1]
            current_value = cash_values.get(key, 0.0)
            target_weight = float(allocation.get("target_weight_pct", 0.0)) if allocation else 0.0
            target_value = total * target_weight / 100.0
            delta = target_value - current_value
            preliminary.append(
                {
                    "asset_type": "cash",
                    "symbol": CASH_SYMBOL_BY_CURRENCY[currency],
                    "market": None,
                    "currency": currency,
                    "display_name": allocation.get("display_name") if allocation else CASH_DISPLAY_BY_CURRENCY[currency],
                    "current_value_krw": current_value,
                    "target_weight_pct": target_weight,
                    "target_value_krw": target_value,
                    "delta_krw": delta,
                    "current_quantity": None,
                    "unit_krw": 1.0 if currency == "KRW" else usd_krw,
                    "data_status": "계산 가능",
                }
            )
            continue

        holding = current_stock.get(key, {})
        target_weight = float(allocation.get("target_weight_pct", 0.0)) if allocation else 0.0
        target_value = total * target_weight / 100.0
        current_value = current_values.get(key, 0.0)
        currency = str((allocation or holding).get("currency") or holding.get("currency") or "USD")
        price = (allocation or {}).get("current_price") if allocation else None
        unit_krw = unit_values.get(key)
        if unit_krw is None and price is not None:
            unit_krw = float(price) * (usd_krw if currency == "USD" else 1.0)
        delta = target_value - current_value
        preliminary.append(
            {
                "asset_type": "stock",
                "symbol": str((allocation or holding).get("symbol") or holding.get("ticker") or key[1]),
                "market": str((allocation or holding).get("market") or holding.get("market") or key[0]),
                "currency": currency,
                "display_name": str((allocation or holding).get("display_name") or holding.get("display_name") or key[1]),
                "current_value_krw": current_value,
                "target_weight_pct": target_weight,
                "target_value_krw": target_value,
                "delta_krw": delta,
                "current_quantity": current_quantities.get(key, 0.0),
                "unit_krw": unit_krw,
                "data_status": "계산 가능" if unit_krw else "현재가 필요",
            }
        )

    positive_stock_delta = sum(float(row["delta_krw"]) for row in preliminary if row["asset_type"] == "stock" and float(row["delta_krw"]) > 0)
    cash_budget = float(cash_krw) + float(cash_usd) * usd_krw + extra_deposit
    scale = 1.0
    if mode == "cash_only" and positive_stock_delta > cash_budget > 0:
        scale = cash_budget / positive_stock_delta
    elif mode == "cash_only" and positive_stock_delta > 0 and cash_budget <= 0:
        scale = 0.0

    result_rows: list[RebalanceRow] = []
    for row in preliminary:
        delta = float(row["delta_krw"])
        effective_delta = delta
        if mode == "deposit_only" and row["asset_type"] == "stock":
            effective_delta = max(delta, 0.0)
        if mode == "cash_only" and row["asset_type"] == "stock":
            effective_delta = max(delta, 0.0) * scale
        if is_negligible_rebalance_delta(effective_delta, total):
            effective_delta = 0.0

        estimated_value = effective_delta
        adjustment_quantity: int | None = None
        action = "유지"
        if row["asset_type"] == "stock":
            unit_krw = row.get("unit_krw")
            if not unit_krw or float(unit_krw) <= 0:
                adjustment_quantity = None
                estimated_value = 0.0
                action = "현재가 필요"
            elif effective_delta > 0:
                adjustment_quantity = math.floor(effective_delta / float(unit_krw))
                estimated_value = adjustment_quantity * float(unit_krw)
                action = "늘림" if adjustment_quantity else "유지"
            elif effective_delta < 0 and mode == "full":
                current_quantity = float(row.get("current_quantity") or 0.0)
                adjustment_quantity = -min(int(math.ceil(abs(effective_delta) / float(unit_krw))), int(math.floor(current_quantity)))
                estimated_value = adjustment_quantity * float(unit_krw)
                action = "줄임" if adjustment_quantity else "유지"
            else:
                adjustment_quantity = 0
                estimated_value = 0.0
                action = "유지"
        else:
            if mode in {"deposit_only", "cash_only"} and effective_delta < 0:
                effective_delta = 0.0
                estimated_value = 0.0
            adjustment_quantity = None
            cash_amount = _cash_adjustment_amount(effective_delta, str(row["currency"]), usd_krw)
            if cash_amount > 0:
                action = "현금 증가"
            elif cash_amount < 0:
                action = "현금 감소"
            else:
                action = "유지"

        post_value = float(row["current_value_krw"]) + estimated_value
        result_rows.append(
            RebalanceRow(
                asset_type=str(row["asset_type"]),
                symbol=str(row["symbol"]),
                market=row.get("market") if row.get("market") is None else str(row.get("market")),
                currency=str(row["currency"]),
                display_name=str(row["display_name"]),
                current_weight_pct=(float(row["current_value_krw"]) / total * 100.0 if total else 0.0),
                target_weight_pct=float(row["target_weight_pct"]),
                current_value_krw=float(row["current_value_krw"]),
                target_value_krw=float(row["target_value_krw"]),
                delta_krw=delta,
                current_quantity=row.get("current_quantity") if row.get("current_quantity") is None else float(row.get("current_quantity") or 0.0),
                adjustment_quantity=adjustment_quantity,
                estimated_adjustment_value_krw=estimated_value,
                post_adjustment_weight_pct=(post_value / total * 100.0 if total else 0.0),
                action=action,
                data_status=str(row["data_status"]),
            )
        )

    total_weight = sum(float(row["target_weight_pct"]) for row in clean_allocations)
    return RebalancePlan(
        rows=result_rows,
        total_asset_krw=total,
        target_weight_sum_pct=total_weight,
        weight_sum_ok=is_target_weight_sum_valid(total_weight),
        mode=mode,
        additional_deposit_krw=extra_deposit,
        cash_budget_krw=cash_budget,
    )
