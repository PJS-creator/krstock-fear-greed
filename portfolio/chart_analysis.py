from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd


POLICY_VERSION = "tp-policy-v0.7.0"
EVIDENCE_VERSION = "tp-evidence-v0.7.0"
TOP_RULE_ID = "flow-rule-5d26405bc64e"
MINIMUM_INPUT_ROWS = 300
READINESS_ELIGIBLE_ROWS = 200
RECOMMENDED_INPUT_ROWS = 500
TOP_COMPONENT_IDS = ("A1", "A2", "A3", "A4", "A5", "A6", "A7")


class ChartAnalysisError(ValueError):
    pass


@dataclass(frozen=True)
class AnalysisInstrument:
    market: str
    symbol: str
    display_name: str

    @property
    def key(self) -> str:
        return f"{self.market}:{self.symbol}"


@dataclass(frozen=True)
class DailyHistoryInput:
    instrument: AnalysisInstrument
    frame: pd.DataFrame | None
    provider: str = ""
    adjustment_mode: str = ""
    source_symbol: str = ""
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class ChartScoreSnapshot:
    as_of_session: date
    top_score: float
    bottom_score: float
    top_components: Mapping[str, bool]
    bottom_components: Mapping[str, float]
    top_flow_break: bool
    top_damage_observed: bool
    bottom_watch: bool
    direction_conflict: bool
    verdict: str


@dataclass(frozen=True)
class ChartAnalysisResult:
    instrument: AnalysisInstrument
    readiness: str
    provider: str = ""
    adjustment_mode: str = ""
    source_symbol: str = ""
    rows: int = 0
    eligible_rows: int = 0
    source_sha256: str = ""
    quality_status: str = "ERROR"
    warnings: tuple[str, ...] = ()
    error: str | None = None
    latest: ChartScoreSnapshot | None = None
    previous: ChartScoreSnapshot | None = None
    recent: tuple[ChartScoreSnapshot, ...] = ()

    @property
    def top_delta(self) -> float | None:
        if self.latest is None or self.previous is None:
            return None
        return round(self.latest.top_score - self.previous.top_score, 2)

    @property
    def bottom_delta(self) -> float | None:
        if self.latest is None or self.previous is None:
            return None
        return round(self.latest.bottom_score - self.previous.bottom_score, 2)


def score_top_conditions(conditions: Mapping[str, object] | list[object] | tuple[object, ...]) -> float:
    if isinstance(conditions, Mapping):
        values = [bool(conditions.get(component)) for component in TOP_COMPONENT_IDS]
    else:
        values = [bool(value) for value in conditions]
    if len(values) != len(TOP_COMPONENT_IDS):
        raise ValueError("top score requires exactly seven conditions")
    return round(sum(values) * 100.0 / len(TOP_COMPONENT_IDS), 2)


def calculate_bottom_evidence_score(
    drawdown_63: float,
    near_low_20: float,
    rsi14: float,
) -> tuple[float, dict[str, float], bool]:
    values = (drawdown_63, near_low_20, rsi14)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("bottom score inputs must be finite")
    drawdown_component = 40.0 * float(np.clip(float(drawdown_63) / 0.25, 0.0, 1.0))
    near_low_component = 30.0 * float(np.clip(1.0 - float(near_low_20) / 0.20, 0.0, 1.0))
    rsi_component = 30.0 * float(np.clip((50.0 - float(rsi14)) / 20.0, 0.0, 1.0))
    components = {
        "drawdown": round(drawdown_component, 6),
        "near_low": round(near_low_component, 6),
        "rsi": round(rsi_component, 6),
    }
    score = round(float(np.clip(sum(components.values()), 0.0, 100.0)), 2)
    watch = float(drawdown_63) >= 0.25 and float(near_low_20) <= 0.04 and float(rsi14) <= 30.0
    return score, components, watch


