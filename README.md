# krstock-fear-greed

DCInside 국내주식 게시글 수집 실험과 개인용 포트폴리오 대시보드 MVP를 함께 관리하는 저장소입니다.

## DCInside Scraper

기존 스크래퍼 런타임 의존성만 설치합니다.

```bash
python -m pip install -r requirements.txt
```

기본 설정으로 DCInside 게시글 수집기를 실행합니다.

```bash
python main.py
```

주요 환경변수는 `BOARD_ID`, `TARGET_DATE`, `DATES_FILE`, `START_TIME`, `END_TIME`, `OUT_DIR`입니다. GitHub Actions 스크래퍼 워크플로우도 이 기본 의존성만 설치하도록 유지합니다.

## Portfolio Dashboard

개인용 포트폴리오 대시보드입니다. 공개 GitHub 코드에는 실제 보유종목, 수량, 평단, API key, 비밀번호, Supabase service role key를 저장하지 않습니다.

버전별 주요 흐름은 다음과 같습니다.

- v0.2: 직접 입력과 CSV 업로드/다운로드
- v0.3: Alpha Vantage `GLOBAL_QUOTE` 기반 미국 USD 종목 가격 갱신
- v0.4: `APP_PASSWORD` 기반 경량 보호
- v0.5: Supabase 저장/불러오기
- v0.6: ticker/quantity 중심 빠른 입력, KRW/USD 현금, Supabase 자산 이력, Plotly 차트, 자산 진단
- v0.7: FinanceDataReader 기반 국내 KR/KRW 종목 최근 제공 가격 갱신

### 대시보드 의존성 설치

```bash
python -m pip install -r requirements-dashboard.txt
```

### Streamlit 대시보드 실행

```bash
streamlit run app/portfolio_dashboard.py
```

의존성 설치가 제한된 환경에서는 표준 라이브러리 기반 미니 대시보드를 실행할 수 있습니다.

```bash
python app/simple_dashboard.py
```

## v0.7 사용법

### 빠른 입력

1. **보유자산** 탭을 엽니다.
2. 빠른 입력 표에 `market`, `ticker`, `quantity`를 입력합니다.
3. 미국 주식은 `market = US`, 국내 주식은 `market = KR`을 선택합니다.
4. **입력 적용**을 누릅니다.
5. 상단의 **가격 새로고침**을 눌러 최근 제공 가격과 전일 종가를 채웁니다.

빠른 입력 모드의 기본 처리 방식은 다음과 같습니다.

- `market = US`: `currency = USD`, `display_name = ticker`
- `market = KR`: `currency = KRW`, `display_name = ticker`
- `avg_price = 미입력`

국내 주식은 6자리 종목코드를 입력합니다.

```text
삼성전자: 005930
SK하이닉스: 000660
NAVER: 035420
```

`005930.KS`, `005930.KQ`, `KR:005930`처럼 입력해도 가능한 경우 `005930`으로 정규화합니다. 6자리 코드가 아니면 입력 오류로 표시됩니다.

`avg_price`는 선택값입니다. 평균 매수가가 없는 종목은 총손익과 총수익률 계산에서 제외됩니다. 평균 매수가가 일부 종목에만 있으면 화면에는 **원가 정보 범위**가 표시됩니다.

### 고급 설정

**보유자산** 탭의 **고급 설정**에서 아래 필드를 선택적으로 수정할 수 있습니다.

```text
market,currency,display_name,account_name,target_weight,avg_price,strategy_tag,note
```

종목명, 현재가, 전일 종가, 평균 매수가는 필수 입력이 아닙니다. 가격 조회에 실패한 종목은 0원으로 계산하지 않습니다. 마지막 정상 가격이 있으면 stale 상태로 유지하고, 정상 가격도 없으면 평가액을 미산정으로 표시합니다.

### 가격 새로고침

상단의 **가격 새로고침** 버튼 하나로 미국 주식과 국내 주식을 함께 갱신합니다.

- `US`/`USD`: Alpha Vantage `GLOBAL_QUOTE` 기반 최근 제공 가격
- `KR`/`KRW`: FinanceDataReader 기반 최근 제공 가격 또는 최근 종가
- 그 외 market/currency 조합: 수동 입력 가격 유지

API 또는 데이터 소스 호출은 Streamlit 화면 rerun만으로 실행되지 않습니다. 사용자가 **가격 새로고침**을 누른 경우에만 실행됩니다.

국내 주식 가격 조회는 FinanceDataReader를 사용하며 별도 API key가 필요 없습니다. Alpha Vantage key는 미국 주식 가격과 USD/KRW 환율 조회에 사용됩니다.

