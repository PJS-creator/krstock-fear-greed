# UX Stability Audit

이 문서는 공개 배포용 Streamlit 포트폴리오 앱의 운영 안정화, 라이트/다크 테마, 차트, 표, 빈 상태, 예외 처리, 리밸런싱 저장 구조를 점검한 기록이다.

## 현재 화면 구조 요약

- Public entrypoint: `app/public_portfolio_dashboard.py`
  - `PORTFOLIO_PUBLIC_AUTH=1`을 설정한 뒤 `app.portfolio_dashboard`를 import한다.
- Main app shell: `app/portfolio_dashboard.py`
  - 인증/저장소 설정, 세션 초기화, 자동 로드/저장, 가격/환율 갱신, 헤더, 탭 렌더링을 담당한다.
- 공개 앱 상위 탭:
  - `총괄현황`
  - `세부내역`
  - `사용자입력`
  - `자산추이`
  - `리밸런싱`
- `사용자입력` 하위 탭:
  - `보유 현황`
  - `현금·입출금·환율`
  - `거래 입력`
  - `CSV`
- `자산추이` 하위 탭:
  - `실제 기록`
  - `성과분석`
  - `리스크분석`
  - `과거 보유현황 재구성`
- 주요 UI 모듈:
  - `app/ui/investment_summary_card.py`: 총괄현황 카드, treemap형 heatmap, 보유종목 HTML table
  - `app/ui/overview.py`: 세부내역 KPI, 도넛, 통화노출, 기여도, 진단
  - `app/ui/holdings.py`: 보유현황 표, 보유종목 quick/advanced editor
  - `app/ui/transactions.py`: 표준 거래 form, 빠른 입력, 거래 CSV, 거래 cashflow
  - `app/ui/historical_reconstruction.py`: 과거 보유현황 재구성 입력/차트
  - `app/ui/performance.py`: 성과분석
  - `app/ui/risk.py`: MDD/Beta
  - `app/ui/rebalancing.py`: 목표 비중 editor와 계산 결과
  - `app/ui/data_portability.py`: CSV 가져오기/내보내기
  - `app/ui/onboarding.py`: 신규 사용자 시작 흐름과 샘플 포트폴리오

## 현재 테마 구현 방식

- `app/ui/theme.py`에 `AppTheme` dataclass와 `APP_THEMES`가 있다.
- 활성 테마 키는 `app_theme_mode`이며 값은 `dark` 또는 `light`이다.
- `app/portfolio_dashboard.py`의 `_initialize_theme_state()`와 `_render_theme_toggle()`이 앱 내부 테마 선택을 관리한다.
- `app/ui/styles.py`는 `get_app_theme(mode).css_variables()`를 CSS variable로 주입한다.
- `.streamlit/config.toml`은 Streamlit 기본 theme를 `base = "dark"`로 고정한다.
- 앱 내부 토글과 Streamlit native theme가 완전히 동일한 source of truth는 아니다. 앱 대부분은 CSS variable을 사용하므로 내부 토글이 우선 동작하지만, 일부 Streamlit native widget/data editor는 Streamlit theme 영향도 받는다.

## 현재 CSS/custom markdown 사용 지점

- `app/ui/styles.py`
  - 전역 CSS variable, body/card/button/tab/dataframe/sidebar/mobile style을 주입한다.
- `app/ui/investment_summary_card.py`
  - `unsafe_allow_html=True`로 총괄현황 전체 HTML/CSS를 직접 렌더링한다.
  - 주요 시각 이슈가 발생할 가능성이 가장 높은 파일이다.
- `app/ui/holdings.py`
  - 모바일 보유종목 카드를 HTML로 렌더링한다.
- `app/ui/historical_reconstruction.py`
  - 일부 강조 텍스트에 markdown을 사용한다.
- `app/simple_dashboard.py`
  - 별도 간단 HTML dashboard이다. 공개 앱 main path는 아니지만 hardcoded light CSS가 있다.

