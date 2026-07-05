# Color System Audit

## Scope

The public app entry point is `app/public_portfolio_dashboard.py`, which loads the shared Streamlit dashboard in `app/portfolio_dashboard.py`.

This audit covers the Streamlit UI modules under `app/ui`, `.streamlit/config.toml`, and chart helpers used by the public dashboard.

## Current Color Inventory

Before this pass, colors appeared in these places:

- `app/ui/theme.py`: semantic colors, category colors, light/dark theme values, chart colors.
- `app/ui/styles.py`: Streamlit CSS overrides, buttons, tabs, alerts, dataframes, forms, mobile rules.
- `app/ui/charts.py`: Plotly transparent backgrounds, tooltip text, zero lines, allocation colors, currency colors.
- `app/ui/investment_summary_card.py`: summary heatmap color mixing, sparkline tones, KPI icon tones, cash/other colors.
- `.streamlit/config.toml`: Streamlit default primary and chart palette.
- `app/simple_dashboard.py`: legacy static fallback dashboard, not used by the public app.

## Duplicated Or Conflicting Meanings

- Profit and generic success were both green in some older paths.
- Loss and danger/error were both red in some older paths.
- Chart blue, link blue, loss blue, and primary blue were not clearly separated.
- Cash used amber/orange in some places and gray/slate in others.
- Allocation charts had a broader rainbow-like palette than needed.

## Low Contrast Risks

- Light mode table and form widgets could inherit Streamlit defaults that did not match the app shell.
- Dark mode chart tooltip text used hardcoded white while other chart text used theme values.
- Summary heatmap dark borders used pure black, making some tiles look harsher than the rest of the app.
- Some badge/alert colors depended on status names instead of explicit status tokens.

## Chart Issues

- Allocation and summary colors were deterministic but could feel too colorful.
- Currency exposure used a fixed currency map instead of theme tokens.
- Plotly axis, grid, tooltip, and zero-line colors were partly hardcoded.

## Table/Data Editor Issues

- Streamlit dataframe/data editor styling was already centralized in `app/ui/styles.py`, but the token set did not expose enough table-specific values.
- Header, row, hover, focus, and text colors now map to table/input/component tokens.

## Fix Priority

1. Define a complete token set with identical light/dark keys.
2. Separate investment P&L colors from success/error status colors.
3. Move chart palettes to theme tokens.
4. Replace summary heatmap/sparkline direct colors with tokens.
5. Add contrast and no-hardcoded-color tests.
6. Document remaining exceptions.

## Final Token Direction

- Primary: calm blue/navy family for brand, main buttons, active tabs, portfolio lines.
- Accent: teal for secondary emphasis and investment/cash split.
- Neutral: slate/blue-gray for surfaces, text, borders, tables, and cash.
- P&L: Korean investor convention, profit/up = rose/red, loss/down = blue.
- Status: success/warning/danger/info separated from P&L.
- Charts: limited allocation, diverging, and status palettes from theme tokens.

## Remaining Exceptions

- `app/ui/theme.py`: allowed source of truth for color values.
- `.streamlit/config.toml`: allowed minimal Streamlit bootstrap palette before app token CSS loads.
- `app/ui/charts.py`: `rgba(0,0,0,0)` is retained only for Plotly transparent `paper_bgcolor` and `plot_bgcolor`.
- `app/simple_dashboard.py`: legacy static fallback dashboard outside the public Streamlit product surface.
