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
