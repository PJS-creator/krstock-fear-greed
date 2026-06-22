from __future__ import annotations

from pathlib import Path
import sys


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


_ensure_project_root_on_path()

import pandas as pd
import streamlit as st

from portfolio.analytics import build_portfolio_snapshot
from portfolio.sample_data import sample_portfolio


def krw(value: float) -> str:
    return f"₩{value:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:,.2f}%"


st.set_page_config(page_title="Personal Portfolio Control Panel", layout="wide")
st.title("Personal Portfolio Control Panel")
st.caption("샘플 포트폴리오 기반 준실시간 자산/손익/비중 계산 MVP")

positions, quotes, usd_krw, cash_krw = sample_portfolio()
with st.sidebar:
    st.header("MVP 입력값")
    usd_krw = st.number_input("USD/KRW", min_value=1.0, value=usd_krw, step=1.0)
    cash_krw = st.number_input("현금(KRW)", min_value=0.0, value=cash_krw, step=100000.0)
    st.info("현재 버전은 샘플 포트폴리오와 캐시된 Quote로 계산합니다. 다음 PR에서 API 공급자를 붙이면 됩니다.")

snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)

col1, col2, col3, col4 = st.columns(4)
col1.metric("총자산", krw(snapshot.total_value_krw))
col2.metric("오늘 손익", krw(snapshot.day_pnl_krw))
col3.metric("총 손익", krw(snapshot.total_pnl_krw), pct(snapshot.total_pnl_pct))
col4.metric("현금 비중", pct(snapshot.cash_krw / snapshot.total_value_krw if snapshot.total_value_krw else 0))

rows = []
for item in snapshot.positions:
    rows.append(
        {
            "시장": item.position.market,
            "티커": item.position.symbol,
            "종목명": item.position.name,
            "전략": item.position.strategy_tag,
            "수량": item.position.quantity,
            "평균단가": item.position.avg_price,
            "현재가": item.quote.price,
            "평가액(KRW)": round(item.market_value_krw),
            "일간손익(KRW)": round(item.day_pnl_krw),
            "총손익(KRW)": round(item.total_pnl_krw),
            "총수익률": item.total_pnl_pct,
            "현재비중": item.weight,
            "목표비중": item.position.target_weight,
            "비중차이": item.target_gap,
        }
    )

frame = pd.DataFrame(rows)
st.subheader("Action Board")
left, right = st.columns(2)
if not frame.empty:
    overweight = frame.sort_values("비중차이", ascending=False).iloc[0]
    underweight = frame.sort_values("비중차이", ascending=True).iloc[0]
    left.warning(f"목표 비중 초과: {overweight['종목명']} ({overweight['비중차이'] * 100:.2f}%p)")
    right.info(f"목표 비중 미달: {underweight['종목명']} ({underweight['비중차이'] * 100:.2f}%p)")

st.subheader("보유 종목")
st.dataframe(
    frame.style.format(
        {
            "평균단가": "{:,.2f}",
            "현재가": "{:,.2f}",
            "평가액(KRW)": "{:,.0f}",
            "일간손익(KRW)": "{:,.0f}",
            "총손익(KRW)": "{:,.0f}",
            "총수익률": "{:.2%}",
            "현재비중": "{:.2%}",
            "목표비중": "{:.2%}",
            "비중차이": "{:.2%}",
        }
    ),
    use_container_width=True,
)

st.subheader("전략 태그별 평가액")
tag_frame = frame.groupby("전략", as_index=False)["평가액(KRW)"].sum()
st.bar_chart(tag_frame, x="전략", y="평가액(KRW)")
