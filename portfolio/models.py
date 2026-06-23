from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Market = Literal["KR", "US"]
Currency = Literal["KRW", "USD"]


@dataclass(frozen=True)
class Position:
    market: Market
    symbol: str
    name: str
    quantity: float
    avg_price: float | None
    currency: Currency
    target_weight: float = 0.0
    strategy_tag: str = "Core"
    account_name: str = "Manual"
    note: str = ""


@dataclass(frozen=True)
class Quote:
    market: Market
    symbol: str
    price: float
    previous_close: float
    currency: Currency
    provider: str = "sample"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class PositionSnapshot:
    position: Position
    quote: Quote
    fx_rate: float
    cost_basis_krw: float | None
    market_value_krw: float
    day_pnl_krw: float
    total_pnl_krw: float | None
    total_pnl_pct: float | None
    weight: float
    target_gap: float


@dataclass(frozen=True)
class PortfolioSnapshot:
    positions: list[PositionSnapshot]
    cash_krw: float
    total_position_value_krw: float
    total_value_krw: float
    total_cost_krw: float
    day_pnl_krw: float
    total_pnl_krw: float | None
    total_pnl_pct: float | None
    cost_basis_market_value_krw: float = 0.0
    cost_basis_coverage: float = 0.0
    cost_basis_position_count: int = 0
