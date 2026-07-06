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
- v0.7: FinanceDataReader 기반 국내 KR/KRW 종목 최근 제공 가격 갱신과 Professional UI/UX 정리
- v0.8: 과거 보유현황 스냅샷 기반 자산추이 재구성
- v0.9: 종목명/티커와 수량 중심 최소 입력, 입력 미리보기, 과거 보유현황 이벤트 입력
- v1.0: 자산 구성 차트 시각 개선, 현금 포함 도넛, 국내 종목명 우선 표기, 콤마 숫자 포맷 강화
- v1.1: 투자 총괄 카드 탭, 평단가 기반 평가이익/수익률 표시, 빠른 입력 평단가 선택 입력
- v1.2: 매입/매도 거래 입력으로 자산 입력 일원화, 거래 기준 현재 보유현황 자동 계산, 매입/매도 자산 증감 그래프
- v1.3: 미국 주식 최근 가격 조회를 Alpha Vantage에서 yfinance로 변경해 API key 없이 가격 새로고침 가능
- v1.4: Streamlit Secrets 계정별 저장소 owner, 로그인 후 기본 포트폴리오 자동 불러오기, 가격/환율 자동 갱신

### 대시보드 의존성 설치

Streamlit 대시보드는 Cloud 프론트엔드 호환성을 위해 `streamlit==1.50.0`으로 고정합니다. `app/requirements.txt`, `requirements-dashboard.txt`, `requirements-dev.txt`의 대시보드 핵심 버전은 함께 맞춥니다.

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

## v1.2 매입/매도 거래 입력 방식

v1.2부터 자산 입력은 **보유자산 → 자산 입력**에서 매입/매도 거래로 관리합니다. 사용자는 직접 현재 보유수량을 고치는 대신 거래를 입력하고, 앱이 거래내역을 기준으로 전체 보유현황과 평균 매입 단가를 다시 계산합니다.

거래 입력에 필요한 값은 아래 5개입니다.

```text
구분,주식명,평단가,수량,시점
```

- `구분`: `매입` 또는 `매도`
- `주식명`: 삼성전자, 005930, MU, QURE 같은 종목명 또는 티커
- `평단가`: 해당 거래의 1주당 가격입니다. 국내 종목은 원화, 미국 종목은 달러 기준입니다.
- `수량`: 해당 거래 수량입니다.
- `시점`: 거래일입니다. `YYYY-MM-DD` 형식을 권장합니다.

입력 위치는 세 가지입니다.

1. **거래 1건 입력**: 한 건씩 명확히 입력할 때 사용합니다.
2. **여러 개 빠른 입력**: 표에 여러 거래를 한 번에 입력하거나 아래 형식으로 붙여넣습니다.
3. **CSV로 한번에 입력**: 거래 CSV 템플릿을 내려받아 작성한 뒤 업로드합니다.

빠른 붙여넣기 예시는 다음과 같습니다.

```text
매입 삼성전자 72300 200 2026-04-13
매입 MU 120.5 20 2026-04-13
매도 MU 130.0 5 2026-06-01
```

거래 CSV 컬럼은 아래와 같습니다.

```text
transaction_type,ticker_or_name,unit_price,quantity,occurred_at
```

CSV의 `transaction_type`에는 `매입`, `매도`, `buy`, `sell` 중 하나를 입력할 수 있습니다.

거래를 미리보기한 뒤 **오류 없는 거래 반영**을 누르면 다음 항목이 자동으로 갱신됩니다.

- **전체 보유현황**: 매입은 수량을 늘리고, 매도는 수량을 줄입니다.
- **평단가**: 남은 보유수량 기준 평균 매입 단가로 다시 계산합니다.
- **투자 총괄 카드 / 개요 / 보유자산 표**: 계산된 현재 보유현황을 기준으로 표시합니다.
- **매입/매도 기준 자산 증감**: 날짜별 순매입과 누적 순매입 그래프를 표시합니다.

보유수량보다 큰 매도 거래는 반영하지 않습니다. 가격 새로고침은 거래 입력 후 별도로 **가격 새로고침**을 눌러 실행합니다.

## v0.9 이전 최소 입력 방식 참고

v0.9 방식의 종목명 또는 티커, 수량, 선택 평단가 입력은 v1.2에서 거래 입력 방식으로 대체되었습니다. 현재 화면에서는 **보유자산 → 자산 입력**에서 매입/매도 거래를 입력합니다.

현재 포트폴리오 예시는 다음과 같습니다.

```text
삼성전자 10 72300
SK하이닉스 5 180000
MU 20 120.5
QURE 500
```