## 하드코딩된 색상 목록

Token으로 관리되는 색상:

- `app/ui/theme.py`
  - semantic colors, category colors, currency colors, dark/light theme tokens

Token 밖 하드코딩 색상 또는 rgba:

- `app/ui/charts.py`
  - transparent background, hover label white, vline/hline rgba, fillcolor, marker line color
- `app/ui/investment_summary_card.py`
  - heatmap tone mixing colors, cash/other colors, sparkline colors, icon colors, raw rgba shadow/highlight
- `app/ui/styles.py`
  - 일부 button text white, shadow rgba, mobile sidebar control color
- `app/simple_dashboard.py`
  - standalone HTML style

우선 조치:

- 반드시 의미를 가진 palette 자체는 `theme.py`에 남긴다.
- UI background/text/border/table/chart axis/alert/card 색상은 token 기반으로 정리한다.
- Plotly hover label text는 현재 흰색 고정이다. light mode에서도 hover 배경이 dark라 읽히지만 token 이름을 통해 의도를 명시하는 것이 낫다.

## 라이트/다크 모드에서 깨질 수 있는 컴포넌트

- `investment_summary_card.py`
  - HTML table, summary badge, heatmap tile, sparkline, KPI icon은 직접 CSS라 token 적용 누락 시 light mode 대비가 낮아질 수 있다.
- Streamlit `st.data_editor`
  - `rebalancing.py`, `transactions.py`, `holdings.py`, `historical_reconstruction.py`
  - Streamlit native theme 영향이 크며, `.streamlit/config.toml`의 `base = "dark"` 때문에 앱 내부 light mode와 다르게 보일 수 있다.
- `st.metric`
  - native widget text color는 Streamlit theme와 injected CSS가 충돌할 수 있다.
- Plotly charts
  - `risk.py`와 `performance.py` 일부 chart는 `apply_chart_layout()`을 사용하지 않고 자체 layout/title을 둔다.
- Warning/info/success/error boxes
  - Streamlit native alert 색상과 앱 CSS가 모두 적용될 수 있으므로 contrast를 확인해야 한다.

## 차트 렌더링 함수 목록

- `app/ui/charts.py`
  - `apply_chart_layout`
  - `plot_allocation`
  - `plot_contribution`
  - `plot_currency_exposure`
  - `plot_total_value_history`
  - `plot_transaction_cashflow`
  - `plot_reconstructed_total_value`
  - `plot_reconstructed_holdings_area`
- `app/ui/performance.py`
  - `_plot_asset_vs_deposit`
  - `_plot_pnl_waterfall`
- `app/ui/risk.py`
  - `_plot_total_value`
  - `_plot_drawdown`
  - `_plot_return_scatter`

구현 반영:

- `app/ui/charts.py`에 `has_chart_data`, `sanitize_chart_df`, `is_all_zero_series`, `render_empty_chart_state`, 축 포맷 helper를 추가했다.
- 실제 기록, 성과분석, 리스크분석 차트는 all-zero, NaN/Inf, 데이터 부족 상태에서 빈 상태 안내를 표시하도록 보강했다.
- `risk.py`와 `performance.py` chart에도 공통 Plotly theme/layout을 적용했다.

## 표/dataframe/data_editor 렌더링 지점

- `app/portfolio_dashboard.py`
  - 현금 원장 table
- `app/ui/components.py`
  - 가격 갱신 상세 table
- `app/ui/data_portability.py`
  - CSV preview/issues/export
- `app/ui/historical_reconstruction.py`
  - schedule editor, holdings/cash editor, reconstruction summary tables
- `app/ui/holdings.py`
  - quick/advanced holding editor, holdings table
- `app/ui/performance.py`
  - 월별/종목별 성과 table
- `app/ui/rebalancing.py`
  - target allocations editor, result table
- `app/ui/transactions.py`
  - preview table, quick editor, transaction ledger editor, cashflow table

