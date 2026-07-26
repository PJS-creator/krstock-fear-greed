# ChatGPT 08:10 KST 작업 프롬프트

아래 내용은 GitHub Actions 공식 산출물이 최초로 생성된 뒤 ChatGPT 예약 작업에 사용합니다.

```text
매일 08:10 KST에 다음 순서로 RED Router-S1 공식 판정을 설명해 주세요.

1. 먼저 아래 runs 파일을 읽으세요.
https://raw.githubusercontent.com/PJS-creator/krstock-fear-greed/meta-strategy-data/runs/latest_run.json

2. 다음으로 마지막 검증 완료 signal을 읽으세요.
https://raw.githubusercontent.com/PJS-creator/krstock-fear-greed/meta-strategy-data/signals/latest_validated.json

3. runs 상태가 VALIDATED이면 당일 판정을 설명하세요.
4. NO_NEW_SESSION이면 신규 완료 거래일이 없다고 먼저 알리고 마지막 검증 완료 판정을 설명하세요.
5. CONFIG_FAILED, SOURCE_FAILED, VALIDATION_FAILED, UNEXPECTED_FAILED이면 갱신 불가 사유를 먼저 알리고, signal의 직전 검증 완료 값을 "직전 검증 완료 값"으로 명시해 설명하세요.
6. 직접 P, RSI, 이동평균, Router를 다시 계산하거나 웹의 다른 값으로 대체하지 마세요.
7. 다음 항목을 간결히 설명하세요.
   - 판정 거래일과 예정 실행일
   - 시장구간
   - 활성화 전략
   - Router 목표자산
   - 전체 실행 목표자산
   - P 값과 rank_less/rank_equal/260 계보
   - QQQ 종가, SMA50, 상방이격률
   - 신규 자금 유입 시 집행 방식
   - RSI14 참고 경고와 최근 5거래일 흐름
   - 결측 또는 fallback reason code
8. 자동 매매나 투자 추천이 아니라 규칙 기반 상태 설명임을 마지막에 한 문장으로 표시하세요.
```

이 작업은 PR 병합 및 `meta-strategy-data` 브랜치 최초 생성 이후 등록합니다.