def _wilder_average(values: pd.Series, period: int) -> pd.Series:
    result = pd.Series(np.nan, index=values.index, dtype=float)
    numeric = values.astype(float).to_numpy()
    if len(numeric) < period:
        return result
    average = float(np.mean(numeric[:period]))
    result.iloc[period - 1] = average
    for index in range(period, len(numeric)):
        average = ((period - 1) * average + float(numeric[index])) / period
        result.iloc[index] = average
    return result


def _wilder_rsi(values: pd.Series, period: int = 14) -> pd.Series:
    result = pd.Series(np.nan, index=values.index, dtype=float)
    numeric = values.astype(float).to_numpy()
    if len(numeric) <= period:
        return result
    changes = np.diff(numeric)
    gains = np.maximum(changes, 0.0)
    losses = np.maximum(-changes, 0.0)
    average_gain = float(np.mean(gains[:period]))
    average_loss = float(np.mean(losses[:period]))

    def rsi_value(gain: float, loss: float) -> float:
        if gain == 0.0 and loss == 0.0:
            return 50.0
        if loss == 0.0:
            return 100.0
        relative_strength = gain / loss
        return 100.0 - 100.0 / (1.0 + relative_strength)

    result.iloc[period] = rsi_value(average_gain, average_loss)
    for value_index in range(period + 1, len(numeric)):
        change_index = value_index - 1
        average_gain = ((period - 1) * average_gain + float(gains[change_index])) / period
        average_loss = ((period - 1) * average_loss + float(losses[change_index])) / period
        result.iloc[value_index] = rsi_value(average_gain, average_loss)
    return result


def validate_daily_bars(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ChartAnalysisError("일봉 데이터가 없습니다.")
    normalized = frame.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in normalized.columns]
    if "timestamp" in normalized.columns:
        timestamps = pd.to_datetime(normalized.pop("timestamp"), errors="coerce")
    elif "date" in normalized.columns:
        timestamps = pd.to_datetime(normalized.pop("date"), errors="coerce")
    else:
        timestamps = pd.to_datetime(normalized.index, errors="coerce")
    if bool(pd.isna(timestamps).any()):
        raise ChartAnalysisError("파싱할 수 없는 거래일이 있습니다.")
    normalized.insert(0, "session", [timestamp.date() for timestamp in timestamps])
    required_columns = ("open", "high", "low", "close", "volume")
    missing = [column for column in required_columns if column not in normalized.columns]
    if missing:
        raise ChartAnalysisError("필수 일봉 열이 없습니다: " + ", ".join(missing))
    for column in required_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if normalized[list(required_columns)].isna().any().any():
        raise ChartAnalysisError("OHLCV에 결측 또는 비숫자 값이 있습니다.")
    finite_values = normalized[list(required_columns)].to_numpy(dtype=float)
    if not bool(np.isfinite(finite_values).all()):
        raise ChartAnalysisError("OHLCV에 유한하지 않은 값이 있습니다.")
    if bool((normalized[["open", "high", "low", "close"]] <= 0).any().any()) or bool((normalized["volume"] < 0).any()):
        raise ChartAnalysisError("가격은 양수이고 거래량은 0 이상이어야 합니다.")
    if bool((normalized["low"] > normalized["high"]).any()):
        raise ChartAnalysisError("저가가 고가보다 큰 행이 있습니다.")
    if bool(((normalized["open"] < normalized["low"]) | (normalized["open"] > normalized["high"])).any()):
        raise ChartAnalysisError("시가가 고가·저가 범위를 벗어난 행이 있습니다.")
    if bool(((normalized["close"] < normalized["low"]) | (normalized["close"] > normalized["high"])).any()):
        raise ChartAnalysisError("종가가 고가·저가 범위를 벗어난 행이 있습니다.")
    normalized = normalized.sort_values("session", kind="stable").reset_index(drop=True)
    if bool(normalized["session"].duplicated().any()):
        raise ChartAnalysisError("중복된 거래일이 있습니다.")

    warnings: list[str] = []
    if "traded_value" in normalized.columns:
        normalized["traded_value"] = pd.to_numeric(normalized["traded_value"], errors="coerce")
        if normalized["traded_value"].isna().any():
            raise ChartAnalysisError("제공된 거래대금 열에 결측 또는 비숫자 값이 있습니다.")
        if bool((normalized["traded_value"] < 0).any()) or not bool(np.isfinite(normalized["traded_value"]).all()):
            raise ChartAnalysisError("거래대금은 유한한 0 이상 값이어야 합니다.")
    else:
        normalized["traded_value"] = (
            (normalized["high"] + normalized["low"] + normalized["close"]) / 3.0 * normalized["volume"]
        )
        warnings.append("APPROXIMATED_TRADED_VALUE")
    normalized["decision_eligible"] = normalized["volume"] > 0
    if int((~normalized["decision_eligible"]).sum()) > 0:
        warnings.append("ZERO_VOLUME_SESSION_PRESENT")
    return normalized, tuple(warnings)