구현 반영:

- Streamlit `st.dataframe`/`st.data_editor`의 header, row, cell text, hover, selected row 색상을 앱 token 기반 CSS로 보강했다.
- 리밸런싱은 보유종목과 현금이 모두 없으면 target editor 대신 시작 안내를 표시한다.

## 빈 데이터 상태에서 렌더링되는 화면 목록

- 총괄현황
  - 보유종목과 현금이 모두 없으면 0원 KPI 카드 묶음 대신 공통 empty state를 표시한다.
- 세부내역
  - KPI cards는 0원 상태에서도 먼저 렌더링된다.
  - 이후 `render_empty_portfolio()`가 표시된다.
- 사용자입력 > 보유 현황
  - holdings table에서 빈 상태 안내가 표시된다.
- 사용자입력 > 현금·입출금·환율
  - 현금 0원 카드와 입력 form이 표시된다.
- 사용자입력 > 거래 입력
  - form과 고급 입력이 표시된다.
- 사용자입력 > CSV
  - 템플릿/업로드/export가 표시된다.
- 자산추이 > 실제 기록
  - 기록 2개 미만 안내가 표시된다.
- 자산추이 > 성과분석
  - 거래/원장/보유가 없으면 info가 표시된다.
- 자산추이 > 리스크분석
  - 기록 부족 안내가 표시된다.
- 리밸런싱
  - no-data 또는 총자산 0원 상태에서는 목표 비중 editor/result table 대신 빈 상태 안내를 표시한다.

## 예외 처리가 부족한 함수 목록

- 주요 section render 함수는 앱 shell 수준의 공통 try/except로 감싸져 있지 않다.
- `render_investment_summary_card()`는 HTML 생성 중 예외가 나면 총괄현황 전체가 실패할 수 있다.
- `render_overview()`는 chart 생성 실패가 section 전체 실패로 확산될 수 있다.
- `render_rebalancing()`은 editor frame/normalize/calculation 일부 예외만 처리한다.
- `render_risk_analysis()`는 yfinance load와 계산 예외는 처리하지만 chart 생성 예외는 별도 fallback이 없다.
- `render_performance_analysis()`도 계산 예외와 chart 예외를 더 분리할 여지가 있다.
- 현재 `_refresh_prices()`와 `_fetch_fx_rate()`는 provider failure를 다루지만 가격 갱신 중 중복 클릭 guard나 global loading key는 제한적이다.

## session_state key 목록과 충돌 가능성

Core app keys:

- `is_authenticated`
- `authenticated_account_id`
- `authenticated_owner_id`
- `authenticated_default_portfolio`
- `authenticated_access_token`
- `authenticated_refresh_token`
- `portfolio_name`
- `portfolio_name_input`
- `pending_portfolio_name`
- `pending_portfolio_state`
- `saved_portfolio_signature`
- `last_saved_portfolio_state`
- `mark_portfolio_clean`
- `portfolio_save_status_message`
- `price_refresh_mode`
- `account_auto_load_attempted`
- `account_auto_price_refreshed`
- `account_status_message`
- `public_auto_save_status`
- `public_dashboard_section`
- `public_holdings_view`
- `cash_fx_inline_input_sync`
- `cash_fx_inline_cash_krw`
- `cash_fx_inline_cash_usd`
- `cash_fx_inline_usd_krw`
- `cash_ledger_status_message`
- `allow_negative_cash_balance`
- `app_theme_choice`
- `app_theme_mode`

Feature keys:

- `sample_portfolio_active`
- `onboarding_mode`
- `transaction_preview_rows`
- `transaction_message`
- `quick_holdings_preview_rows`
- `target_allocations_editor`
- `rebalance_mode`
- `history_period`
- `risk_period`
- `risk_benchmark`
- `risk_custom_benchmark`
- `risk_beta_basis`
- `historical_reconstruction_result`
- many historical reconstruction editor/preview keys

Potential issues:

