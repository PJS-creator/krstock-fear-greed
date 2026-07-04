# UI Product Redesign Plan

## 1. Current Screen Structure

- Public entrypoint: `app/public_portfolio_dashboard.py`.
- Runtime app: `app/portfolio_dashboard.py`.
- Current public sections: `총괄현황`, `세부내역`, `사용자입력`, `자산추이`, `리밸런싱`.
- Current `총괄현황` is rendered by `app/ui/investment_summary_card.py`.
- Current `세부내역` is rendered by `app/ui/overview.py`.
- Current `자산추이` contains actual history, performance, risk, and historical reconstruction through `app/ui/history.py`.
- User data source of truth remains existing session state and Supabase-backed portfolio payload:
  - `holdings_rows`
  - `portfolio_transactions`
  - `cash_ledger_entries`
  - `target_allocations`
  - `usd_krw`, `cash_krw`, `cash_usd`

## 2. Current Summary Problems

- The first screen mixes hero information, allocation, heatmap, detailed holdings table, and KPI cards in one long section.
- Cash appears as one row inside portfolio composition, so investment assets and cash are not visually separated enough.
- Detailed tables appear too early for daily mobile use.
- Performance, allocation, risk, and history exist, but the navigation does not match how users usually ask questions: "how much do I have, what changed, where is profit, what is my allocation, what happened recently?"
- Empty states are present, but the summary still tends to feel table/chart-first.

## 3. Relationship Between Existing Details, History, Rebalancing, And New Analysis UI

- Existing detailed functions should not be removed.
- `세부내역` becomes part of a broader `분석` area.
- `성과분석`, `리스크분석`, and `실제 기록` stay available as analysis subviews.
- `리밸런싱` remains a top-level section because it is an action-oriented calculator.
- Historical reconstruction remains an advanced tool under analysis/history.

## 4. New Home Dashboard Information Architecture

1. Total asset hero
   - KRW total asset
   - daily gain/loss and daily return
   - price/fx status
   - last refresh
2. Quick analysis nav
   - 수익, 세금, 배당, 추이, 비중, 매매일지
3. Investment section
   - top holdings as mobile-first rows
   - sort controls
   - top 5 by default with expand option
   - detailed holdings table in an expander
4. Cash section
   - KRW cash
   - USD cash
   - KRW converted total cash
   - cash weight
5. Profit preview
   - unrealized, realized, dividends/interest, fees/taxes, total
6. Allocation preview
   - compact donut/bar and top rows
7. Alerts
   - price/fx failures, missing prices, negative cash, target weight issues, insufficient data

## 5. Profit Summary Card Structure

- Period selector: today, total, week, month, quarter, year, custom.
- v1 uses available current metrics and transaction/cash-ledger based performance totals.
- If period-specific data is insufficient, show `데이터 부족` instead of pretending the value is zero.
- Cards:
  - 평가수익
  - 실현수익
  - 배당/이자
  - 수수료/세금
  - 합계
- Detailed per-symbol rows stay in an expander or the full performance view.

## 6. Allocation Structure

- Perspectives:
  - 종목별
  - 유형별
  - 통화별
  - 계좌별
- Stocks and cash are both included in total allocation, but cash rows are styled separately.
- Zero total asset uses an empty state, not an empty chart.
- Small items collapse into `기타` for readability.
- Advanced diagnostics such as HHI, top 3 concentration, max single asset weight, and USD exposure stay in an expander.

## 7. Journal Structure

- Sources:
  - transactions
  - cash_ledger
  - journal_notes
- Buy/sell settlement ledger rows linked to transactions should not appear as duplicate timeline events.
- Independent deposit, withdrawal, dividend, interest, fee/tax, manual adjustment, and FX conversion events appear in the timeline.
- Manual notes are additive and use a new optional `journal_notes` structure.

## 8. Investment/Cash Separation Rendering Strategy

- Investment rows use `render_asset_row`.
- Cash rows use `render_cash_row`.
- The home screen renders investment and cash in separate section cards.
- Existing detailed holdings table remains in `상세 표 보기`.

## 9. Data Model Change

- Existing portfolio payload remains compatible.
- Additive optional `journal_notes` is introduced for manual timeline notes.
- Supabase migration adds `public.journal_notes` with RLS on `auth.uid() = user_id`.
- Existing `portfolio_snapshots.payload_json` can also carry `journal_notes` as a fallback so older deployments do not break.

## 10. Test Plan

- `tests/test_dashboard_view_model.py`
- `tests/test_profit_summary_view_model.py`
- `tests/test_allocation_view_model.py`
- `tests/test_journal_events.py`
- `tests/test_navigation_state.py`
- `tests/test_responsive_empty_states.py`
- Existing test suite must still pass.

## 11. Manual QA Plan

- Mobile 390px, tablet 768px, desktop 1440px.
- Dark and light themes.
- Empty account, sample mode, real data account.
- Price/fx failures and missing price states.
- Journal duplicate handling for transaction-linked settlement ledger rows.
- Manual note create/edit/delete.

## 12. Regression Prevention Points

- Public app must not use `SUPABASE_SERVICE_ROLE_KEY`.
- Supabase Auth user id remains the only public `owner_id`.
- `main` remains the public portfolio name.
- Existing detailed tables, CSV import/export, historical reconstruction, performance, risk, and rebalancing remain reachable.
- Additive migrations only; no destructive schema changes.
