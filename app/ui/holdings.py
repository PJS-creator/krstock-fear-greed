from __future__ import annotations

import pandas as pd
import streamlit as st

from portfolio.holdings import HOLDING_COLUMNS, QUICK_INPUT_COLUMNS, PortfolioMetrics, merge_quick_rows_with_existing, normalize_holding_rows

from .styles import full_krw, pct

STATUS_LABELS = {
    "updated": "갱신됨",
    "cached": "캐시",
    "stale": "이전 가격 유지",
    "failed": "조회 실패",
    "missing": "가격 없음",
    "missing_api_key": "API key 없음",
    "manual": "수동",
}


def _quick_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=QUICK_INPUT_COLUMNS)
    return pd.DataFrame(
        [
            {
                "market": row.get("market") or "US",
                "ticker": row.get("ticker") or row.get("symbol"),
                "quantity": row.get("quantity"),
            }
            for row in rows
        ],
        columns=QUICK_INPUT_COLUMNS,
    )


def _advanced_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=HOLDING_COLUMNS)


def render_holdings_editor() -> None:
    st.subheader("빠른 입력")
    st.caption("market, ticker, quantity만 입력합니다. 미국은 US/USD, 국내는 KR/KRW로 처리하며 국내 ticker는 6자리 종목코드입니다. 가격 조회는 상단의 가격 새로고침 버튼을 눌렀을 때만 실행됩니다.")
    rows = st.session_state.get("holdings_rows", [])
    quick_frame = st.data_editor(
        _quick_frame(rows),
        key="quick_holdings_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "market": st.column_config.SelectboxColumn("market", options=["US", "KR"], required=True, help="US는 미국 주식, KR은 국내 주식입니다."),
            "ticker": st.column_config.TextColumn("ticker", required=True, help="국내 주식은 005930 같은 6자리 종목코드를 입력합니다."),
            "quantity": st.column_config.NumberColumn("quantity", min_value=0.0, step=0.0001, required=True),
        },
    )
    if st.button("입력 적용", type="primary"):
        try:
            st.session_state.holdings_rows = merge_quick_rows_with_existing(quick_frame.to_dict("records"), rows)
            st.session_state.holdings_message = "입력값을 적용했습니다. 가격 새로고침 버튼을 눌러 최근 제공 가격을 갱신하세요."
            st.rerun()
        except ValueError as exc:
            st.error(f"입력값을 적용할 수 없습니다: {exc}")

    message = st.session_state.pop("holdings_message", None)
    if message:
        st.success(message)

    with st.expander("고급 설정"):
        advanced = st.data_editor(
            _advanced_frame(st.session_state.get("holdings_rows", [])),
            key="advanced_holdings_editor",
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ticker": st.column_config.TextColumn("ticker", required=True),
                "quantity": st.column_config.NumberColumn("quantity", min_value=0.0, step=0.0001, required=True),
                "market": st.column_config.SelectboxColumn("market", options=["US", "KR"], required=True),
                "currency": st.column_config.SelectboxColumn("currency", options=["USD", "KRW"], required=True),
                "avg_price": st.column_config.NumberColumn("avg_price", min_value=0.0, step=0.01),
                "target_weight": st.column_config.NumberColumn("target_weight", min_value=0.0, max_value=1.0, step=0.01),
            },
        )
        if st.button("고급 설정 적용"):
            try:
                st.session_state.holdings_rows = normalize_holding_rows(advanced.to_dict("records"))
                st.rerun()
            except ValueError as exc:
                st.error(f"고급 설정을 적용할 수 없습니다: {exc}")


def render_holdings_table(metrics: PortfolioMetrics) -> None:
    st.subheader("보유자산")
    rows = []
    for item in metrics.rows:
        holding = item.holding
        rows.append(
            {
                "ticker": holding["ticker"],
                "display_name": holding["display_name"],
                "market": holding["market"],
                "quantity": holding["quantity"],
                "currency": holding["currency"],
                "current_price": holding.get("current_price"),
                "market_value_krw": full_krw(item.market_value_krw),
                "day_change_krw": full_krw(item.day_change_krw),
                "day_change_pct": pct(item.day_change_pct),
                "weight": pct(item.weight),
                "quote_status": STATUS_LABELS.get(str(holding.get("quote_status")), str(holding.get("quote_status"))),
                "fetched_at": holding.get("fetched_at") or "미조회",
            }
        )
    if not rows:
        st.info("보유자산을 입력하면 표가 표시됩니다.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