- Theme uses `app_theme_mode` as the persisted key and now keeps compatible alias `theme_mode` in sync. The app still avoids Streamlit widget key warnings by not setting `app_theme_choice` default from session state after widget creation.
- Some dynamic keys use portfolio names or row numbers. They are mostly stable enough, but deleting/renaming portfolio rows can leave stale widget state.
- Onboarding mode is global. If user switches to CSV subtab while onboarding CSV mode is active, duplicate uploader keys can be possible in edge cases.

## target_allocations 저장 원천 분석

현재 authoritative source of truth는 `portfolio_snapshots.payload_json` 안의 `target_allocations` 필드이다.

Evidence:

- `app/portfolio_dashboard.py` passes `st.session_state["target_allocations"]` to `serialize_portfolio_payload()`.
- `_auto_save_public_portfolio()` persists the full payload through `PortfolioStore.save_portfolio()`.
- `queue_portfolio_record_load()` restores `target_allocations` from payload.
- `app/ui/rebalancing.py` `on_save` only updates `st.session_state["target_allocations"]`.
- `docs/supabase_migration_v5_target_allocations.sql` creates a separate `target_allocations` table with RLS, but no app store currently reads/writes that table.

Decision for current stabilization:

- Do not add a new destructive or partially wired storage path.
- Keep `portfolio_snapshots.payload_json` as the app source of truth for now.
- Treat `target_allocations` table migration as additive future storage support.
- Improve docs and UI to make payload fallback implicit and stable.

## 우선순위별 수정 계획

### P0

- Create this audit document before broad code changes.
- Add tests for theme tokens, empty data state, chart sanitization, safe render fallback, session state helpers.

### P1

- Extend `AppTheme` with compatibility aliases for objective token names.
- Add shared UI primitives: empty state, badges, info/warning/error boxes, safe section render.
- Improve CSS for Streamlit native dataframe/data_editor in light mode.

### P2

- Add chart helpers: `has_chart_data`, `is_all_zero_series`, `sanitize_chart_df`, axis formatters, empty chart state.
- Apply chart guard to history, reconstruction, performance, risk charts.
- Replace all-zero or too-short charts with explicit empty states.

### P3

- Introduce `get_app_data_state()` with `NO_DATA`, `SAMPLE_MODE`, `PARTIAL_DATA`, `READY`, `ERROR_STATE`.
- Make onboarding large only in `NO_DATA`; sample mode uses compact banner; partial data uses next-step banner.

### P4

- Wrap major public/private section renderers with `safe_render_section()`.
- Preserve app shell when one tab fails.
- Improve top status readability and loading/refresh messaging.

### P5

- Improve rebalancing no-data/zero-asset behavior.
- Avoid showing empty target/result tables when total asset is 0.
- Keep “사용자 설정 목표 대비 계산” wording; avoid “추천”.

### P6

- Update docs/manual QA/security docs with no-data, all-zero, blank screen, target allocation source of truth, and viewport checks.

### P7

- Run `pytest`, `compileall`, and relevant Streamlit AppTest smoke tests.

## 이번 PR 구현 요약

