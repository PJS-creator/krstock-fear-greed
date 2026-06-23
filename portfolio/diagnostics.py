from __future__ import annotations

from dataclasses import dataclass

from .holdings import PortfolioMetrics


@dataclass(frozen=True)
class DiagnosticThresholds:
    high_single_position_weight: float = 0.30
    high_top3_weight: float = 0.65
    high_hhi: float = 0.18
    high_cash_weight: float = 0.35
    high_usd_exposure: float = 0.70
    low_cost_basis_coverage: float = 0.60


@dataclass(frozen=True)
class DiagnosticItem:
    key: str
    label: str
    value: str
    level: str
    message: str


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "데이터 부족"
    return f"{value * 100:.1f}%"


def _top_contributors(metrics: PortfolioMetrics, *, positive: bool) -> list[str]:
    rows = [row for row in metrics.rows if row.day_change_krw is not None]
    if positive:
        rows = [row for row in rows if (row.day_change_krw or 0.0) > 0]
        rows.sort(key=lambda row: row.day_change_krw or 0.0, reverse=True)
    else:
        rows = [row for row in rows if (row.day_change_krw or 0.0) < 0]
        rows.sort(key=lambda row: row.day_change_krw or 0.0)
    return [str(row.holding["ticker"]) for row in rows[:3]]


def calculate_diagnostics(
    metrics: PortfolioMetrics,
    thresholds: DiagnosticThresholds = DiagnosticThresholds(),
) -> list[DiagnosticItem]:
    if metrics.total_value_krw <= 0:
        return [
            DiagnosticItem(
                key="insufficient_data",
                label="진단",
                value="데이터 부족",
                level="info",
                message="평가 가능한 보유자산이나 현금 데이터가 아직 없습니다.",
            )
        ]

    weights = sorted((row.weight for row in metrics.rows if row.market_value_krw is not None), reverse=True)
    max_weight = weights[0] if weights else None
    top3_weight = sum(weights[:3]) if weights else None
    hhi = sum(weight * weight for weight in weights) if weights else None
    cash_weight = metrics.cash_total_krw / metrics.total_value_krw if metrics.total_value_krw else None
    cost_basis_coverage = metrics.cost_basis_coverage if metrics.total_position_value_krw else None
    gainers = _top_contributors(metrics, positive=True)
    losers = _top_contributors(metrics, positive=False)

    return [
        DiagnosticItem(
            key="max_position_weight",
            label="최대 단일 종목 비중",
            value=_fmt_pct(max_weight),
            level="warning" if max_weight is not None and max_weight >= thresholds.high_single_position_weight else "ok",
            message="단일 종목 평가액이 총자산에서 차지하는 비중입니다.",
        ),
        DiagnosticItem(
            key="top3_weight",
            label="상위 3개 종목 비중",
            value=_fmt_pct(top3_weight),
            level="warning" if top3_weight is not None and top3_weight >= thresholds.high_top3_weight else "ok",
            message="상위 보유 종목에 자산이 얼마나 집중되어 있는지 보여줍니다.",
        ),
        DiagnosticItem(
            key="hhi",
            label="HHI 집중도",
            value="데이터 부족" if hhi is None else f"{hhi:.3f}",
            level="warning" if hhi is not None and hhi >= thresholds.high_hhi else "ok",
            message="보유 비중 제곱합으로 계산한 집중도 지표입니다. 투자 권고가 아닌 상태 진단입니다.",
        ),
        DiagnosticItem(
            key="cash_weight",
            label="현금 비중",
            value=_fmt_pct(cash_weight),
            level="info" if cash_weight is not None and cash_weight >= thresholds.high_cash_weight else "ok",
            message="KRW 현금과 USD 현금을 KRW로 환산한 총현금 비중입니다.",
        ),
        DiagnosticItem(
            key="usd_exposure",
            label="USD 노출도",
            value=_fmt_pct(metrics.usd_exposure_pct),
            level="info" if metrics.usd_exposure_pct >= thresholds.high_usd_exposure else "ok",
            message="USD 현금과 USD 표시 자산의 KRW 환산 비중입니다.",
        ),
        DiagnosticItem(
            key="quote_freshness",
            label="가격 상태",
            value=f"정상 {metrics.priced_count} / stale {metrics.stale_quote_count} / 실패 {metrics.failed_quote_count}",
            level="warning" if metrics.stale_quote_count or metrics.failed_quote_count or metrics.missing_quote_count else "ok",
            message="최근 제공 가격을 기준으로 평가 가능한 종목 수와 stale/실패 상태를 보여줍니다.",
        ),
        DiagnosticItem(
            key="gain_contributors",
            label="오늘 상승 기여 상위",
            value=", ".join(gainers) if gainers else "데이터 부족",
            level="info",
            message="전일 종가와 최근 제공 가격 차이 기준의 상승 기여 종목입니다.",
        ),
        DiagnosticItem(
            key="loss_contributors",
            label="오늘 하락 기여 상위",
            value=", ".join(losers) if losers else "데이터 부족",
            level="info",
            message="전일 종가와 최근 제공 가격 차이 기준의 하락 기여 종목입니다.",
        ),
        DiagnosticItem(
            key="cost_basis_coverage",
            label="원가 정보 범위",
            value=_fmt_pct(cost_basis_coverage),
            level="warning" if cost_basis_coverage is not None and cost_basis_coverage < thresholds.low_cost_basis_coverage else "ok",
            message="원가 정보가 입력된 종목의 평가액이 전체 보유 평가액에서 차지하는 비중입니다.",
        ),
    ]
