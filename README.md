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

## Portfolio Dashboard MVP

샘플 포트폴리오를 기반으로 총자산, 일간 손익, 총손익, 보유 비중, 목표 비중 차이를 계산하는 개인용 포트폴리오 대시보드입니다.

v0.2부터는 공개 GitHub 코드에 실제 보유종목, 수량, 평단을 저장하지 않고 웹 화면에서 직접 입력하거나 CSV 파일로 불러와 계산할 수 있습니다. Supabase 저장소가 설정되지 않은 경우 입력 데이터는 Streamlit 브라우저 세션 안에서만 유지됩니다.

v0.3부터는 Alpha Vantage API key를 Streamlit Community Cloud Secrets에 설정한 경우에만 미국 USD 종목의 현재가와 전일종가를 선택적으로 자동 업데이트할 수 있습니다. API key가 없으면 기존 수동 입력과 CSV 업로드/다운로드 기능은 그대로 동작합니다.

v0.4부터는 `APP_PASSWORD`를 Streamlit Community Cloud Secrets에 설정해 공개 앱을 간단히 보호할 수 있습니다. 기본값은 전체 앱 보호이며, 인증된 사용자만 직접 입력, CSV 업로드/다운로드, Alpha Vantage 가격 자동 업데이트를 사용할 수 있습니다.

v0.5부터는 Supabase를 외부 저장소로 사용해 직접 입력한 포트폴리오를 이름 붙여 저장하고 다시 불러올 수 있습니다. Supabase secrets가 없으면 기존 CSV 업로드/다운로드 방식만 사용할 수 있습니다.

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

### v0.2 직접 입력 사용법

1. 앱 왼쪽 사이드바에서 **내 포트폴리오 직접 입력**을 선택합니다.
2. `USD/KRW` 환율과 `현금(KRW)`을 입력합니다.
3. 화면의 입력 폼에 `market`, `symbol`, `name`, `currency`, `quantity`, `avg_price`, `current_price`, `previous_close`, `target_weight`, `strategy_tag`를 입력합니다.
4. **종목 추가**를 누르면 현재 포트폴리오 테이블에 종목이 추가됩니다.
5. 삭제가 필요하면 **삭제할 종목**에서 종목을 선택하고 **선택 종목 삭제**를 누릅니다.

`currency`는 `KRW` 또는 `USD`만 허용합니다. 수량, 가격, 환율, 현금은 음수를 허용하지 않습니다. `quantity=0`은 관심 종목이나 감시용 입력으로 허용되며 평가액은 0으로 계산됩니다.

### v0.3 미국 주식 가격 자동 업데이트

1. 직접 입력 모드에서 미국 주식은 `market`을 `US` 또는 `USA`, `currency`를 `USD`로 입력합니다.
2. Streamlit Community Cloud Secrets에 `ALPHA_VANTAGE_API_KEY`가 설정되어 있으면 **미국 주식 가격 자동 업데이트** 버튼을 누릅니다.
3. Alpha Vantage `GLOBAL_QUOTE`에서 조회한 값으로 `current_price`, `previous_close`가 갱신됩니다.
4. Alpha Vantage 호출이 실패하거나 rate limit/오류 응답이 오면 기존에 직접 입력한 가격을 유지하고 화면에 경고를 보여줍니다.
5. 한국 주식이나 `KRW` 종목은 이번 v0.3에서 자동 업데이트하지 않고 **수동 입력 유지**로 표시됩니다.

API 호출 남발을 막기 위해 Alpha Vantage quote는 10분 동안 앱 메모리에 캐시합니다.

### v0.4 비밀번호 보호

`APP_PASSWORD`가 설정되어 있으면 앱 시작 시 비밀번호 입력 화면이 먼저 표시됩니다. 로그인 후에는 사이드바의 **로그아웃** 버튼으로 인증 상태를 지울 수 있습니다.

보호 범위는 `APP_AUTH_SCOPE`로 선택할 수 있습니다.

