from __future__ import annotations

from html import escape
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portfolio.analytics import build_portfolio_snapshot
from portfolio.sample_data import sample_portfolio


def krw(value: float) -> str:
    return f"₩{value:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:,.2f}%"


def render_dashboard() -> str:
    positions, quotes, usd_krw, cash_krw = sample_portfolio()
    snapshot = build_portfolio_snapshot(positions, quotes, usd_krw=usd_krw, cash_krw=cash_krw)
    rows = "".join(
        f"""
        <tr>
          <td>{escape(item.position.market)}</td>
          <td>{escape(item.position.symbol)}</td>
          <td>{escape(item.position.name)}</td>
          <td>{escape(item.position.strategy_tag)}</td>
          <td>{item.position.quantity:g}</td>
          <td>{item.quote.price:,.2f}</td>
          <td>{krw(item.market_value_krw)}</td>
          <td>{krw(item.day_pnl_krw)}</td>
          <td>{krw(item.total_pnl_krw)}</td>
          <td>{pct(item.weight)}</td>
          <td>{pct(item.target_gap)}</td>
        </tr>
        """
        for item in snapshot.positions
    )
    return f"""
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8" />
        <title>Personal Portfolio Control Panel</title>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 32px; background: #f7f8fb; color: #172033; }}
          .cards {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 16px; margin: 24px 0; }}
          .card {{ background: white; border-radius: 18px; padding: 18px; box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08); }}
          .label {{ color: #667085; font-size: 14px; }}
          .value {{ font-size: 24px; font-weight: 700; margin-top: 8px; }}
          table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 18px; overflow: hidden; }}
          th, td {{ padding: 12px; border-bottom: 1px solid #eaecf0; text-align: right; }}
          th:nth-child(-n+4), td:nth-child(-n+4) {{ text-align: left; }}
          th {{ background: #101828; color: white; }}
        </style>
      </head>
      <body>
        <h1>Personal Portfolio Control Panel</h1>
        <p>샘플 포트폴리오 기반 총자산/손익/비중 계산 MVP</p>
        <section class="cards">
          <div class="card"><div class="label">총자산</div><div class="value">{krw(snapshot.total_value_krw)}</div></div>
          <div class="card"><div class="label">오늘 손익</div><div class="value">{krw(snapshot.day_pnl_krw)}</div></div>
          <div class="card"><div class="label">총 손익</div><div class="value">{krw(snapshot.total_pnl_krw)} / {pct(snapshot.total_pnl_pct)}</div></div>
          <div class="card"><div class="label">현금 비중</div><div class="value">{pct(snapshot.cash_krw / snapshot.total_value_krw)}</div></div>
        </section>
        <h2>보유 종목</h2>
        <table>
          <thead><tr><th>시장</th><th>티커</th><th>종목명</th><th>전략</th><th>수량</th><th>현재가</th><th>평가액</th><th>일간손익</th><th>총손익</th><th>현재비중</th><th>비중차이</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </body>
    </html>
    """


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = render_dashboard().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8501) -> None:
    HTTPServer((host, port), DashboardHandler).serve_forever()


if __name__ == "__main__":
    run()
