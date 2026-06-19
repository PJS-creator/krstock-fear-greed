# Portfolio Dashboard MVP

이 MVP는 보유 종목, 수량, 평균단가, 현금, USD/KRW 환율을 기반으로 총자산, 일간 손익, 총손익, 비중, 목표 비중 차이를 계산한다.

## 현재 범위

- Streamlit 대시보드
- 표준 라이브러리 기반 fallback HTML 대시보드
- 샘플 포트폴리오
- KRW/USD 환산 계산
- currency mismatch 및 음수 입력 validation
- 총자산/손익/비중 계산 테스트
- SQLite 초기화 스크립트

## 계산 정책

- 지원 통화는 `KRW`, `USD`로 제한한다.
- `Position.currency`와 `Quote.currency`가 다르면 계산을 중단하고 `ValueError`를 발생시킨다.
- short position은 MVP 범위에서 제외한다.
- `total_pnl_pct`는 현금을 제외한 투자 포지션 원금 대비 수익률이다.

## 다음 단계

1. FMP/KIS 등 가격 공급자 인터페이스 추가
2. Quote TTL 캐시
3. 포지션 CRUD UI
4. 목표 비중 기반 리밸런싱 제안 고도화
5. PostgreSQL 전환 시 `NUMERIC`, `TIMESTAMPTZ`, quote cache/history 분리 검토