def _most_recent_peak_position(highs: pd.Series, current_position: int) -> int:
    start = max(0, current_position - 19)
    window = highs.iloc[start : current_position + 1]
    maximum = float(window.max())
    matching = np.flatnonzero(np.isclose(window.to_numpy(dtype=float), maximum, rtol=0.0, atol=0.0))
    return start + int(matching[-1])


def _verdict(top_flow: bool, top_damage: bool, bottom_watch: bool) -> tuple[str, bool]:
    top_active = top_flow or top_damage
    if top_active and bottom_watch:
        return "방향 충돌 · 고점 훼손/저점 투매", True
    if top_flow and top_damage:
        return "고점 흐름 훼손 · 손상 관찰", False
    if top_flow:
        return "고점 흐름 훼손", False
    if top_damage:
        return "고점 손상 관찰", False
    if bottom_watch:
        return "저점권 투매 관찰", False
    return "특이 조건 없음", False


def calculate_chart_score_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    bars, warnings = validate_daily_bars(frame)
    close = bars["close"].astype(float)
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = _wilder_average(true_range, 14)
    rsi14 = _wilder_rsi(close, 14)
    ema5 = close.ewm(span=5, adjust=False, min_periods=5).mean()
    log_returns = np.log(close / previous_close)
    sigma20 = log_returns.rolling(window=20, min_periods=20).std(ddof=0)
    risk_unit = pd.concat([atr14 / close, 1.25 * sigma20], axis=1).max(axis=1)
    daily_returns = close.pct_change(fill_method=None)
    eligible_count = bars["decision_eligible"].astype(int).cumsum()

    scored = bars.copy()
    scored["atr14"] = atr14
    scored["rsi14"] = rsi14
    scored["ema5"] = ema5
    scored["sigma20"] = sigma20
    scored["risk_unit"] = risk_unit
    scored["eligible_count"] = eligible_count
    for column in (
        "top_score",
        "bottom_score",
        "drawdown_63",
        "near_low_20",
        "bottom_drawdown_component",
        "bottom_near_low_component",
        "bottom_rsi_component",
    ):
        scored[column] = np.nan
    for component in TOP_COMPONENT_IDS:
        scored[f"top_{component}"] = False
    scored["top_flow_break"] = False
    scored["top_damage_observed"] = False
    scored["bottom_watch"] = False
    scored["direction_conflict"] = False
    scored["verdict"] = "준비 중"

    for current in range(len(scored)):
        if not bool(scored.at[current, "decision_eligible"]):
            scored.at[current, "verdict"] = "세션 부적격"
            continue
        if int(eligible_count.iloc[current]) < READINESS_ELIGIBLE_ROWS:
            continue
        peak = _most_recent_peak_position(high, current)
        peak_age = current - peak
        risk_at_peak = float(risk_unit.iloc[peak])
        current_atr_fraction = float(atr14.iloc[current] / close.iloc[current])
        current_ema5 = float(ema5.iloc[current])
        current_rsi = float(rsi14.iloc[current])
        if not all(math.isfinite(value) for value in (risk_at_peak, current_atr_fraction, current_ema5, current_rsi)):
            continue
        prior_low = float(low.iloc[max(0, peak - 20) : peak + 1].min())
        runup = float(high.iloc[peak] / prior_low - 1.0)
        required_runup = max(0.05, 1.5 * risk_at_peak)
        damage_target = float(np.clip(3.0 * risk_at_peak, 0.07, 0.15))
        drawdown = float(1.0 - close.iloc[current] / high.iloc[peak])
        progress = drawdown / damage_target if damage_target > 0 else float("nan")
        speed = drawdown / (risk_at_peak * max(peak_age, 1)) if risk_at_peak > 0 else float("nan")
        z3 = float("nan")
        if current >= 3 and current_atr_fraction > 0:
            z3 = float((close.iloc[current] / close.iloc[current - 3] - 1.0) / (current_atr_fraction * math.sqrt(3.0)))
        flow_start = max(0, current - 9)
        flow_values = scored["traded_value"].iloc[flow_start : current + 1]
        flow_returns = daily_returns.iloc[flow_start : current + 1]
        total_flow = float(flow_values.sum())
        down_flow_share = float(flow_values[flow_returns < 0].sum() / total_flow) if total_flow > 0 else float("nan")
        conditions = {
            "A1": 1 <= peak_age <= 8,
            "A2": runup >= required_runup,
            "A3": math.isfinite(progress) and 0.45 <= progress <= 0.80,
            "A4": math.isfinite(speed) and speed >= 0.25,
            "A5": math.isfinite(z3) and z3 <= -0.60,
            "A6": float(close.iloc[current]) <= current_ema5,
            "A7": math.isfinite(down_flow_share) and down_flow_share >= 0.50,
        }
        top_score = score_top_conditions(conditions)
        top_flow = all(conditions.values())
        eligible_path = scored.iloc[peak + 1 : current + 1]
        eligible_path = eligible_path[eligible_path["decision_eligible"]]
        path_damage = float("nan")
        if not eligible_path.empty:
            path_damage = float(1.0 - eligible_path["low"].min() / high.iloc[peak])
        top_damage = bool(
            conditions["A2"]
            and 1 <= peak_age <= 10
            and math.isfinite(path_damage)
            and path_damage >= damage_target
        )

        high63 = float(high.iloc[max(0, current - 62) : current + 1].max())
        low20 = float(low.iloc[max(0, current - 19) : current + 1].min())
        drawdown_63 = float(1.0 - close.iloc[current] / high63)
        near_low_20 = float(close.iloc[current] / low20 - 1.0)
        bottom_score, bottom_components, bottom_watch = calculate_bottom_evidence_score(
            drawdown_63,
            near_low_20,
            current_rsi,
        )
        verdict, direction_conflict = _verdict(top_flow, top_damage, bottom_watch)
        scored.at[current, "top_score"] = top_score
        scored.at[current, "bottom_score"] = bottom_score
        scored.at[current, "drawdown_63"] = drawdown_63
        scored.at[current, "near_low_20"] = near_low_20
        scored.at[current, "bottom_drawdown_component"] = bottom_components["drawdown"]
        scored.at[current, "bottom_near_low_component"] = bottom_components["near_low"]
        scored.at[current, "bottom_rsi_component"] = bottom_components["rsi"]
        for component, active in conditions.items():
            scored.at[current, f"top_{component}"] = active
        scored.at[current, "top_flow_break"] = top_flow
        scored.at[current, "top_damage_observed"] = top_damage
        scored.at[current, "bottom_watch"] = bottom_watch
        scored.at[current, "direction_conflict"] = direction_conflict
        scored.at[current, "verdict"] = verdict
    return scored, warnings


