# Color System

## Philosophy

The app uses a restrained financial-product palette. Color is assigned by role, not by page:

- Primary blue for core actions, active navigation, and portfolio lines.
- Teal accent for limited secondary emphasis.
- Slate/blue-gray neutrals for background, cards, tables, borders, and cash.
- P&L colors are separate from system status colors.
- Chart colors come from a small tokenized palette, not per-chart rainbow lists.

## Light Palette

- App background: soft blue-gray off-white.
- Surfaces: white and near-white raised panels.
- Text: slate/navy.
- Primary: royal blue.
- Accent: teal.
- Profit: rose/red.
- Loss: sky/blue.

## Dark Palette

- App background: deep navy/slate, not pure black.
- Surfaces: raised navy panels.
- Text: cool gray.
- Primary: softer blue.
- Accent: teal.
- Profit: softened rose.
- Loss: readable sky blue.

## Main Tokens

- `bg`, `bg_subtle`, `surface`, `surface_raised`, `surface_sunken`, `surface_hover`
- `text`, `text_muted`, `text_subtle`, `text_inverse`
- `primary`, `primary_hover`, `primary_active`, `primary_soft`, `primary_text`
- `accent`, `accent_hover`, `accent_soft`
- `profit`, `profit_soft`, `profit_text`
- `loss`, `loss_soft`, `loss_text`
- `success`, `warning`, `danger`, `info` with matching `*_soft` and `*_text`
- `cash`, `krw`, `usd`
- `chart_grid`, `chart_axis`, `chart_text`, `chart_tooltip_bg`, `chart_tooltip_text`
- component tokens for buttons, tabs, cards, tables, inputs, and badges

## Usage Rules

- Use `primary` only for core app actions, active tabs, links, and primary chart series.
- Use `accent` sparingly for secondary emphasis.
- Use `profit/loss` only for investment gains and losses.
- Use `success/warning/danger/info` only for system or data status.
- Use `cash` as a quiet neutral value color.
- Use `get_chart_palette()` for chart colors.
- Use `get_pnl_color()` for P&L coloring.
- Use `get_status_color()` for status badges and notices.

## Forbidden

- Do not introduce ad hoc hex colors in render functions.
- Do not use random rainbow chart palettes.
- Do not use pure black or pure white as the only app background.
- Do not mix profit with success.
- Do not mix loss with primary/link blue.
- Do not add a color without adding light/dark values and contrast coverage.

## Component Examples

- Button: primary background plus primary text for main actions, neutral surface for secondary actions.
- Card: neutral surface, border, and soft shadow. Avoid function-specific card colors.
- Tabs: active tab uses primary or primary underline. Inactive tab uses muted text.
- Table: table header and row colors come from table tokens; P&L cells use P&L tokens only.
- Chart: allocation uses `chart_palette_allocation`; diverging uses `profit/neutral/loss`; status uses semantic status colors.
- Badge and alert: use status soft background and status text.

## Adding Colors Later

1. Try existing tokens first.
2. If a new token is necessary, document its meaning and scope.
3. Add both light and dark values.
4. Add contrast tests where text is involved.
5. Keep chart palettes limited.
