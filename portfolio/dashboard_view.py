from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from portfolio.holdings import PortfolioMetrics
from portfolio.performance import PerformanceAnalysis, calculate_performance_metrics


@dataclass(frozen=True)
class AssetRowView:
    asset_id: str
    name: str
    ticker: str
    market: str
    currency: str
    quantity: float
    current_price: float | None
    value_krw: float
    weight: float
    day_change_krw: float | None
    day_change_pct: float | None
    total_pnl_krw: float | None
    total_pnl_pct: float | None
    status: str


@dataclass(frozen=True)
class CashRowView:
    currency: str
    amount: float
    value_krw: float
    weight: float
    fx_rate: float


@dataclass(frozen=True)
class ProfitContributor:
    label: str
    value_krw: float
    pct: float | None = None


@dataclass(frozen=True)
class ProfitSummaryView:
    period: str
    evaluation_profit_krw: float | None
    evaluation_profit_pct: float | None
    realized_profit_krw: float | None
    dividend_interest_krw: float
    fees_taxes_krw: float
    total_profit_krw: float | None
    simple_return: float | None
    insufficient_reasons: tuple[str, ...]
    top_contributors: tuple[ProfitContributor, ...]
    loss_contributors: tuple[ProfitContributor, ...]

    @property
    def has_data(self) -> bool:
        values = [
            self.evaluation_profit_krw,
            self.realized_profit_krw,
            self.dividend_interest_krw,
            self.fees_taxes_krw,
            self.total_profit_krw,
        ]
        return any(value not in (None, 0) for value in values)


@dataclass(frozen=True)
class DashboardViewModel:
    total_asset_krw: float
    investment_value_krw: float
    cash_value_krw: float
    cash_weight: float
    day_change_krw: float | None
    day_change_pct: float | None
    usd_krw: float
    priced_count: int
    holdings_count: int
    failed_quote_count: int
    missing_quote_count: int
    stale_quote_count: int
    last_price_refresh_at: str | None
    asset_rows: tuple[AssetRowView, ...]
    cash_rows: tuple[CashRowView, ...]
    profit_summary: ProfitSummaryView
    alerts: tuple[str, ...]
    is_empty: bool


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_day(value: object | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def period_start(period: str, *, today: date | None = None) -> date | None:
    today = today or date.today()
    normalized = str(period or "총")
    if normalized in {"총", "전체"}:
        return None
    if normalized == "오늘":
        return today
    if normalized == "이번주":
        return today - timedelta(days=today.weekday())
    if normalized == "이번달":
        return today.replace(day=1)
    if normalized == "이번분기":
        month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=month, day=1)
    if normalized == "올해":
        return today.replace(month=1, day=1)
    return None


def _row_in_period(row: Mapping[str, Any], field_name: str, start: date | None, *, today: date) -> bool:
    if start is None:
        return True
    row_day = _parse_day(row.get(field_name))
    return row_day is not None and start <= row_day <= today


def _fx_rate(currency: str, row: Mapping[str, Any], usd_krw: float) -> float:
    if currency == "KRW":
        return 1.0
    raw = row.get("fx_rate_to_krw")
    if raw not in (None, ""):
        rate = _to_float(raw, usd_krw)
        return rate if rate > 0 else usd_krw
    return usd_krw


def _amount_krw(amount: float, currency: str, row: Mapping[str, Any], usd_krw: float) -> float:
    return amount * _fx_rate(currency, row, usd_krw)


def _performance_analysis(
    *,
    metrics: PortfolioMetrics,
    transactions: Iterable[Mapping[str, Any]],
    cash_ledger: Iterable[Mapping[str, Any]],
) -> PerformanceAnalysis | None:
    try:
        return calculate_performance_metrics(
            transactions=transactions,
            cash_ledger=cash_ledger,
            holdings=[row.holding for row in metrics.rows],
            usd_krw=metrics.usd_krw,
            current_total_value_krw=metrics.total_value_krw,
        )
    except ValueError:
        return None