```toml
APP_AUTH_SCOPE = "all"
```

- `all`: 전체 앱 보호입니다. 기본값입니다.
- `manual`: 샘플 포트폴리오 모드는 공개하고, 직접 입력/CSV/가격 업데이트 기능만 보호합니다.

`APP_PASSWORD`가 없으면 앱은 계속 작동하지만 상단에 다음 경고를 표시합니다.

```text
공개 앱에서 API key quota 보호를 위해 APP_PASSWORD 설정을 권장합니다.
```

`ALPHA_VANTAGE_API_KEY`가 있는데 `APP_PASSWORD`가 없으면 API quota 보호를 위해 가격 자동 업데이트 버튼은 비활성화됩니다. v0.5 저장/불러오기는 Supabase secrets가 있더라도 `APP_PASSWORD`가 없으면 비활성화됩니다.

이 비밀번호 보호는 개인용 경량 보호입니다. 금융기관급 인증, 계정 관리, 접근 감사, OAuth, DB 기반 사용자 관리를 제공하지 않습니다.

### v0.5 Supabase 저장/불러오기

이 기능은 개인용 단일 사용자 저장소입니다. `PORTFOLIO_OWNER_ID` 하나에 연결된 포트폴리오만 저장하고 불러옵니다. 다중 사용자 로그인, RLS 정책 설계, OAuth, 팀 계정, PostgreSQL 직접 connection string 방식은 이번 버전 범위 밖입니다.

Supabase 설정이 없으면 앱에는 다음 안내가 표시되고, CSV 업로드/다운로드는 계속 사용할 수 있습니다.

```text
저장소가 설정되지 않아 CSV 방식만 사용할 수 있습니다
```

Supabase 설정 순서는 다음과 같습니다.

