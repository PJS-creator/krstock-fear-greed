from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

import pandas as pd
import streamlit as st

from portfolio.rebalancing import (
    RebalancePlan,
    calculate_rebalancing_plan,
    default_target_allocations_from_portfolio,
    is_negligible_rebalance_delta,
    normalize_target_allocations,
    target_weight_sum,
)

from .components import render_empty_state
from .formatters import format_number, full_krw, percentage, signed_krw
from .stability import begin_ui_action, finish_ui_action, request_app_rerun
from .theme import DIMENSIONS


MODE_LABELS = {
    "full": "목표까지 전체 조정",
    "deposit_only": "매도 없이 신규 입금",
    "cash_only": "현금 우선 사용",
}
MODE_BY_LABEL = {label: key for key, label in MODE_LABELS.items()}
RESULT_BASE_COLUMNS = ["자산", "현재 비중", "목표 비중", "차이 금액", "조정 수량", "조정 방향", "데이터 상태"]
RESULT_DETAIL_COLUMNS = ["자산 유형", "현재 평가액", "목표 평가액", "현재 수량", "예상 조정 금액", "조정 후 예상 비중"]


def _editor_rows(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    editor_rows = []
    for row in rows:
        asset_type = "현금" if row.get("asset_type") == "cash" else "종목"
        editor_rows.append(
            {
                "asset_type": asset_type,
                "display_name": row.get("display_name") or row.get("symbol") or "",
                "symbol": "" if row.get("asset_type") == "cash" else row.get("symbol") or "",
                "market": row.get("market") or "",
                "currency": row.get("currency") or "",
                "target_weight_pct": float(row.get("target_weight_pct") or 0.0),
                "current_price": row.get("current_price"),
                "is_enabled": bool(row.get("is_enabled", True)),
            }
        )
    return editor_rows


def _initial_target_rows(
    *,
    holdings: list[dict[str, object]],
    target_allocations: list[dict[str, object]],
    cash_krw: float,
    cash_usd: float,
    usd_krw: float,
    total_asset_krw: float,
) -> list[dict[str, object]]:
    if target_allocations:
        try:
            return normalize_target_allocations(target_allocations)
        except ValueError:
            return []
    return default_target_allocations_from_portfolio(
        holdings,
        cash_krw=cash_krw,
        cash_usd=cash_usd,
        usd_krw=usd_krw,
        total_asset_krw=total_asset_krw,
    )


def _rows_from_editor(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for row in frame.to_dict("records"):
        rows.append(
            {
                "asset_type": row.get("asset_type"),
                "display_name": row.get("display_name"),
                "symbol": row.get("symbol"),
                "market": row.get("market"),
                "currency": row.get("currency"),
                "target_weight_pct": row.get("target_weight_pct"),
                "current_price": row.get("current_price"),
                "is_enabled": row.get("is_enabled"),
            }
        )
    return rows


def _quantity_text(value: object) -> str:
    if value is None:
        return "-"
    number = float(value)
    return format_number(number, digits=4, trim=True)


def _adjustment_quantity_text(value: object) -> str:
    if value is None:
        return "-"
    number = int(value)
    if number == 0:
        return "0"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,}주"


def _result_frame(plan: RebalancePlan) -> pd.DataFrame:
    rows = []
    for row in plan.rows:
        display_delta = 0.0 if is_negligible_rebalance_delta(row.delta_krw, plan.total_asset_krw) else row.delta_krw
        rows.append(
            {
                "자산": row.display_name,
                "자산 유형": "현금" if row.asset_type == "cash" else "종목",
                "현재 비중": f"{row.current_weight_pct:.2f}%",
                "목표 비중": f"{row.target_weight_pct:.2f}%",
                "현재 평가액": full_krw(row.current_value_krw),
                "목표 평가액": full_krw(row.target_value_krw),
                "차이 금액": signed_krw(display_delta),
                "현재 수량": _quantity_text(row.current_quantity),
                "조정 수량": _adjustment_quantity_text(row.adjustment_quantity),
                "예상 조정 금액": signed_krw(row.estimated_adjustment_value_krw),
                "조정 후 예상 비중": f"{row.post_adjustment_weight_pct:.2f}%",
                "조정 방향": row.action,
                "데이터 상태": row.data_status,
            }
        )
    return pd.DataFrame(rows)


def rebalancing_empty_result_message(*, has_targets: bool, total_asset_krw: float, total_target_pct: float) -> tuple[str, str] | None:
    if not has_targets:
        return "목표 비중이 없습니다.", "목표 비중을 입력하면 현재 포트폴리오와의 차이를 계산합니다."
    if total_asset_krw <= 0:
        return "총자산이 0원이라 계산할 수 없습니다.", "현금 입금 또는 보유종목 입력 후 리밸런싱 결과를 확인할 수 있습니다."
    if total_target_pct <= 0:
        return "목표 비중을 입력하세요.", "합계가 100%가 되도록 목표 비중을 입력하면 계산 결과가 표시됩니다."
    return None


def _render_plan_summary(plan: RebalancePlan) -> None:
    col1, col2, col3, col4 = st.columns(4, gap="small")
    col1.metric("총자산", full_krw(plan.total_asset_krw), border=True)
    col2.metric("목표 합계", f"{plan.target_weight_sum_pct:.2f}%", delta="정상" if plan.weight_sum_ok else "확인 필요", delta_color="off", border=True)
    col3.metric("추가 입금", full_krw(plan.additional_deposit_krw), border=True)
    col4.metric("현금 한도", full_krw(plan.cash_budget_krw), help="현금 우선 사용 모드에서 조정량 산정에 쓰는 현금 범위입니다.", border=True)


def render_rebalancing(
    *,
    holdings: list[dict[str, object]],
    target_allocations: list[dict[str, object]],
    cash_krw: float,
    cash_usd: float,
    usd_krw: float,
    total_asset_krw: float,
    on_save: Callable[[list[dict[str, object]]], None],
) -> None:
    st.subheader("리밸런싱")
    st.caption("투자 조언이 아니라 사용자가 입력한 목표 비중 대비 필요한 조정량을 계산합니다.")
    has_assets = bool(holdings) or cash_krw > 0 or cash_usd > 0
    if not has_assets and not target_allocations:
        render_empty_state(
            "리밸런싱할 자산 데이터가 없습니다.",
            "보유종목을 입력하거나 KRW/USD 입금을 기록하면 목표 비중을 만들 수 있습니다.",
        )
        return

    initial_rows = _initial_target_rows(
        holdings=holdings,
        target_allocations=target_allocations,
        cash_krw=cash_krw,
        cash_usd=cash_usd,
        usd_krw=usd_krw,
        total_asset_krw=total_asset_krw,
    )
    editor_frame = pd.DataFrame(
        _editor_rows(initial_rows),
        columns=["asset_type", "display_name", "symbol", "market", "currency", "target_weight_pct", "current_price", "is_enabled"],
    )
    editor_frame["current_price"] = pd.to_numeric(editor_frame["current_price"], errors="coerce")

    action_col1, action_col2 = st.columns([1, 2], vertical_alignment="bottom")
    if action_col1.button("현재 보유 기준 행 생성", icon=":material/refresh:"):
        if not begin_ui_action("rebalance_defaults", payload={"holdings": holdings, "cash_krw": cash_krw, "cash_usd": cash_usd, "usd_krw": usd_krw}):
            return
        defaults = default_target_allocations_from_portfolio(
            holdings,
            cash_krw=cash_krw,
            cash_usd=cash_usd,
            usd_krw=usd_krw,
            total_asset_krw=total_asset_krw,
        )
        try:
            on_save(defaults)
        except Exception:
            finish_ui_action(success=False)
            raise
        request_app_rerun()
    action_col2.caption("보유 종목, KRW 현금, USD 현금 행을 자동으로 만들고 현재 비중을 기본 목표 비중으로 채웁니다.")

    edited = st.data_editor(
        editor_frame,
        key="target_allocations_editor",
        num_rows="dynamic",
        width="stretch",
        column_config={
            "asset_type": st.column_config.SelectboxColumn("자산 유형", options=["종목", "현금"], required=True),
            "display_name": st.column_config.TextColumn("자산", help="화면에 표시할 이름입니다."),
            "symbol": st.column_config.TextColumn("종목명 또는 티커", help="현금 행은 비워 두어도 됩니다."),
            "market": st.column_config.SelectboxColumn("시장", options=["", "KR", "US"], help="현금은 비워 둡니다."),
            "currency": st.column_config.SelectboxColumn("통화", options=["KRW", "USD"], required=True),
            "target_weight_pct": st.column_config.NumberColumn("목표 비중 %", min_value=0.0, max_value=100.0, step=0.1, format="%.2f"),
            "current_price": st.column_config.NumberColumn("현재가", min_value=0.0, step=0.01, help="현재 보유하지 않은 목표 종목의 수량 계산에 사용합니다."),
            "is_enabled": st.column_config.CheckboxColumn("사용", default=True),
        },
    )

    raw_rows = _rows_from_editor(edited)
    try:
        clean_rows = normalize_target_allocations(raw_rows)
        total_pct = target_weight_sum(clean_rows)
    except ValueError as exc:
        st.warning(f"목표 비중 입력을 확인하세요: {exc}")
        clean_rows = []
        total_pct = 0.0

    if clean_rows:
        if total_pct <= 0:
            st.info("아직 목표 비중을 입력하지 않았습니다. 각 자산의 목표 비중을 입력하면 저장과 계산이 가능합니다.")
        elif abs(total_pct - 100.0) <= 0.1:
            st.success(f"목표 비중 합계 {total_pct:.2f}%")
        else:
            st.warning(f"목표 비중 합계가 {total_pct:.2f}%입니다. 99.9~100.1% 범위를 벗어나면 저장하지 않습니다.")

    target_sum_ok = clean_rows and total_pct > 0 and abs(total_pct - 100.0) <= 0.1
    if st.button("목표 비중 저장", type="primary", disabled=not target_sum_ok):
        if begin_ui_action("rebalance_save_targets", payload=clean_rows):
            try:
                on_save(clean_rows)
                st.success("목표 비중을 저장했습니다. 공개 앱에서는 다음 자동 저장 시 계정 포트폴리오에 반영됩니다.")
            except Exception:
                finish_ui_action(success=False)
                raise
            request_app_rerun()

    st.subheader("계산 옵션")
    option_cols = st.columns([1.5, 1], vertical_alignment="bottom")
    selected_mode_label = option_cols[0].radio("계산 방식", list(MODE_BY_LABEL.keys()), horizontal=True, key="rebalance_mode")
    additional_deposit = option_cols[1].number_input("추가 입금 예정액", min_value=0.0, step=100_000.0, value=0.0, help="매도 없이 신규 입금 모드와 현금 우선 사용 모드에서 KRW 기준으로 반영합니다.")
    mode = MODE_BY_LABEL[str(selected_mode_label)]

    empty_result = rebalancing_empty_result_message(has_targets=bool(clean_rows), total_asset_krw=total_asset_krw, total_target_pct=total_pct)
    if empty_result is not None:
        render_empty_state(*empty_result)
        return
    try:
        plan = calculate_rebalancing_plan(
            target_allocations=clean_rows,
            holdings=holdings,
            cash_krw=cash_krw,
            cash_usd=cash_usd,
            usd_krw=usd_krw,
            total_asset_krw=total_asset_krw,
            mode=mode,
            additional_deposit_krw=additional_deposit,
        )
    except ValueError as exc:
        st.warning(f"리밸런싱 계산을 할 수 없습니다: {exc}")
        return

    _render_plan_summary(plan)
    result = _result_frame(plan)
    show_detail_columns = st.checkbox("결과 상세 열 보기", value=False, key="rebalance_result_show_detail")
    result_columns = RESULT_BASE_COLUMNS + (RESULT_DETAIL_COLUMNS if show_detail_columns else [])
    st.dataframe(
        result[result_columns],
        hide_index=True,
        width="stretch",
        height=min(DIMENSIONS.max_table_height, 100 + len(result) * DIMENSIONS.row_height),
    )
    st.caption("수수료와 세금 추정은 v1에서 0으로 둡니다. 실제 주문 전에는 사용자가 별도로 비용과 세금을 확인해야 합니다.")