def _contributors_from_metrics(metrics: PortfolioMetrics) -> tuple[tuple[ProfitContributor, ...], tuple[ProfitContributor, ...]]:
    contributors = [
        ProfitContributor(
            label=str(row.holding.get("display_name") or row.holding.get("ticker")),
            value_krw=float(row.total_pnl_krw or 0.0),
            pct=row.total_pnl_pct,
        )
        for row in metrics.rows
        if row.total_pnl_krw not in (None, 0)
    ]
    positives = tuple(sorted((row for row in contributors if row.value_krw > 0), key=lambda row: row.value_krw, reverse=True)[:3])
    negatives = tuple(sorted((row for row in contributors if row.value_krw < 0), key=lambda row: row.value_krw)[:3])
    return positives, negatives


def build_profit_summary_view(
    *,
    metrics: PortfolioMetrics,
    transactions: Iterable[Mapping[str, Any]] = (),
    cash_ledger: Iterable[Mapping[str, Any]] = (),
    period: str = "총",
    today: date | None = None,
) -> ProfitSummaryView:
    today = today or date.today()
    start = period_start(period, today=today)
    tx_rows = list(transactions)
    ledger_rows = list(cash_ledger)
    analysis = _performance_analysis(metrics=metrics, transactions=tx_rows, cash_ledger=ledger_rows)
    insufficient: list[str] = []

    if start is None:
        evaluation_profit = analysis.unrealized_pnl_krw if analysis is not None else metrics.total_pnl_krw
        evaluation_pct = metrics.total_pnl_pct
        realized_profit = analysis.realized_pnl_krw if analysis is not None else None
        dividend_interest = analysis.dividend_interest_krw if analysis is not None else _ledger_income_krw(ledger_rows, metrics.usd_krw, start, today)
        fees_taxes = analysis.fees_taxes_krw if analysis is not None else _fees_taxes_krw(tx_rows, ledger_rows, metrics.usd_krw, start, today)
        total_profit = analysis.total_profit_krw if analysis is not None else (
            None if evaluation_profit is None else evaluation_profit + dividend_interest - fees_taxes
        )
        simple_return = analysis.simple_return if analysis is not None else metrics.total_pnl_pct
    else:
        evaluation_profit = metrics.day_change_krw if period == "오늘" else None
        evaluation_pct = metrics.day_change_pct if period == "오늘" else None
        if evaluation_profit is None:
            insufficient.append("선택 기간의 평가수익은 기간별 스냅샷이 더 쌓이면 계산됩니다.")
        realized_profit = None
        insufficient.append("선택 기간의 실현손익은 상세 성과분석에서 거래 기준으로 확인하세요.")
        dividend_interest = _ledger_income_krw(ledger_rows, metrics.usd_krw, start, today)
        fees_taxes = _fees_taxes_krw(tx_rows, ledger_rows, metrics.usd_krw, start, today)
        total_profit = None if evaluation_profit is None else evaluation_profit + dividend_interest - fees_taxes
        simple_return = evaluation_pct

    positives, negatives = _contributors_from_metrics(metrics)
    return ProfitSummaryView(
        period=period,
        evaluation_profit_krw=evaluation_profit,
        evaluation_profit_pct=evaluation_pct,
        realized_profit_krw=realized_profit,
        dividend_interest_krw=dividend_interest,
        fees_taxes_krw=fees_taxes,
        total_profit_krw=total_profit,
        simple_return=simple_return,
        insufficient_reasons=tuple(insufficient),
        top_contributors=positives,
        loss_contributors=negatives,
    )


def _ledger_income_krw(rows: Iterable[Mapping[str, Any]], usd_krw: float, start: date | None, today: date) -> float:
    total = 0.0
    for row in rows:
        if str(row.get("event_type")) not in {"dividend", "interest"}:
            continue
        if not _row_in_period(row, "event_date", start, today=today):
            continue
        currency = str(row.get("currency") or "KRW")
        total += _amount_krw(_to_float(row.get("amount")), currency, row, usd_krw)
    return total


