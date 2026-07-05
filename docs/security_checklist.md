# 보안 점검 체크리스트

이 문서는 공개 Streamlit 앱을 외부 사용자에게 배포하기 전 확인해야 할 Supabase Auth, RLS, Secrets 원칙을 정리한다.

## Streamlit Secrets

- [ ] 공개 앱 Secrets에는 `SUPABASE_URL`을 설정한다.
- [ ] 공개 앱 Secrets에는 `SUPABASE_PUBLISHABLE_KEY` 또는 `SUPABASE_ANON_KEY`만 설정한다.
- [ ] 공개 앱 Secrets에는 `SUPABASE_SERVICE_ROLE_KEY`를 넣지 않는다.
- [ ] 공개 앱 Secrets에는 `PUBLIC_USER_AUTH = true`를 설정한다.
- [ ] `.env`, API key, Supabase secret key, SQLite `.db`, 캐시 파일은 GitHub에 커밋하지 않는다.

## 앱 코드 원칙

- [ ] 공개 앱 main file path는 `app/public_portfolio_dashboard.py`이다.
- [ ] 공개 앱에서는 Supabase Auth의 `user.id`만 `owner_id`로 사용한다.
- [ ] 공개 앱에서는 사용자가 `owner_id` 또는 `portfolio_name`을 직접 바꾸는 UI를 제공하지 않는다.
- [ ] 공개 앱의 포트폴리오 이름은 `main`으로 고정한다.
- [ ] 공개 앱에서는 service role client를 생성하거나 사용자 요청 처리에 사용하지 않는다.
- [ ] `Manage app`은 Streamlit Cloud 운영 권한 메뉴이므로 일반 사용자에게 Streamlit workspace 권한을 부여하지 않는다.
- [ ] 주요 화면 렌더링 오류는 사용자 데이터나 secret 값을 노출하지 않고 일반 오류 안내와 로그용 오류 ID만 표시한다.

## RLS 정책 확인

사용자별 데이터 테이블은 `auth.uid()`와 row의 사용자 식별자를 비교해야 한다.

- [ ] `portfolio_snapshots`: RLS enabled, `owner_id = auth.uid()::text`
- [ ] `portfolio_value_history`: RLS enabled, `owner_id = auth.uid()::text`
- [ ] `historical_holding_schedules`: RLS enabled, `owner_id = auth.uid()::text`
- [ ] `cash_ledger`: RLS enabled, `user_id = auth.uid()`
- [ ] `target_allocations`: RLS enabled, `user_id = auth.uid()`
- [ ] `journal_notes`: RLS enabled, `user_id = auth.uid()`

목표 비중은 `target_allocations` 테이블이 존재하고 RLS로 접근 가능하면 그 테이블을 우선 source of truth로 사용한다. 테이블이 없거나 권한/스키마 문제로 실패하면 기존 `portfolio_snapshots.payload_json.target_allocations`를 fallback으로 사용해 기존 사용자 데이터를 보존한다.

공용 시장 데이터 캐시는 사용자 민감정보를 저장하지 않아야 한다.

- [ ] `price_cache`: 가격 데이터만 저장하고 사용자 포트폴리오 정보는 저장하지 않는다.
- [ ] `fx_rates`: 환율 데이터만 저장하고 사용자 포트폴리오 정보는 저장하지 않는다.
- [ ] 공용 캐시 테이블에 쓰기 권한이 필요하면 관리자 작업 경로와 일반 사용자 경로를 분리한다.

## 테스트 사용자 A/B 검증

Supabase SQL Editor 또는 API 테스트에서 사용자 A/B를 각각 로그인한 상태로 검증한다.

- [ ] 사용자 A가 생성한 `cash_ledger` row를 사용자 B가 조회할 수 없다.
- [ ] 사용자 A가 생성한 `target_allocations` row를 사용자 B가 수정할 수 없다.
- [ ] 사용자 A가 생성한 `journal_notes` row를 사용자 B가 조회하거나 수정할 수 없다.
- [ ] 사용자 B가 사용자 A의 `portfolio_snapshots`를 조회할 수 없다.
- [ ] anon role 또는 로그아웃 상태에서는 사용자 데이터 테이블을 조회할 수 없다.
- [ ] 가격/환율 공용 캐시 조회는 사용자 민감정보 없이 동작한다.

## 배포 전 확인

- [ ] GitHub PR diff에 secrets나 `.env`가 포함되지 않았다.
- [ ] Streamlit Cloud 앱 Secrets를 바꾼 뒤 Reboot 또는 Redeploy를 실행했다.
- [ ] 일반 브라우저 또는 시크릿 창에서 로그인 전에는 로그인/회원가입 UI만 보인다.
- [ ] 일반 사용자 계정에서 `저장 관리`, `포트폴리오 저장`, `저장된 포트폴리오`, `선택 포트폴리오 불러오기` UI가 보이지 않는다.
