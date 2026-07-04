from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from portfolio.holdings import PortfolioMetrics


ALLOCATION_PERSPECTIVES = ("종목별", "유형별", "통화별", "계좌별")


@dataclass(frozen=True)
class AllocationRowView:
    key: str
    label: str
    detail: str
    value_krw: float
    weight: float
    kind: str
    currency: str
    members: int = 1


@dataclass(frozen=True)
class AllocationDiagnostics:
    hhi: float
    top3_weight: float
    max_single_weight: float
    usd_exposure_pct: float


@dataclass(frozen=True)
class AllocationViewModel:
    perspective: str
    total_value_krw: float
    rows: tuple[AllocationRowView, ...]
    diagnostics: AllocationDiagnostics
    has_data: bool
    empty_message: str | None = None


def _cash_rows(metrics: PortfolioMetrics) -> list[AllocationRowView]:
    rows: list[AllocationRowView] = []
    if metrics.cash.cash_krw > 0:
        rows.append(
            AllocationRowView(
                key="cash:KRW",
                label="원화 현금",
                detail="현금",
                value_krw=metrics.cash.cash_krw,
                weight=metrics.cash.cash_krw / metrics.total_value_krw if metrics.total_value_krw else 0.0,
                kind="cash",
                currency="KRW",
            )
        )
    if metrics.cash.cash_usd > 0:
        value = metrics.cash.cash_usd * metrics.usd_krw
        rows.append(
            AllocationRowView(
                key="cash:USD",
                label="달러 현금",
                detail="현금",
                value_krw=value,
                weight=value / metrics.total_value_krw if metrics.total_value_krw else 0.0,
                kind="cash",
                currency="USD",
            )
        )
    return rows


def _asset_rows(metrics: PortfolioMetrics) -> list[AllocationRowView]:
    rows: list[AllocationRowView] = []
    for item in metrics.rows:
        value = float(item.market_value_krw or 0.0)
        if value <= 0:
            continue
        holding = item.holding
        rows.append(
            AllocationRowView(
                key=f"{holding.get('market')}:{holding.get('ticker')}",
                label=str(holding.get("display_name") or holding.get("ticker")),
                detail=f"{holding.get('market')} · {holding.get('ticker')}",
                value_krw=value,
                weight=value / metrics.total_value_krw if metrics.total_value_krw else 0.0,
                kind="stock",
                currency=str(holding.get("currency") or ""),
            )
        )
    return rows


def _group_rows(rows: list[AllocationRowView], *, perspective: str, total: float) -> list[AllocationRowView]:
    grouped: dict[str, dict[str, object]] = defaultdict(lambda: {"value": 0.0, "members": 0, "kind": "", "currency": ""})
    for row in rows:
        if perspective == "유형별":
            key = "주식" if row.kind == "stock" else "현금"
            detail = "투자자산" if row.kind == "stock" else "KRW/USD 현금"
            kind = row.kind
            currency = row.currency
        elif perspective == "통화별":
            key = "USD 자산" if row.currency == "USD" else "KRW 자산"
            detail = f"{row.currency} 표시 자산"
            kind = row.kind
            currency = row.currency
        elif perspective == "계좌별":
            key = "기본 계좌"
            detail = "현재 앱은 계좌 구분을 기본 계좌로 집계합니다."
            kind = "account"
            currency = "KRW/USD"
        else:
            return rows
        bucket = grouped[key]
        bucket["value"] = float(bucket["value"]) + row.value_krw
        bucket["members"] = int(bucket["members"]) + row.members
        bucket["detail"] = detail
        bucket["kind"] = kind
        bucket["currency"] = currency
    return [
        AllocationRowView(
            key=key,
            label=key,
            detail=str(value["detail"]),
            value_krw=float(value["value"]),
            weight=float(value["value"]) / total if total else 0.0,
            kind=str(value["kind"]),
            currency=str(value["currency"]),
            members=int(value["members"]),
        )
        for key, value in grouped.items()
        if float(value["value"]) > 0
    ]


def collapse_small_allocations(
    rows: list[AllocationRowView],
    *,
    total_value_krw: float,
    max_rows: int = 8,
    min_weight: float = 0.02,
) -> list[AllocationRowView]:
    sorted_rows = sorted(rows, key=lambda row: row.value_krw, reverse=True)
    if len(sorted_rows) <= max_rows and all(row.weight >= min_weight for row in sorted_rows):
        return sorted_rows
    kept: list[AllocationRowView] = []
    other: list[AllocationRowView] = []
    for row in sorted_rows:
        if len(kept) < max_rows and row.weight >= min_weight:
            kept.append(row)
        else:
            other.append(row)
    if other:
        other_value = sum(row.value_krw for row in other)
        kept.append(
            AllocationRowView(
                key="other",
                label="기타",
                detail=f"{sum(row.members for row in other)}개 항목 합산",
                value_krw=other_value,
                weight=other_value / total_value_krw if total_value_krw else 0.0,
                kind="other",
                currency="mixed",
                members=sum(row.members for row in other),
            )
        )
    return kept


def _diagnostics(rows: list[AllocationRowView], metrics: PortfolioMetrics) -> AllocationDiagnostics:
    weights = [row.weight for row in rows]
    sorted_weights = sorted(weights, reverse=True)
    return AllocationDiagnostics(
        hhi=sum(weight * weight for weight in weights),
        top3_weight=sum(sorted_weights[:3]),
        max_single_weight=max(weights) if weights else 0.0,
        usd_exposure_pct=metrics.usd_exposure_pct,
    )


def build_allocation_view_model(
    metrics: PortfolioMetrics,
    *,
    perspective: str = "종목별",
    max_rows: int = 8,
    min_weight: float = 0.02,
) -> AllocationViewModel:
    if perspective not in ALLOCATION_PERSPECTIVES:
        perspective = "종목별"
    if metrics.total_value_krw <= 0:
        return AllocationViewModel(
            perspective=perspective,
            total_value_krw=0.0,
            rows=(),
            diagnostics=AllocationDiagnostics(hhi=0.0, top3_weight=0.0, max_single_weight=0.0, usd_exposure_pct=0.0),
            has_data=False,
            empty_message="총자산이 0원이라 비중을 계산할 수 없습니다.",
        )

    source_rows = _asset_rows(metrics) + _cash_rows(metrics)
    rows = _group_rows(source_rows, perspective=perspective, total=metrics.total_value_krw)
    if perspective == "종목별":
        rows = collapse_small_allocations(rows, total_value_krw=metrics.total_value_krw, max_rows=max_rows, min_weight=min_weight)
    rows = sorted(rows, key=lambda row: row.value_krw, reverse=True)
    return AllocationViewModel(
        perspective=perspective,
        total_value_krw=metrics.total_value_krw,
        rows=tuple(rows),
        diagnostics=_diagnostics(rows, metrics),
        has_data=bool(rows),
    )