국내 종목명은 무료 KRX listing 기반으로 검색합니다. 검색 결과가 1개면 자동 적용하고, 여러 개면 화면에서 후보를 직접 선택해야 합니다. 검색 결과가 없으면 `005930` 같은 6자리 종목코드를 직접 입력합니다. 미국 종목은 이번 버전에서 회사명 검색을 하지 않고 `MU`, `QURE`, `GOOG` 같은 ticker 기준으로 처리합니다.

입력은 바로 반영되지 않습니다. **입력 미리보기**를 먼저 눌러 아래 항목을 확인한 뒤 **오류 없는 행 적용**을 누릅니다.

```text
입력값, 티커, 표시명, 시장, 통화, 수량, 평단가, 상태, 메시지
```

동일한 `market+ticker`를 다시 입력하면 기본값은 새 입력 수량으로 교체입니다. 필요하면 **기존 수량에 합산**을 선택할 수 있습니다. 이 v0.9 입력 방식에서는 가격 조회가 입력 즉시 실행되지 않으므로 **가격 새로고침** 또는 **실패 종목 다시 시도**를 눌러 갱신합니다.

간편 CSV 템플릿은 아래 컬럼을 사용합니다.

```text
ticker_or_name,quantity,avg_price
```

`avg_price`는 선택값입니다. 국내 종목은 원화 평단가, 미국 종목은 달러 평단가를 넣습니다. 평단가를 비워 두면 보유수량과 평가금액은 계산되지만 평가이익과 수익률은 해당 종목에서 제외됩니다.

전체 컬럼이 필요한 경우 **고급 설정**에서 `market`, `currency`, `display_name`, `account_name`, `strategy_tag`, `avg_price`, `target_weight`, `note`를 직접 수정할 수 있습니다.

### 과거 재구성 입력 모드

과거 재구성에는 두 가지 입력 방식이 있습니다.

- **전체 보유현황 모드**: 각 날짜에 그 시점의 전체 보유현황을 입력합니다. 다음 날짜 전까지 유지됩니다.
- **보유수량 변경 이벤트 모드**: 특정 날짜부터 특정 종목의 총 보유수량이 얼마인지 입력합니다. 매수/매도 금액이나 수익률을 계산하는 거래내역 입력기가 아닙니다.

전체 보유현황 모드의 간편 CSV는 아래 컬럼을 사용합니다.

```text
as_of_date,ticker_or_name,quantity
```

이벤트 모드는 아래처럼 입력합니다.

```text
2026-06-01 삼성전자 100
2026-06-07 삼성전자 200
2026-06-16 삼성전자 100
2026-06-16 SK하이닉스 10
```

이벤트 모드의 `quantity_after`는 해당 날짜부터의 총 보유수량입니다. `quantity_after=0`이면 그 날짜부터 보유 종료로 처리합니다. 앱은 이벤트 입력을 내부적으로 날짜별 전체 보유현황 스케줄로 변환한 뒤 기존 재구성 엔진을 사용합니다.

새 날짜를 추가할 때는 **날짜 추가 - 직전 보유현황 복사**를 사용합니다. 직전 날짜의 전체 보유현황을 복사한 뒤 바뀐 종목 수량만 수정하면 됩니다. 새 날짜에서 직전 날짜에 있던 종목이 빠지면 “이 날짜부터 아래 종목은 보유 종료로 처리됩니다” 경고와 확인 체크박스가 표시됩니다.

과거 재구성 입력과 현재 포트폴리오는 **현재 포트폴리오 연동** 영역에서 명시적으로 연결합니다.

- **현재 보유자산 → 과거 스케줄**: 현재 보유자산과 사이드바 현금/환율을 선택한 기준일의 과거 보유현황으로 추가하거나 같은 날짜를 교체합니다.
- **과거 스케줄 → 현재 보유자산**: 과거 보유현황 스케줄의 최신 기준일을 현재 포트폴리오로 적용합니다. 적용 후 가격은 “미조회” 상태가 되므로 **가격 새로고침**을 누른 뒤 **현재 포트폴리오 저장**을 눌러 실제 기록에도 남깁니다.

개인 테스트 앱은 v0.8 migration까지 적용되어 있으면 기존 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `PORTFOLIO_OWNER_ID`로 저장/불러오기를 계속 사용합니다. 외부 사용자용 앱은 Supabase Auth/RLS 적용을 위해 `docs/supabase_migration_v2_auth_rls.sql`을 추가로 실행합니다.

## v0.8 과거 보유현황 재구성

**자산추이** 탭은 두 영역으로 나뉩니다.

- **실제 기록**: Supabase에 저장된 실제 포트폴리오 snapshot 기록입니다.
- **과거 보유현황 재구성**: 날짜별 전체 보유현황 snapshot과 현금 snapshot을 입력해 과거 일별 평가액을 다시 계산합니다.