FinanceDataReader가 반환한 가격 데이터에서 최신 `Close`를 `current_price`로 사용하고, 직전 `Close`를 `previous_close`로 사용합니다. 최신 행이 하나뿐이라 직전 종가를 확정할 수 없으면 `previous_close = current_price`로 저장합니다. 이 경우 일간 변동은 0으로 표시될 수 있습니다.

종목명은 FinanceDataReader의 KRX listing에서 가능한 경우 보완합니다. listing 조회가 실패하면 6자리 종목코드를 표시명으로 유지합니다. listing과 가격 조회에는 10분 TTL cache를 적용해 같은 버튼을 반복 클릭할 때 불필요한 호출을 줄입니다.

### 현금과 환율

사이드바에서 아래 값을 입력합니다.

- `KRW 현금`
- `USD 현금`
- `USD/KRW`

총현금은 KRW 기준으로 환산되어 표시됩니다. **USD/KRW 환율 갱신** 버튼을 누르면 Alpha Vantage `CURRENCY_EXCHANGE_RATE`로 USD/KRW를 조회합니다. 실패하면 기존 수동 환율을 유지합니다. 환율 조회도 자동 실행되지 않고 버튼을 눌렀을 때만 실행됩니다.

### 가격 최신성

Alpha Vantage 무료 `GLOBAL_QUOTE`는 거래소 호가 화면처럼 즉시 변하는 가격이 아니라, 장마감 기준 최신 제공 가격일 수 있습니다. FinanceDataReader 기반 국내 주식 가격도 무료 데이터 소스의 최근 제공 가격 또는 최근 종가이며, 공식 시세 서비스가 아닙니다. 이 앱은 “최근 제공 가격”, “최근 종가”, “마지막 가격 갱신”으로 표시합니다.

`fetched_at`은 가격 자체의 거래 시각이 아니라 앱이 데이터 소스를 조회한 시각입니다.

가격 상태는 다음처럼 표시됩니다.

- `updated`: 새로 조회된 최근 제공 가격
- `cached`: 10분 TTL cache에서 사용한 가격
- `stale`: 조회 실패로 마지막 정상 가격 유지
- `failed`: 조회 실패, 정상 가격 없음
- `missing`: 가격 데이터 없음
- `missing_api_key`: 미국 주식 조회용 Alpha Vantage API key 없음
- `manual`: 수동 가격 유지

### 개요 탭

**개요** 탭에는 다음이 표시됩니다.

- 총자산
- 오늘 변동액 및 변동률
- 총현금 및 현금 비중
- USD 자산 노출도
- 종목별 자산 비중 donut chart
- 오늘 변동 기여도 horizontal bar chart
- 통화별 노출도 chart
- 자산 진단

총손익과 총수익률은 평균 매수가 정보가 있는 종목 범위에서만 보조 정보로 표시됩니다. 원가 정보가 없으면 잘못된 0% 수익률을 표시하지 않습니다.

### 자산추이 탭

**자산추이** 탭은 Supabase에 저장된 실제 snapshot 기반 **총자산 추이**를 보여줍니다. 거래내역과 외부 입출금 기록이 없으므로 CAGR, TWR, 투자성과 수익률은 계산하지 않습니다.

스냅샷은 아래 시점에 저장됩니다.

- 가격 새로고침이 성공한 후
- 포트폴리오 저장 후
- 사용자가 **현재 상태 기록**을 누른 경우

로그인이나 화면 rerun만으로 snapshot을 자동 저장하지 않습니다. 이력은 v0.6 배포 이후부터 쌓입니다. 과거 주가로 현재 보유량을 역산해 과거 자산처럼 보이게 만들지 않습니다.

### 관리 탭

**관리** 탭에는 CSV, 저장/불러오기/삭제, 현재 상태 기록 기능이 있습니다.

Supabase 설정이 없으면 다음 안내가 표시되고 CSV 방식은 계속 사용할 수 있습니다.

```text
저장소가 설정되지 않아 CSV 방식만 사용할 수 있습니다
```

## Supabase 설정

v0.5 저장 테이블은 그대로 유지합니다. v0.6에서는 자산 이력용 테이블을 추가합니다. destructive migration은 없습니다.

처음 설정하는 경우:

1. Supabase 프로젝트를 만듭니다.
2. Supabase **SQL Editor**에서 `docs/supabase_schema.sql` 내용을 실행합니다.
3. 이어서 `docs/supabase_migration_v0_6.sql` 내용을 실행합니다.
4. Streamlit Cloud **App settings → Secrets**에 아래 값을 추가합니다.

