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

v0.2부터는 공개 GitHub 코드에 실제 보유종목, 수량, 평단을 저장하지 않고 웹 화면에서 직접 입력하거나 CSV 파일로 불러와 계산할 수 있습니다. 입력 데이터는 Streamlit 브라우저 세션 안에서만 유지되며, 앱이 DB나 로그인 저장소에 저장하지 않습니다.

v0.3부터는 Alpha Vantage API key를 Streamlit Community Cloud Secrets에 설정한 경우에만 미국 USD 종목의 현재가와 전일종가를 선택적으로 자동 업데이트할 수 있습니다. API key가 없으면 기존 수동 입력과 CSV 업로드/다운로드 기능은 그대로 동작합니다.

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

공개 앱이므로 실제 보유종목, 수량, 평단, 계좌 정보, API 키, `.env`, `secrets.toml`, SQLite `.db` 파일은 GitHub 코드에 커밋하지 마세요.

### Streamlit Community Cloud 배포

Streamlit Community Cloud는 실행 파일 위치 기준으로 가까운 `requirements.txt`를 찾습니다. 이 저장소는 Cloud 배포용 의존성을 `app/requirements.txt`에 둡니다. 내용은 로컬 대시보드 의존성 파일인 `requirements-dashboard.txt`와 동일하게 유지합니다.

1. Streamlit Community Cloud에 GitHub 계정으로 로그인합니다.
2. **New app**을 선택합니다.
3. Repository는 `PJS-creator/krstock-fear-greed`를 선택합니다.
4. Branch는 `main`을 선택합니다.
5. Main file path는 `app/portfolio_dashboard.py`를 입력합니다.
6. Python version은 `3.11` 또는 `3.12`를 선택합니다.
7. Alpha Vantage 자동 업데이트를 쓰지 않을 경우 Secrets는 비워 둡니다.
8. **Deploy**를 클릭합니다.

Alpha Vantage 자동 업데이트를 사용하려면 Streamlit Community Cloud의 **Settings → Secrets** 또는 **Advanced settings → Secrets**에 다음 값을 추가합니다.

```toml
ALPHA_VANTAGE_API_KEY = "your-alpha-vantage-api-key"
```

`.streamlit/secrets.toml`, `.env`, API key, 실제 계좌/보유종목 정보는 절대 GitHub에 커밋하지 마세요. Secrets는 Streamlit Cloud 설정 화면에만 입력합니다.

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

현재 SQLite 스키마는 MVP용입니다. 나중에 PostgreSQL로 전환할 때는 금액/수량의 `NUMERIC` 타입, `TIMESTAMPTZ`, provider별 quote cache/history 분리를 검토합니다.

## Tests

테스트 전용 의존성을 설치합니다.

```bash
python -m pip install -r requirements-dev.txt
```

테스트를 실행합니다.

```bash
pytest -q
```
