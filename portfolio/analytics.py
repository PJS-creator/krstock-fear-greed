from __future__ import annotations

from .models import PortfolioSnapshot, Position, PositionSnapshot, Quote

SUPPORTED_CURRENCIES = {"KRW", "USD"}


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_currency(currency: str) -> None:
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency: {currency}")


def _currency_to_krw_rate(currency: str, usd_krw: float) -> float:
    _validate_currency(currency)
    if currency == "KRW":
        return 1.0
    return usd_krw


def _validate_position(position: Position) -> None:
    _validate_currency(position.currency)
    _validate_non_negative("quantity", position.quantity)
    if position.avg_price is not None:
        _validate_non_negative("avg_price", position.avg_price)


def _validate_quote(quote: Quote) -> None:
    _validate_currency(quote.currency)
    _validate_non_negative("quote.price", quote.price)
    _validate_non_negative("previous_close", quote.previous_close)


def _validate_position_quote_pair(position: Position, quote: Quote) -> None:
    if position.symbol != quote.symbol or position.market != quote.market:
        raise ValueError(f"Quote does not match position: {position.symbol} / {quote.symbol}")
    if position.currency != quote.currency:
        raise ValueError(
            "Position currency and quote currency must match for this MVP: "
            f"{position.symbol} position={position.currency} quote={quote.currency}"
        )


def build_position_snapshot(
    position: Position,
    quote: Quote,
    total_value_krw: float,
    usd_krw: float,
) -> PositionSnapshot:
    _validate_positive("usd_krw", usd_krw)
    _validate_position(position)
    _validate_quote(quote)
    _validate_position_quote_pair(position, quote)

    fx_rate = _currency_to_krw_rate(position.currency, usd_krw)
    market_value_krw = quote.price * position.quantity * fx_rate
    day_pnl_krw = (quote.price - quote.previous_close) * position.quantity * fx_rate
    weight = market_value_krw / total_value_krw if total_value_krw else 0.0
    target_gap = weight - position.target_weight

    cost_basis_krw: float | None = None
    total_pnl_krw: float | None = None
    total_pnl_pct: float | None = None
    if position.avg_price is not None:
        cost_basis_krw = position.avg_price * position.quantity * fx_rate
        total_pnl_krw = market_value_krw - cost_basis_krw
        total_pnl_pct = total_pnl_krw / cost_basis_krw if cost_basis_krw else 0.0

    return PositionSnapshot(
        position=position,
        quote=quote,
        fx_rate=fx_rate,
        cost_basis_krw=cost_basis_krw,
        market_value_krw=market_value_krw,
        day_pnl_krw=day_pnl_krw,
        total_pnl_krw=total_pnl_krw,
        total_pnl_pct=total_pnl_pct,
        weight=weight,
        target_gap=target_gap,
    )


def build_portfolio_snapshot(
    positions: list[Position],
    quotes: dict[tuple[str, str], Quote],
    *,
    usd_krw: float,
    cash_krw: float = 0.0,
) -> PortfolioSnapshot:
    _validate_positive("usd_krw", usd_krw)
    _validate_non_negative("cash_krw", cash_krw)

    quote_values = []
    for position in positions:
        quote = quotes[(position.market, position.symbol)]
        _validate_position(position)
        _validate_quote(quote)
        _validate_position_quote_pair(position, quote)
        fx_rate = _currency_to_krw_rate(position.currency, usd_krw)
        quote_values.append(quote.price * position.quantity * fx_rate)

    total_position_value_krw = sum(quote_values)
    total_value_krw = total_position_value_krw + cash_krw

    position_snapshots = [
        build_position_snapshot(position, quotes[(position.market, position.symbol)], total_value_krw, usd_krw)
        for position in positions
    ]

    known_cost_positions = [item for item in position_snapshots if item.cost_basis_krw is not None]
    total_cost_krw = sum(item.cost_basis_krw or 0.0 for item in known_cost_positions)
    day_pnl_krw = sum(item.day_pnl_krw for item in position_snapshots)
    total_pnl_krw = sum(item.total_pnl_krw or 0.0 for item in known_cost_positions) if known_cost_positions else None
    total_pnl_pct = None
    if known_cost_positions:
        total_pnl_pct = (total_pnl_krw or 0.0) / total_cost_krw if total_cost_krw else 0.0
    cost_basis_market_value_krw = sum(item.market_value_krw for item in known_cost_positions)
    cost_basis_coverage = cost_basis_market_value_krw / total_position_value_krw if total_position_value_krw else 0.0

    return PortfolioSnapshot(
        positions=position_snapshots,
        cash_krw=cash_krw,
        total_position_value_krw=total_position_value_krw,
        total_value_krw=total_value_krw,
        total_cost_krw=total_cost_krw,
        day_pnl_krw=day_pnl_krw,
        total_pnl_krw=total_pnl_krw,
        total_pnl_pct=total_pnl_pct,
        cost_basis_market_value_krw=cost_basis_market_value_krw,
        cost_basis_coverage=cost_basis_coverage,
        cost_basis_position_count=len(known_cost_positions),
    )