과거 보유현황 재구성은 거래내역 입력기가 아닙니다. 각 `as_of_date`는 그 날짜부터 다음 snapshot 전까지 유효한 **전체 보유현황**입니다. 예를 들어 2026-06-01 snapshot에 `005930`, `MU`가 있고 2026-06-10 snapshot에 `005930`만 있으면, 2026-06-10부터 `MU`는 더 이상 보유하지 않는 것으로 계산합니다.

### 입력 컬럼

보유현황 스케줄 CSV는 아래 컬럼을 사용합니다.

```text
as_of_date,market,ticker,quantity,display_name,currency,account_name,strategy_tag,note
```

현금/환율 스케줄 CSV는 아래 컬럼을 사용합니다.

```text
as_of_date,cash_krw,cash_usd,usd_krw
```

`market`은 `KR` 또는 `US`입니다. `market`과 `currency`를 비워 두면 6자리 숫자 ticker는 `KR/KRW`, 영문 ticker는 `US/USD`로 추론합니다. 국내 종목코드는 `005930`처럼 6자리 문자열로 유지합니다.

### 사용 순서

1. Streamlit Cloud Secrets에 `APP_PASSWORD`가 설정되어 있어야 합니다.
2. 앱에서 로그인합니다. `APP_AUTH_SCOPE = "manual"`인 경우에도 이 기능은 인증 후 사용할 수 있습니다.
3. **자산추이 → 과거 보유현황 재구성**을 엽니다.
4. 화면 표에 직접 입력하거나 CSV 템플릿을 내려받아 작성한 뒤 업로드합니다.
5. 시작일과 종료일을 확인합니다.
6. 필요하면 **고급 설정**에서 “가격이 없는 날짜에 전일 종가 forward-fill 사용”을 켭니다.
7. **재구성 실행**을 누릅니다.
8. 결과 KPI, 총자산 차트, 종목별 stacked chart, 일별 상세표를 확인합니다.
9. 필요하면 일별 평가 CSV와 종목별 평가 CSV를 내려받습니다.

Supabase v0.8 migration을 실행한 경우 **현재 스케줄 저장**, **선택 스케줄 불러오기**, **선택 스케줄 삭제**를 사용할 수 있습니다. migration을 아직 실행하지 않았거나 Supabase Secrets가 없으면 저장/불러오기는 비활성화되고 CSV 방식만 사용할 수 있습니다.

### 계산 규칙

- 가격 데이터는 FinanceDataReader의 `Close` 컬럼을 사용합니다.
- 미국 주식의 과거 가격도 Alpha Vantage historical API가 아니라 FinanceDataReader를 기본값으로 사용합니다.
- 평가일은 조회된 실제 거래일 기준입니다. 비거래일에 입력한 snapshot은 다음 거래일에 적용되고 화면에 안내가 표시됩니다.
- 가격 조회 실패 또는 누락 가격은 0원으로 계산하지 않습니다. 해당 종목은 그 날짜의 합계에서 제외하고 누락으로 표시합니다.
- USD 종목과 USD 현금은 `cash` snapshot의 `usd_krw`, FinanceDataReader 환율, 현재 세션의 USD/KRW 순서로 환산합니다.
- 결과의 변화율은 입력 snapshot과 가격 데이터 기준 평가액 변화입니다. 외부 입출금과 거래내역을 분리한 투자성과 수익률이 아닙니다.
- 보유현황 변경일의 급격한 변화는 매매, 입출금, 종목 교체가 섞인 snapshot 평가액 변화일 수 있습니다. 이 기능은 TWR, MWR, CAGR을 계산하지 않습니다.

### 데이터 소스 제한

FinanceDataReader는 무료 데이터 소스에 의존합니다. 데이터 구조 변경, 일시 차단, 특정 ticker 누락, 환율 누락이 발생할 수 있습니다. 장기간·다종목 재구성은 느릴 수 있어 Streamlit cache를 사용하며, 필요할 때 **가격 데이터 캐시 비우기** 또는 **가격 데이터 캐시 무시하고 재조회**를 사용합니다.

## v0.7 이전 빠른 입력 방식 참고

### 빠른 입력

1. **보유자산** 탭을 엽니다.
2. 빠른 입력 표에는 기본적으로 `ticker_or_name`, `quantity`, 선택 `avg_price`를 입력합니다.
3. 6자리 숫자 ticker는 국내 `KR/KRW`, 그 외 영문 ticker는 미국 `US/USD`로 자동 추론됩니다.
4. 자동 추론 preview에서 `market`, `ticker`, `quantity`, `avg_price`를 확인하고 필요하면 수정합니다.
5. **입력 적용**을 누릅니다.
6. 상단의 **가격 새로고침**을 눌러 최근 제공 가격과 전일 종가를 채웁니다.