def _fees_taxes_krw(
    transactions: Iterable[Mapping[str, Any]],
    cash_ledger: Iterable[Mapping[str, Any]],
    usd_krw: float,
    start: date | None,
    today: date,
) -> float:
    total = 0.0
    for row in transactions:
        if not _row_in_period(row, "occurred_at", start, today=today):
            continue
        currency = str(row.get("currency") or "KRW")
        total += _amount_krw(_to_float(row.get("fee")) + _to_float(row.get("tax")), currency, row, usd_krw)
    for row in cash_ledger:
        if str(row.get("event_type")) not in {"fee", "tax"}:
            continue
        if not _row_in_period(row, "event_date", start, today=today):
            continue
        currency = str(row.get("currency") or "KRW")
        total += abs(_amount_krw(_to_float(row.get("amount")), currency, row, usd_krw))
    return total


def build_dashboard_view_model(
    metrics: PortfolioMetrics,
    *,
    transactions: Iterable[Mapping[str, Any]] = (),
    cash_ledger: Iterable[Mapping[str, Any]] = (),
    period: str = "총",
    max_assets: int | None = None,
) -> DashboardViewModel:
    asset_rows = []
    for row in sorted(metrics.rows, key=lambda item: item.market_value_krw or 0.0, reverse=True):
        holding = row.holding
        value = float(row.market_value_krw or 0.0)
        asset_rows.append(
            AssetRowView(
                asset_id=f"{holding.get('market')}:{holding.get('ticker')}",
                name=str(holding.get("display_name") or holding.get("ticker")),
                ticker=str(holding.get("ticker") or ""),
                market=str(holding.get("market") or ""),
                currency=str(holding.get("currency") or ""),
                quantity=float(holding.get("quantity") or 0.0),
                current_price=None if holding.get("current_price") is None else float(holding.get("current_price")),
                value_krw=value,
                weight=value / metrics.total_value_krw if metrics.total_value_krw else 0.0,
                day_change_krw=row.day_change_krw,
                day_change_pct=row.day_change_pct,
                total_pnl_krw=row.total_pnl_krw,
                total_pnl_pct=row.total_pnl_pct,
                status=str(holding.get("quote_status") or "missing"),
            )
        )
    if max_assets is not None:
        asset_rows = asset_rows[:max_assets]

    cash_rows = []
    if metrics.cash.cash_krw > 0:
        cash_rows.append(
            CashRowView(
                currency="KRW",
                amount=metrics.cash.cash_krw,
                value_krw=metrics.cash.cash_krw,
                weight=metrics.cash.cash_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0,
                fx_rate=1.0,
            )
        )
    if metrics.cash.cash_usd > 0:
        value = metrics.cash.cash_usd * metrics.usd_krw
        cash_rows.append(
            CashRowView(
                currency="USD",
                amount=metrics.cash.cash_usd,
                value_krw=value,
                weight=value / metrics.total_value_krw if metrics.total_value_krw else 0.0,
                fx_rate=metrics.usd_krw,
            )
        )

    alerts: list[str] = []
    if metrics.failed_quote_count:
        alerts.append(f"가격 조회 실패 {metrics.failed_quote_count}건")
    if metrics.missing_quote_count:
        alerts.append(f"가격 미조회 {metrics.missing_quote_count}건")
    if metrics.stale_quote_count:
        alerts.append(f"이전 저장 가격 사용 {metrics.stale_quote_count}건")
    if metrics.cash.cash_krw < 0 or metrics.cash.cash_usd < 0:
        alerts.append("현금 잔고가 음수입니다.")

    return DashboardViewModel(
        total_asset_krw=metrics.total_value_krw,
        investment_value_krw=metrics.total_position_value_krw,
        cash_value_krw=metrics.cash_total_krw,
        cash_weight=metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0,
        day_change_krw=metrics.day_change_krw,
        day_change_pct=metrics.day_change_pct,
        usd_krw=metrics.usd_krw,
        priced_count=metrics.priced_count,
        holdings_count=metrics.holdings_count,
        failed_quote_count=metrics.failed_quote_count,
        missing_quote_count=metrics.missing_quote_count,
        stale_quote_count=metrics.stale_quote_count,
        last_price_refresh_at=metrics.last_price_refresh_at,
        asset_rows=tuple(asset_rows),
        cash_rows=tuple(cash_rows),
        profit_summary=build_profit_summary_view(metrics=metrics, transactions=transactions, cash_ledger=cash_ledger, period=period),
        alerts=tuple(alerts),
        is_empty=metrics.holdings_count == 0 and metrics.cash_total_krw <= 0,
    )