def _snapshot_from_row(row: pd.Series) -> ChartScoreSnapshot:
    return ChartScoreSnapshot(
        as_of_session=row["session"],
        top_score=round(float(row["top_score"]), 2),
        bottom_score=round(float(row["bottom_score"]), 2),
        top_components={component: bool(row[f"top_{component}"]) for component in TOP_COMPONENT_IDS},
        bottom_components={
            "drawdown": round(float(row["bottom_drawdown_component"]), 2),
            "near_low": round(float(row["bottom_near_low_component"]), 2),
            "rsi": round(float(row["bottom_rsi_component"]), 2),
        },
        top_flow_break=bool(row["top_flow_break"]),
        top_damage_observed=bool(row["top_damage_observed"]),
        bottom_watch=bool(row["bottom_watch"]),
        direction_conflict=bool(row["direction_conflict"]),
        verdict=str(row["verdict"]),
    )


def _source_hash(frame: pd.DataFrame) -> str:
    columns = ["session", "open", "high", "low", "close", "volume", "traded_value"]
    payload = frame[columns].to_csv(index=False, lineterminator="\n", float_format="%.10g").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def analyze_daily_history(history: DailyHistoryInput) -> ChartAnalysisResult:
    if history.error or history.frame is None:
        return ChartAnalysisResult(
            instrument=history.instrument,
            readiness="ERROR",
            provider=history.provider,
            adjustment_mode=history.adjustment_mode,
            source_symbol=history.source_symbol,
            warnings=history.warnings,
            error=history.error or "일봉 데이터를 불러오지 못했습니다.",
        )
    try:
        scored, validation_warnings = calculate_chart_score_frame(history.frame)
    except (ChartAnalysisError, ValueError, TypeError) as exc:
        return ChartAnalysisResult(
            instrument=history.instrument,
            readiness="ERROR",
            provider=history.provider,
            adjustment_mode=history.adjustment_mode,
            source_symbol=history.source_symbol,
            warnings=history.warnings,
            error=str(exc),
        )
    rows = len(scored)
    eligible_rows = int(scored["decision_eligible"].sum())
    warnings = tuple(dict.fromkeys((*history.warnings, *validation_warnings)))
    source_sha256 = _source_hash(scored)
    common: dict[str, Any] = {
        "instrument": history.instrument,
        "provider": history.provider,
        "adjustment_mode": history.adjustment_mode,
        "source_symbol": history.source_symbol,
        "rows": rows,
        "eligible_rows": eligible_rows,
        "source_sha256": source_sha256,
        "warnings": warnings,
    }
    if rows < MINIMUM_INPUT_ROWS:
        return ChartAnalysisResult(
            **common,
            readiness="WARMUP",
            quality_status="WARNING",
            error=f"일봉 {rows}개로 입력 최소 {MINIMUM_INPUT_ROWS}개보다 부족합니다.",
        )
    if eligible_rows < READINESS_ELIGIBLE_ROWS:
        return ChartAnalysisResult(
            **common,
            readiness="WARMUP",
            quality_status="WARNING",
            error=f"적격 일봉 {eligible_rows}개로 준비 기준 {READINESS_ELIGIBLE_ROWS}개보다 부족합니다.",
        )
    latest_row = scored.iloc[-1]
    if not bool(latest_row["decision_eligible"]):
        return ChartAnalysisResult(
            **common,
            readiness="READY_INELIGIBLE",
            quality_status="WARNING",
            error="직전 완료 세션의 거래량이 0이라 판정 대상에서 제외했습니다.",
        )
    ready_rows = scored[
        scored["decision_eligible"]
        & scored["top_score"].notna()
        & scored["bottom_score"].notna()
    ]
    if ready_rows.empty or int(ready_rows.index[-1]) != len(scored) - 1:
        return ChartAnalysisResult(
            **common,
            readiness="WARMUP",
            quality_status="WARNING",
            error="직전 완료 세션의 점수를 계산할 준비가 되지 않았습니다.",
        )
    snapshots = tuple(_snapshot_from_row(row) for _, row in ready_rows.tail(5).iterrows())
    latest = snapshots[-1]
    previous = snapshots[-2] if len(snapshots) >= 2 else None
    return ChartAnalysisResult(
        **common,
        readiness="READY_ELIGIBLE",
        quality_status="PASS" if not warnings else "WARNING",
        latest=latest,
        previous=previous,
        recent=snapshots,
    )