다중 붙여넣기는 **보유자산 → 다중 붙여넣기**에서 사용할 수 있습니다.

```text
005930,10,72300
MU,20,120.5
GOOG,2
```

동일 `market+ticker`가 붙여넣기에 여러 번 나오면 마지막 입력을 preview에 남깁니다. 기존 보유 행과 같은 ticker를 적용하면 새 행을 만들지 않고 기존 행의 수량을 수정합니다.

국내 주식은 6자리 종목코드를 유지합니다.

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
market,currency,display_name,account_name,target_weight,avg_price,strategy_tag,note,current_price,previous_close,quote_status,fetched_at,provider
```

종목명, 현재가, 전일 종가, 평균 매수가는 필수 입력이 아닙니다. 가격 조회에 실패한 종목은 0원으로 계산하지 않습니다. 마지막 정상 가격이 있으면 stale 상태로 유지하고, 정상 가격도 없으면 평가액을 미산정으로 표시합니다.

### 가격 새로고침과 상세 로그

상단의 **현재가/환율 갱신** 버튼 하나로 보유 중인 미국 주식, 국내 주식, USD/KRW 환율을 함께 갱신합니다. 이 버튼은 이전 조회 시간이 얼마 되지 않았더라도 현재 세션의 가격/환율 캐시를 우회해 전체 종목을 다시 조회합니다.

- `US`/`USD`: yfinance 기반 최근 제공 가격
- `KR`/`KRW`: FinanceDataReader 기반 최근 제공 가격 또는 최근 종가
- 그 외 market/currency 조합: 수동 입력 가격 유지

API 또는 데이터 소스 호출은 일반적인 Streamlit 화면 rerun만으로 반복 실행되지 않습니다. 로그인 후 계정의 기본 포트폴리오가 자동으로 불러와진 경우에는 USD/KRW 환율과 보유 종목 가격을 한 번 자동 갱신합니다. 그 외에는 사용자가 **현재가/환율 갱신** 또는 **USD/KRW 환율 갱신**을 누른 경우에만 실행됩니다.

가격 갱신 후 메인 화면에는 요약 메시지 하나만 표시됩니다. 종목별 상세 결과는 기본적으로 접혀 있는 **데이터 업데이트 상세** expander에서 확인합니다. 상세 표에는 ticker, 종목명, 시장, provider, 상태, KST 조회 시각, message가 표시됩니다. 실패·이전 가격·미조회 항목만 보는 필터도 제공합니다.

미국 주식 가격 조회와 USD/KRW 환율 조회는 yfinance를 사용하며 별도 API key가 필요 없습니다. 국내 주식 가격 조회는 FinanceDataReader를 사용하며 별도 API key가 필요 없습니다. 기본 앱 흐름에서는 Alpha Vantage key를 사용하지 않습니다.

yfinance와 FinanceDataReader가 반환한 가격 데이터에서 최신 `Close`를 `current_price`로 사용하고, 직전 `Close`를 `previous_close`로 사용합니다. 최신 행이 하나뿐이라 직전 종가를 확정할 수 없으면 `previous_close = current_price`로 저장합니다. 이 경우 일간 변동은 0으로 표시될 수 있습니다.

yfinance와 FinanceDataReader 기반 가격은 무료 데이터 소스의 최근 제공 가격 또는 최근 종가이며, 공식 시세 서비스가 아닙니다. 데이터 소스의 제한, 지연, 일시 차단, ticker 누락이 발생할 수 있습니다.

`fetched_at`은 가격 자체의 거래 시각이 아니라 앱이 데이터 소스를 조회한 시각입니다. 화면의 시간은 KST 형식으로 표시됩니다.

가격 상태는 다음처럼 표시됩니다.

- `updated`: 새로 조회된 최근 제공 가격
- `cached`: 10분 TTL cache에서 사용한 가격
- `stale`: 조회 실패로 마지막 정상 가격 유지
- `failed`: 조회 실패, 정상 가격 없음
- `missing`: 가격 데이터 없음
- `missing_api_key`: 이전 버전의 Alpha Vantage API key 없음 상태 또는 과거 저장 데이터의 legacy 상태
- `manual`: 수동 가격 유지

### 현금과 환율

사이드바의 **현금 및 환율**에서 아래 값을 입력합니다.

- `KRW 현금`
- `USD 현금`
- `USD/KRW`

총현금은 KRW 기준으로 환산되어 표시됩니다. **USD/KRW 환율 갱신** 버튼을 누르면 yfinance의 USD/KRW 환율 데이터를 조회합니다. 별도 API key는 필요 없습니다. 실패하면 기존 수동 환율을 유지합니다. 로그인 후 기본 포트폴리오가 자동으로 불러와진 경우에는 환율도 한 번 자동 갱신됩니다.

holdings, 현금, 환율, 포트폴리오 이름이 바뀌면 헤더와 사이드바에 **저장하지 않은 변경 있음**이 표시됩니다. 저장이 끝나거나 저장된 포트폴리오를 불러오면 **저장됨** 상태로 돌아갑니다.

### 포트폴리오 선택과 저장 상태

Supabase 저장소가 설정되어 있고 저장된 포트폴리오가 있으면 사이드바의 **현재 포트폴리오** 영역에 저장된 포트폴리오 선택 상자가 표시됩니다. 로그인 계정에 `default_portfolio`가 설정되어 있고 같은 이름의 저장 포트폴리오가 있으면 앱이 시작될 때 자동으로 불러옵니다. 다른 포트폴리오를 선택한 뒤 **선택 포트폴리오 불러오기**를 누르면 해당 포트폴리오를 불러옵니다.

저장하지 않은 변경이 있으면 불러오기 버튼이 비활성화되고 관리 탭에서 먼저 저장하라는 경고가 표시됩니다. 새 포트폴리오 생성과 이름 변경은 **관리** 탭의 저장 폼에서 처리합니다.

### 투자 총괄 카드 탭

**투자 총괄 카드** 탭은 현재 포트폴리오를 보고서 형태로 한 화면에 보여줍니다.

- 상단에는 포트폴리오명, 업데이트 기준일, 전일 대비 손익이 표시됩니다.
- 왼쪽에는 종목별/현금 자산 비중, 가운데에는 총자산 도넛 카드가 표시됩니다.
- 보유 종목 현황 표에는 종목명, 보유 수량, 평단가, 평가 수익률, 평가금액, 자산 비중이 표시됩니다.
- 하단에는 총자산, 주식 평가금액, 현금, 평가이익, 수익률, 금일 손익, 총 시드, 적용 환율 KPI가 표시됩니다.

평가이익과 수익률은 **보유자산 → 자산 입력**의 매입/매도 거래에서 계산된 평균 매입 단가 기준입니다. 평단가가 없는 종목은 잘못된 0% 수익률로 표시하지 않고 미산정으로 남깁니다.

### 개요 탭

**개요** 탭 상단에는 핵심 KPI 4개가 표시됩니다.

- **총자산**: 보유 종목 평가액과 KRW 환산 현금 합계
- **오늘 변동**: 최근 제공 가격과 전일 종가 차이로 계산한 일간 변동액과 변동률
- **총현금**: KRW 현금과 USD 현금을 USD/KRW로 환산한 합계, delta는 총자산 대비 현금 비중
- **USD 노출도**: USD 현금과 USD 표시 자산의 KRW 환산 비중

차트는 다음 원칙을 따릅니다.

- 자산 구성 도넛은 현금을 포함한 총자산 기준 비중을 표시하고, 조각에는 종목명 또는 현금과 비율을 표시합니다.
- 국내 상장 종목은 ticker보다 기업명을 우선 표시합니다. 티커는 legend, hover, 상세 열에서 함께 확인할 수 있습니다.
- 도넛 hover에는 종목명, ticker, 시장, 평가액, 비중, 오늘 변동, 총수익률이 표시됩니다.
- 작은 조각이나 많은 종목은 **기타**로 합산됩니다.
- 오늘 변동 기여도는 0 기준선을 가진 diverging horizontal bar chart입니다.
- 양수는 `positive`, 음수는 `negative`, 중립/미조회는 `neutral` 계열로 표시하며 +/− 부호와 상태 텍스트를 함께 사용합니다.
- 통화 노출은 KRW/USD 100% stacked horizontal bar를 사용합니다. 통화가 하나뿐이면 차트 대신 compact metric으로 표시합니다.

총손익과 총수익률은 평균 매수가 정보가 있는 종목 범위에서만 보조 정보로 표시됩니다. 원가 정보가 없으면 잘못된 0% 수익률을 표시하지 않습니다.

### 자산 진단

기본 진단 카드는 6개입니다.

- 최대 단일 종목 비중
- 상위 3개 종목 비중
- HHI 집중도
- 현금 비중
- USD 노출도
- 가격 데이터 상태

긴 설명은 metric의 help tooltip로 이동했습니다. 오늘 상승·하락 기여와 원가 정보 범위 같은 보조 진단은 **세부 진단** expander에서 확인합니다. 진단은 투자 권고가 아니라 현재 데이터 상태 설명입니다.

### 보유자산 표

**보유자산** 표에서는 다음을 할 수 있습니다.

- ticker 또는 종목명 검색
- 시장 필터: 전체/미국/국내
- 가격 상태 필터: 전체/문제만/최신/캐시/이전 가격/실패/미조회/수동
- 비중 progress 표시
- 상세 열 보기: 통화, 평단가, provider, 비중 표시 등 추가 정보 확인

국내 종목코드는 문자열로 유지되어 선행 0이 사라지지 않습니다.

### 자산추이 탭

**자산추이** 탭은 Supabase에 저장된 실제 snapshot 기반 **총자산 변화**를 보여줍니다. 거래내역과 외부 입출금 기록이 없으므로 CAGR, TWR, 투자성과 수익률로 해석하지 않습니다.

기간은 `1주`, `1개월`, `3개월`, `전체` 중 선택할 수 있습니다. hover에는 KST 시각, 총자산, 투자자산, 총현금, USD/KRW가 표시됩니다.

스냅샷은 아래 시점에 저장됩니다.

- 가격 새로고침이 성공한 후
- 포트폴리오 저장 후
- 사용자가 **현재 상태 기록**을 누른 경우

단순 화면 rerun만으로 snapshot을 자동 저장하지 않습니다. 로그인 후 자동 가격/환율 갱신이 성공한 경우에는 `price_refresh` snapshot이 저장될 수 있습니다. 이력은 v0.6 배포 이후부터 쌓입니다. 과거 주가로 현재 보유량을 역산해 과거 자산처럼 보이게 만들지 않습니다.

### 관리 탭

**관리** 탭에는 거래내역 CSV 다운로드, 계산된 현재 보유현황 CSV 다운로드, 저장/불러오기/삭제, 현재 상태 기록 기능이 있습니다.

거래 CSV 업로드는 **보유자산 → 자산 입력 → CSV로 한번에 입력**에서 처리합니다. Supabase 설정이 없으면 다음 안내가 표시되고 CSV 다운로드는 계속 사용할 수 있습니다.

```text
저장소가 설정되지 않아 CSV 방식만 사용할 수 있습니다
```

## Supabase 설정

v0.8 과거 보유현황 스케줄 저장/불러오기를 사용하려면 새 Supabase migration을 한 번 실행해야 합니다. 기존 v0.5 저장 테이블과 v0.6 자산 이력 테이블은 그대로 유지합니다.

처음 설정하는 경우:

1. Supabase 프로젝트를 만듭니다.
2. Supabase **SQL Editor**에서 `docs/supabase_schema.sql` 파일의 내용을 복사해 실행합니다.
3. 이어서 `docs/supabase_migration_v0_6.sql` 파일의 내용을 복사해 실행합니다.
4. 이어서 `docs/supabase_migration_v0_8_historical_holdings.sql` 파일의 내용을 복사해 실행합니다.
5. 외부 사용자용 앱을 배포할 경우 `docs/supabase_migration_v2_auth_rls.sql` 파일의 내용도 복사해 실행합니다.
6. Streamlit Cloud **App settings → Secrets**에 아래 값을 추가합니다.

이미 v0.6까지 설정한 경우:

1. 기존 `portfolio_snapshots`와 자산 이력 테이블은 유지합니다.
2. Supabase **SQL Editor**에서 `docs/supabase_migration_v0_8_historical_holdings.sql` 파일의 내용을 복사해 실행합니다.
3. 외부 사용자용 앱을 배포할 경우 `docs/supabase_migration_v2_auth_rls.sql` 파일의 내용을 복사해 실행합니다.
4. Streamlit Cloud 앱을 **Reboot** 또는 **Redeploy**합니다.

SQL Editor에는 `docs/supabase_migration_v0_8_historical_holdings.sql` 같은 파일 경로를 입력하지 않습니다. GitHub에서 해당 파일을 열고 SQL 전체 내용을 복사한 뒤 Supabase SQL Editor 입력창에 붙여넣고 **Run**을 누릅니다.

Streamlit Secrets 예시는 다음과 같습니다. 실제 값을 GitHub에 넣지 마세요.

```toml
APP_AUTH_SCOPE = "all"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"