1. [Supabase](https://supabase.com/)에 로그인합니다.
2. **New project**를 눌러 새 프로젝트를 만듭니다.
3. 프로젝트가 준비되면 왼쪽 메뉴에서 **SQL Editor**를 엽니다.
4. `docs/supabase_schema.sql` 파일 내용을 SQL Editor에 붙여넣고 실행합니다.
5. 왼쪽 메뉴의 **Project Settings → API**에서 Project URL과 service role key를 확인합니다.
6. Streamlit Community Cloud의 **Settings → Secrets**에 아래 값을 추가합니다.

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
PORTFOLIO_OWNER_ID = "jisung-main"
```

`SUPABASE_SERVICE_ROLE_KEY`는 Supabase 데이터에 강한 권한을 가진 비밀키입니다. 절대 GitHub 코드, README, 이슈, PR 댓글, `.env`, `.streamlit/secrets.toml`에 커밋하거나 붙여넣지 마세요. Streamlit Cloud Secrets 화면에만 입력합니다.

저장/불러오기 사용법은 다음과 같습니다.

1. `APP_PASSWORD`로 로그인합니다.
2. 왼쪽 사이드바에서 **내 포트폴리오 직접 입력**을 선택합니다.
3. 종목, `USD/KRW`, `현금(KRW)`을 입력하거나 CSV로 불러옵니다.
4. **포트폴리오 저장/불러오기** 섹션의 `portfolio_name`에 이름을 입력하고 **현재 포트폴리오 저장**을 누릅니다.
5. 같은 `portfolio_name`으로 다시 저장하면 기존 저장값을 덮어씁니다.
6. 저장된 포트폴리오 목록에서 항목을 선택하고 **선택 포트폴리오 불러오기**를 누르면 종목, 환율, 현금이 현재 화면에 반영됩니다.
7. 삭제하려면 삭제 경고 아래 체크박스를 선택한 뒤 **선택 포트폴리오 삭제**를 누릅니다.

### CSV 업로드 사용법

1. **CSV 템플릿 다운로드**를 눌러 필요한 컬럼이 들어 있는 파일을 받습니다.
2. 템플릿의 컬럼 이름을 유지한 채 종목 정보를 입력합니다.
3. 앱의 **CSV 업로드**에서 작성한 CSV 파일을 선택합니다.
4. 업로드가 끝나면 현재 포트폴리오 테이블과 계산 결과가 자동으로 갱신됩니다.

CSV 컬럼은 다음 순서를 사용합니다.

```text
market,symbol,name,currency,quantity,avg_price,current_price,previous_close,target_weight,strategy_tag
```

`target_weight`는 `0.25`처럼 25%를 소수로 입력합니다.

### CSV 다운로드 사용법

현재 화면에 입력한 포트폴리오를 보관하려면 **현재 포트폴리오 CSV 다운로드**를 누릅니다. 이 CSV 파일은 사용자의 브라우저로 내려받는 파일이며 GitHub 저장소에는 저장되지 않습니다.

공개 앱이므로 실제 보유종목, 수량, 평단, 계좌 정보, API 키, 비밀번호, Supabase service role key, `.env`, `secrets.toml`, SQLite `.db` 파일은 GitHub 코드에 커밋하지 마세요.

### Streamlit Community Cloud 배포

Streamlit Community Cloud는 실행 파일 위치 기준으로 가까운 `requirements.txt`를 찾습니다. 이 저장소는 Cloud 배포용 의존성을 `app/requirements.txt`에 둡니다. 내용은 로컬 대시보드 의존성 파일인 `requirements-dashboard.txt`와 동일하게 유지합니다.

1. Streamlit Community Cloud에 GitHub 계정으로 로그인합니다.
2. **New app**을 선택합니다.
3. Repository는 `PJS-creator/krstock-fear-greed`를 선택합니다.
4. Branch는 `main`을 선택합니다.
5. Main file path는 `app/portfolio_dashboard.py`를 입력합니다.
6. Python version은 `3.11` 또는 `3.12`를 선택합니다.
7. **Deploy**를 클릭합니다.

Streamlit Community Cloud의 **Settings → Secrets** 또는 **Advanced settings → Secrets**에 다음 값을 추가합니다.

```toml
APP_PASSWORD = "strong-password-placeholder"
ALPHA_VANTAGE_API_KEY = "your-alpha-vantage-api-key"
APP_AUTH_SCOPE = "all"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
PORTFOLIO_OWNER_ID = "jisung-main"
```

`APP_PASSWORD`, `ALPHA_VANTAGE_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `.streamlit/secrets.toml`, `.env`, 실제 계좌/보유종목 정보는 절대 GitHub에 커밋하지 마세요. Secrets는 Streamlit Cloud 설정 화면에만 입력합니다.

배포 후 생성되는 URL은 보통 다음 형식입니다.

```text
https://<app-name>.streamlit.app
```

### 계산 기준

- 지원 통화는 현재 MVP 기준 `KRW`, `USD`입니다.
- `USD` 포지션은 `usd_krw` 환율로 KRW 환산합니다.
- `Position.currency`와 `Quote.currency`가 다르면 조용히 계산하지 않고 `ValueError`를 발생시킵니다.
- `quantity < 0`인 short position은 이번 MVP 범위에서 지원하지 않습니다.
- `total_pnl_pct`는 현금을 제외한 **투자 포지션 원금 대비 수익률**입니다. 현금은 총자산과 비중 계산의 분모에는 포함되지만, 투자 포지션 수익률의 원금에는 포함되지 않습니다.

### DB 초기화

```bash
python scripts/init_db.py
```

현재 SQLite 스키마는 MVP용입니다. 나중에 PostgreSQL로 전환할 때는 금액/수량의 `NUMERIC` 타입, `TIMESTAMPTZ`, provider별 quote cache/history 분리를 검토합니다. Streamlit Community Cloud의 포트폴리오 저장/불러오기는 SQLite가 아니라 Supabase를 사용합니다.

## Tests

테스트 전용 의존성을 설치합니다.

```bash
python -m pip install -r requirements-dev.txt
```

테스트를 실행합니다.

```bash
pytest -q
```