- `app/ui/theme.py`에 objective token alias와 `theme_mode` compatibility alias를 추가했다.
- `app/ui/components.py`에 empty state, badge, info/warning/error box, `render_metric_card()`, `safe_render_section()`을 추가했다.
- 공개/개인 주요 section renderer를 `safe_render_section()`으로 감싸 한 화면 오류가 전체 흰 화면으로 번지지 않게 했다.
- `render_app_header()`로 상단 제목, 갱신 상태, 저장 상태, 갱신/재시도/저장 버튼 배치를 공통화했다.
- `app/ui/state.py`에 `NO_DATA`, `SAMPLE_MODE`, `PARTIAL_DATA`, `READY`, `ERROR_STATE` 판단 helper를 추가했다.
- 온보딩은 no-data에서만 크게 보이고, partial data에서는 다음 단계 안내로 축소했다.
- 차트 공통 sanitization/all-zero guard를 추가하고 실제 기록, 성과분석, 리스크분석에 적용했다.
- 리밸런싱은 총자산 0원/no-data에서 editor 대신 명확한 안내를 표시한다.
- 리밸런싱 target allocation은 현재 `portfolio_snapshots.payload_json` source of truth를 유지하며 저장/로드 회귀 테스트를 추가했다.
- 빈 포트폴리오에서 상단 가격·환율 갱신 버튼이 외부 가격/환율 조회를 시작하지 않도록 guard를 추가했다.
- 가격·환율 갱신 중복 클릭 방지를 위한 `price_refresh_in_progress` session key와 spinner wrapper를 추가했다.
- 라이트 모드 table/data_editor readability를 CSS token 기반으로 보강했다.
- `tests/test_theme_tokens.py`, `tests/test_empty_states.py`, `tests/test_chart_sanitization.py`, `tests/test_safe_render.py`, `tests/test_session_state.py`, `tests/test_rebalancing_storage.py`와 Streamlit AppTest 회귀 검증을 추가/보강했다.

## 수정한 주요 파일 목록

- `app/portfolio_dashboard.py`
- `app/ui/theme.py`
- `app/ui/styles.py`
- `app/ui/components.py`
- `app/ui/state.py`
- `app/ui/charts.py`
- `app/ui/onboarding.py`
- `app/ui/overview.py`
- `app/ui/history.py`
- `app/ui/performance.py`
- `app/ui/risk.py`
- `app/ui/rebalancing.py`
- `app/ui/investment_summary_card.py`
- `docs/app_user_guide.md`
- `docs/manual_test_checklist.md`
- `docs/security_checklist.md`
- `tests/test_theme_tokens.py`
- `tests/test_empty_states.py`
- `tests/test_chart_sanitization.py`
- `tests/test_safe_render.py`
- `tests/test_session_state.py`
- `tests/test_rebalancing_storage.py`
- `tests/test_streamlit_app.py`

## 배포 전 꼭 봐야 할 화면

- 신규 계정 `NO_DATA` 첫 화면과 온보딩 CTA
- 샘플 포트폴리오 로딩 후 총괄현황/세부내역/자산추이
- 샘플 데이터 삭제 후 빈 상태 복귀
- KRW 입금만 있는 `PARTIAL_DATA`
- USD 입금만 있는 `PARTIAL_DATA`
- 국내 주식 1개 매수 후 총괄현황/사용자입력/성과분석
- 미국 주식 1개 매수 후 USD/KRW 환산과 가격 상태
- 가격·환율 갱신 성공, 일부 실패, 마지막 정상값 사용 상태
- 총괄현황 라이트/다크
- 세부내역 라이트/다크
- 사용자입력 하위 탭 라이트/다크
- 자산추이 no-data/all-zero/sample data
- 성과분석 데이터 부족과 데이터 있음
- 리스크분석 데이터 부족과 데이터 있음
- 리밸런싱 no-data, 현금만 있음, 보유종목 있음, 저장 후 새로고침
- 모바일 390px, tablet 768px, desktop 1440px
- theme toggle 후 active tab/input 유지와 widget key warning 없음
- 의도적 section 오류 또는 mock 실패 시 app shell 유지

## 남은 리스크

- Streamlit native `data_editor` theme may still follow `.streamlit/config.toml` dark base in app light mode.
- HTML-heavy summary card has the largest light/dark contrast risk.
- A separate target allocation table exists but app storage still uses snapshot payload, so future table integration must be deliberate.
- `historical_reconstruction.py`의 세부 editor와 대량 조회 흐름은 별도 UX/performance pass가 필요하다.
- 실제 Streamlit Cloud의 브라우저/권한별 `Manage app` 노출은 앱 코드가 아니라 workspace 권한과 로그인 상태에 따라 달라지므로 수동 QA가 필요하다.