[ACCOUNTS.jisung]
password = "strong-password-placeholder"
owner_id = "jisung-main"
default_portfolio = "main"
```

`SUPABASE_SERVICE_ROLE_KEY`는 Supabase 데이터에 강한 권한을 가진 비밀키입니다. 절대 GitHub 코드, README, 이슈, PR 댓글, `.env`, `.streamlit/secrets.toml`에 커밋하거나 붙여넣지 마세요. Streamlit Cloud Secrets 화면에만 입력합니다.

기존 단일 계정 방식도 계속 지원합니다. 계정 목록을 쓰지 않을 경우에는 `APP_PASSWORD`, `PORTFOLIO_OWNER_ID`, 선택 사항인 `DEFAULT_PORTFOLIO_NAME`을 사용합니다.

```toml
APP_PASSWORD = "strong-password-placeholder"
APP_AUTH_SCOPE = "all"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
PORTFOLIO_OWNER_ID = "jisung-main"
DEFAULT_PORTFOLIO_NAME = "main"
```

v0.8 과거 보유현황 재구성을 위해 별도 Secret은 추가하지 않습니다. Supabase 스케줄 저장/불러오기는 로그인 계정의 `owner_id` 또는 기존 `PORTFOLIO_OWNER_ID`를 그대로 사용합니다.

미국 주식 가격 새로고침과 USD/KRW 환율 갱신에는 `ALPHA_VANTAGE_API_KEY`가 필요하지 않습니다.

### 공용 로그인 앱

기존 개인 테스트 앱은 그대로 두고 외부 사용자용 앱을 새로 만들려면 Streamlit Community Cloud에서 **New app**을 하나 더 생성하고 Main file path를 `app/public_portfolio_dashboard.py`로 지정합니다.

공용 앱은 첫 화면에 **로그인**과 **회원가입** 탭을 표시합니다. 사용자는 Supabase Auth 이메일/비밀번호 계정으로 로그인하고, 앱은 Supabase Auth의 `user.id`를 `owner_id`로 사용해 해당 사용자 포트폴리오만 자동 저장/불러옵니다.

공용 앱 배포 전 Supabase SQL Editor에서 `docs/supabase_migration_v2_auth_rls.sql` 파일의 SQL 전체를 복사해 실행합니다. 파일 경로를 입력하지 말고, SQL 내용을 붙여넣은 뒤 **Run**을 누릅니다. 이 migration은 `portfolio_snapshots`, `portfolio_value_history`, `historical_holding_schedules` 테이블이 없으면 먼저 만든 뒤 RLS 정책을 적용합니다.

기존 `docs/supabase_migration_v1_public_accounts.sql`와 `public_accounts` 테이블은 legacy 계정 방식 호환을 위해 남겨둡니다. 새 외부 사용자용 앱은 `public_accounts`를 사용하지 않습니다.

공용 앱 Secrets 예시는 다음과 같습니다.

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "your-publishable-or-anon-key"
PUBLIC_USER_AUTH = true
AUTH_SESSION_SECRET = "replace-with-32-plus-random-character-secret"
```

