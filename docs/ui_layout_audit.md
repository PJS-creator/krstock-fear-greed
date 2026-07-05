# UI Layout Audit

This audit uses the 2026-07-05 dark-mode screenshots as the visual regression baseline. The goal is layout polish only: spacing, alignment, readable tables/charts, and responsive stability without changing portfolio calculations, Supabase Auth/RLS, or the data model.

## Current Common Layout

- Sidebar: data and auth controls are in the Streamlit sidebar. Public user data is still gated by Supabase Auth/RLS.
- App header: app title, theme toggle, price/fx refresh action, and refresh timestamp are rendered through the shared header component.
- Status area: refresh result banner and data update detail expander sit below the header.
- Main tabs: `총괄현황`, `세부내역`, `사용자입력`, `자산추이`, `매매일지`, `리밸런싱`.
- Sub tabs: `사용자입력` and `자산추이` use secondary tab bars.
- Section cards: summary, metric, form, and table sections are primarily Streamlit containers plus shared CSS.
- Tables: Streamlit dataframe/data_editor are used heavily. Several views had too many default columns.
- Charts: Plotly charts share theme tokens but needed stronger common margins and axis sizing.
- Forms: Streamlit forms are used for trades, cash movements, FX conversion, CSV import, and historical reconstruction.

## Screen Findings And Fix Direction

### 총괄현황

- Finding: holding table showed too many columns by default, causing dense headers and clipped content.
- Fix: keep summary table to core columns; move sparkline/IRR-like detail out of the default table.
- Finding: small heatmap tiles could show clipped labels.
- Fix: hide tile label/change text below a minimum area threshold.
- Finding: bottom KPI cards can sit under Streamlit Cloud operator overlay.
- Fix: add global bottom safe-area padding.

### 세부내역

- Finding: donut, currency exposure, and contribution charts need consistent margins and font sizes.
- Fix: shared Plotly layout uses stable margins, 12px tick fonts, and automargins.
- Finding: diagnosis cards need consistent gap and row height.
- Fix: metric/card CSS now uses shared size and spacing tokens.

### 사용자입력 > 보유 현황

- Finding: filter row baseline was uneven.
- Fix: filter columns now use small gaps and bottom vertical alignment.
- Finding: price status labels were too long.
- Fix: long labels such as `정상_최근종가` are shortened for table display.

### 사용자입력 > 현금·입출금·환율

- Finding: cash/FX forms had too many inputs in one row and inconsistent button baseline.
- Fix: movement and FX forms are split into stable rows with bottom alignment.
- Finding: cash ledger could grow without stable height.
- Fix: ledger table uses tokenized row height and max height.

### 사용자입력 > 거래 입력

- Finding: desktop one-row trade form was too dense and form controls did not align well.
- Fix: standard trade form uses two rows and aligned detail options.
- Finding: advanced input/editor sections needed consistent spacing.
- Fix: shared expander/table/input CSS applies tokenized padding and row heights.

### 사용자입력 > CSV

- Finding: upload and download controls had inconsistent button sizing.
- Fix: download/file uploader buttons use shared control tokens.

### 자산추이 > 실제 기록

- Finding: chart x-axis and legend needed stable spacing.
- Fix: shared chart layout adds automargins, fixed height variants, and bounded tick count.

### 자산추이 > 성과분석

- Finding: performance metric cards had long explanations and dense tables.
- Fix: metric help text is clamped; symbol/monthly tables now show core columns by default with detail toggles.
- Finding: side-by-side charts needed consistent height/margins.
- Fix: shared chart height and margin tokens are used.

### 자산추이 > 리스크분석

- Finding: MDD cards could be uneven and data with only a few observations looked overconfident.
- Fix: metric columns use consistent gaps; a warning appears when MDD has fewer than 5 observations.
- Finding: drawdown y-axis labels needed more room.
- Fix: shared chart layout uses larger left margin and automargins.

### 자산추이 > 과거 보유현황 재구성

- Finding: schedule controls, upload columns, and date controls had inconsistent width and baseline.
- Fix: key column rows now use small gaps and bottom alignment.
- Finding: long form sections need predictable vertical rhythm.
- Fix: shared token spacing applies to expanders, buttons, inputs, and data editors.

### 매매일지

- Finding: summary cards and filter chips looked separate from the common grid rhythm.
- Fix: summary/filter/note columns use shared small gaps and bottom alignment.
- Finding: event card spacing was loose.
- Fix: journal event CSS uses compact tokenized padding and gap.

### 리밸런싱

- Finding: result table exposed too many columns by default.
- Fix: result table now defaults to core columns and exposes detail columns via toggle.
- Finding: calculation mode buttons were vertically stacked and visually inconsistent.
- Fix: calculation mode uses horizontal segmented radio buttons.
- Finding: tiny rounding deltas could create meaningless `-1주` adjustments.
- Fix: deltas below the minimum amount/weight threshold keep the action at `유지`.

## Common Issues

- Text clipping: most visible in dense tables, chart labels, and small heatmap tiles.
- Table density: holdings, rebalancing, performance, ledger, and historical reconstruction tables needed core/detail separation.
- Button inconsistency: fixed by shared height/radius tokens and explicit row alignment.
- Widget baseline mismatch: fixed in trade, cash, FX, historical, filter, and journal rows.
- Chart clipping: fixed through common Plotly margins, automargin, and height variants.
- Card height mismatch: metric cards and Streamlit metric styling use shared sizes and gaps.
- Excess/insufficient spacing: page, card, section, table, and bottom safe area tokens were added.
- Tab alignment: primary and secondary tab bars use shared tokenized CSS with mobile horizontal scroll.
- Mobile risk: grid/flex media queries reduce overflow and stack horizontal blocks where needed.

## Priorities

- P0: app shell, page width, tabs, bottom safe area, button/control sizes.
- P1: default table column reduction and chart margin/height cleanup.
- P2: screen-specific polish for trade, cash, journal, rebalancing, performance, and reconstruction views.
- P3: mobile/tablet wrapping and horizontal-scroll safety.

## Visual Regression Baseline

- Dark mode desktop: 1440px and above, using the 12 attached screenshots.
- Dark mode tablet: 1024px.
- Dark mode mobile: 390px.
- Light mode: final smoke check for the same screens after dark-mode polish.

## Manual Follow-Up

- Verify real Streamlit dataframe/data_editor rendering because column virtualization is browser-dependent.
- Verify Streamlit Cloud operator `Manage app` overlay does not cover final buttons, legends, or table rows.
- Capture post-change screenshots for the same 12 dark-mode screens before merging.