이미 v0.5를 설정한 경우:

1. 기존 `portfolio_snapshots` 테이블은 유지합니다.
2. Supabase **SQL Editor**에서 `docs/supabase_migration_v0_6.sql`만 추가 실행합니다.
3. Streamlit Cloud 앱을 **Reboot** 또는 **Redeploy**합니다.

Streamlit Secrets 예시는 다음과 같습니다. 실제 값을 GitHub에 넣지 마세요.

```toml
APP_PASSWORD = "strong-password-placeholder"
APP_AUTH_SCOPE = "all"
ALPHA_VANTAGE_API_KEY = "your-alpha-vantage-api-key"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
PORTFOLIO_OWNER_ID = "jisung-main"
```

`SUPABASE_SERVICE_ROLE_KEY`는 Supabase 데이터에 강한 권한을 가진 비밀키입니다. 절대 GitHub 코드, README, 이슈, PR 댓글, `.env`, `.streamlit/secrets.toml`에 커밋하거나 붙여넣지 마세요. Streamlit Cloud Secrets 화면에만 입력합니다.

## 저장 데이터 호환

v0.6 저장 payload는 `schema_version=2`를 사용합니다.

새 payload에는 아래가 포함됩니다.

```text
holdings
cash_balances
last_known_quotes
quote_status
usd_krw
schema_version
```

기존 `schema_version=1` 저장 데이터는 불러올 때 자동으로 v2 구조로 변환됩니다. v1의 `rows`, `usd_krw`, `cash_krw`, `current_price`, `previous_close`는 v2의 holdings, cash balances, last known quotes로 옮겨집니다. v0.7의 국내 주식 가격 정보도 같은 holdings 필드의 `current_price`, `previous_close`, `quote_status`, `fetched_at`, `provider`에 저장되므로 destructive migration은 필요하지 않습니다.

## Streamlit Community Cloud 배포

Streamlit Community Cloud는 실행 파일 위치 기준으로 가까운 `requirements.txt`를 찾습니다. 이 저장소는 Cloud 배포용 의존성을 `app/requirements.txt`에 둡니다. 내용은 로컬 대시보드 의존성 파일인 `requirements-dashboard.txt`와 동일하게 유지합니다.

1. Streamlit Community Cloud에 GitHub 계정으로 로그인합니다.
2. **New app**을 선택합니다.
3. Repository는 `PJS-creator/krstock-fear-greed`를 선택합니다.
4. Branch는 `main`을 선택합니다.
5. Main file path는 `app/portfolio_dashboard.py`를 입력합니다.
6. Python version은 `3.11` 또는 `3.12`를 선택합니다.
7. **Deploy**를 클릭합니다.

Secrets를 수정했거나 `app/requirements.txt`가 바뀐 경우 Streamlit Cloud에서 앱을 Reboot 또는 Redeploy 해야 새 설정과 의존성이 반영됩니다. 이번 국내 주식 가격 새로고침 변경은 `finance-datareader` 의존성이 추가되므로 merge 후 Reboot 또는 Redeploy가 필요합니다.

## 향후 개선

국내 주식 provider는 현재 FinanceDataReader 기반 무료 데이터 소스를 사용합니다. 무료 데이터 소스는 구조가 바뀌거나 차단될 수 있습니다. 장기적으로는 한국투자증권 Open API 같은 공식 provider를 선택 옵션으로 추가할 수 있습니다. KIS appkey, appsecret, access token 같은 실제 인증 정보는 코드나 README에 넣지 않고 Streamlit Secrets 같은 비밀 저장소로만 관리해야 합니다.

## 보안 및 데이터 정책

- API key, APP_PASSWORD, Supabase service role key를 코드나 README에 실제 값으로 넣지 않습니다.
- KIS appkey, appsecret, access token 같은 공식 증권 API 인증 정보도 코드나 README에 넣지 않습니다.
- `.env`, `.streamlit/secrets.toml`, SQLite DB, cache 파일을 커밋하지 않습니다.
- 실제 보유종목, 수량, 평단을 코드나 테스트에 하드코딩하지 않습니다.
- 이 앱은 개인용 단일 사용자 저장소입니다. 다중 사용자 로그인, RLS 정책 설계, OAuth, 팀 계정은 이번 버전 범위 밖입니다.
- “매수”, “매도”, “추천” 같은 투자 권고 표현은 사용하지 않습니다.

## Tests

테스트 전용 의존성을 설치합니다.

```bash
python -m pip install -r requirements-dev.txt
```

테스트를 실행합니다.

```bash
pytest -q
```