`SUPABASE_PUBLISHABLE_KEY` 대신 Supabase 프로젝트에 표시되는 `anon` key를 `SUPABASE_ANON_KEY` 이름으로 넣어도 됩니다. 공용 앱에는 `SUPABASE_SERVICE_ROLE_KEY`를 넣지 않습니다.

`AUTH_SESSION_SECRET`은 로그인 유지 쿠키 암호화용 앱 비밀값입니다. 32자 이상의 임의 문자열을 사용하고 Supabase publishable/anon/service role key를 재사용하지 마세요. 이 값이 없으면 로그인 화면의 로그인 유지 체크박스는 비활성화됩니다.

`app/public_portfolio_dashboard.py`는 공용 인증 모드를 자동으로 켭니다. 같은 `app/portfolio_dashboard.py` 파일을 공용 앱으로 쓰고 싶다면 Secrets에 아래 값을 추가해도 됩니다.

```toml
PUBLIC_USER_AUTH = true
```

공용 앱에는 `APP_PASSWORD`, `ACCOUNTS`, `PORTFOLIO_OWNER_ID`를 넣지 않아도 됩니다. 가입한 사용자마다 Supabase Auth `user.id` 기준으로 `owner_id`가 자동 분리됩니다. 공개 앱은 사용자별 `main` 포트폴리오 하나만 자동으로 저장/불러오며, 별도 저장/불러오기 UI를 표시하지 않습니다.

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
6. Python version은 `3.11` 또는 `3.12`를 선택합니다. 로그에 `/python3.14/`가 보이면 App settings > Advanced settings에서 `3.12`로 바꾼 뒤 저장합니다.
7. **Deploy**를 클릭합니다.

Secrets를 수정했거나 `app/requirements.txt`가 바뀐 경우 Streamlit Cloud에서 앱을 Reboot 또는 Redeploy 해야 새 설정과 의존성이 반영됩니다. 대시보드는 `streamlit==1.50.0`으로 고정되어 있으므로 merge 후 Reboot 또는 Redeploy가 필요합니다.

외부 사용자용 새 앱은 같은 절차로 만들되 Main file path에 `app/public_portfolio_dashboard.py`를 입력합니다. 기존 개인 테스트 앱 URL은 그대로 두고, 새 앱 URL만 외부 사용자에게 공유합니다.

외부 사용자용 앱은 `.streamlit/config.toml`의 `client.toolbarMode = "viewer"` 설정과 공개 앱 전용 CSS guard로 앱 내부 Streamlit toolbar 노출을 줄입니다. Streamlit Cloud가 앱 바깥 wrapper에 붙이는 **Manage app**은 앱 코드에서 안전하게 제어하는 대상이 아닙니다.

실제 보안 경계는 아래 권한과 비밀값 관리입니다.

- 일반 이용자에게 GitHub 저장소 collaborator 권한을 주지 않습니다.
- 일반 이용자에게 Streamlit Community Cloud workspace 접근 권한을 주지 않습니다.
- 공용 앱 Secrets에는 `SUPABASE_SERVICE_ROLE_KEY`를 넣지 않고 `SUPABASE_PUBLISHABLE_KEY` 또는 `SUPABASE_ANON_KEY`만 둡니다.
- Supabase에는 `docs/supabase_migration_v2_auth_rls.sql`의 RLS 정책을 적용합니다.
- 운영자 계정으로 로그인한 브라우저에서는 **Manage app**이 보일 수 있습니다. 일반 사용자 화면 검수는 로그아웃 상태, 시크릿 창, 또는 운영 권한이 없는 별도 계정으로 확인합니다.
- Streamlit Cloud **App settings > Sharing**, Streamlit workspace 구성원, GitHub repository collaborator 권한에서 일반 사용자가 개발자/관리자 권한을 갖지 않도록 확인합니다.

## UI 검수 체크리스트

- 데스크톱: KPI 4개, 도넛, 통화 노출, 변동 기여도, 진단 카드가 한 화면에서 과도하게 밀리지 않는지 확인합니다.
- 모바일: 헤더 시간, KPI 값, 가격 상태, 보유자산 표가 잘리지 않는지 확인합니다.
- 빈 포트폴리오: 개요 탭에 여러 빈 차트 대신 onboarding 안내가 표시되는지 확인합니다.
- 일부 가격 실패: 상단에는 요약 경고 하나만 보이고, 상세는 **데이터 업데이트 상세** expander에서 확인되는지 봅니다.
- 다크 테마: 차트 배경이 투명하게 유지되고 텍스트와 hover가 읽히는지 확인합니다.
- 저장 상태: 개인 테스트 앱은 보유자산, 현금, 환율을 바꾸면 **저장하지 않은 변경 있음**이 표시되고 저장 후 **저장됨**으로 돌아오는지 확인합니다. 외부 사용자용 앱은 변경 후 **저장됨** 또는 **저장 실패** 자동 저장 상태가 표시되는지 확인합니다.

## 향후 개선

미국 주식 provider는 현재 yfinance 기반 무료 데이터 소스를 사용하고, 국내 주식 provider는 FinanceDataReader 기반 무료 데이터 소스를 사용합니다. 무료 데이터 소스는 구조가 바뀌거나 차단될 수 있습니다. 장기적으로는 한국투자증권 Open API, Finnhub, Polygon.io 같은 provider를 선택 옵션으로 추가할 수 있습니다. KIS appkey, appsecret, access token 같은 실제 인증 정보는 코드나 README에 넣지 않고 Streamlit Secrets 같은 비밀 저장소로만 관리해야 합니다.

## 보안 및 데이터 정책

- API key, APP_PASSWORD, Supabase service role key를 코드나 README에 실제 값으로 넣지 않습니다.
- KIS appkey, appsecret, access token 같은 공식 증권 API 인증 정보도 코드나 README에 넣지 않습니다.
- `.env`, `.streamlit/secrets.toml`, SQLite DB, cache 파일을 커밋하지 않습니다.
- 실제 보유종목, 수량, 평단을 코드나 테스트에 하드코딩하지 않습니다.
- 개인 테스트 앱은 단일 사용자 설정을 유지합니다. 외부 사용자용 앱은 Supabase Auth 기반 로그인/회원가입과 RLS 기반 사용자별 `owner_id` 분리를 사용합니다. OAuth와 팀 계정은 이번 버전 범위 밖입니다.
- “매수”, “매도”, “추천” 같은 투자 권고 표현은 사용하지 않습니다.

## Tests

테스트 전용 의존성을 설치합니다.

```bash
python -m pip install -r requirements-dev.txt
```

테스트에는 formatter/status/chart 순수 함수 테스트와 `streamlit.testing.v1.AppTest` 기반 smoke test가 포함됩니다. AppTest는 핵심 KPI 4개, 기본 탭, 가격 로그 상세 expander, raw ISO 시간 미노출을 확인합니다. `requirements-dev.txt`에는 이 테스트를 위해 `streamlit==1.50.0`이 포함됩니다.

테스트를 실행합니다.

```bash
pytest -q
```
