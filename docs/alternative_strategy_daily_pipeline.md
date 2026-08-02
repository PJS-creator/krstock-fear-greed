# 대안 N1/V4 shadow 일일 파이프라인

## 목적과 분리 원칙

첨부 전략 `qqq_meta_v1_red_router_s1_n1_v4_shadow_v2_1`을 기존 공식 메타전략과 별도로 매일 판정합니다.

- 공식 판정은 기존 `.github/workflows/meta-strategy-daily.yml`, `meta-strategy-data`, Issue #127을 그대로 사용합니다.
- 대안 판정은 `.github/workflows/alternative-strategy-daily.yml`, `alternative-strategy-data`, Issue #130만 사용합니다.
- 두 경로 모두 같은 Tiingo adjusted 가격과 FRED 원자료를 조회하지만 결과 파일, 실행 이력, 알림 marker가 서로 다릅니다.
- 대안 판정은 shadow 검증 전용이며 실제 주문, 계좌 연동, 자동 매매를 수행하지 않습니다.

전략 원본 계약은 다음 파일에 보존합니다.

```text
config/strategies/qqq_meta_v1_red_router_s1_n1_v4_shadow_v2_1.kis.yaml
```

## 판정 순서

1. 기존 공식 계산기로 Meta-v1.0, 유동성 P, 히스테리시스, SMA20 회복, 비교1·비교3, RED Router-S1을 계산합니다.
2. 공식 결과의 `overall_execution_target`을 N1 적용 전 `base_execution_target`으로 고정 기록합니다.
3. 아래 네 조건이 모두 참일 때만 N1을 적용합니다.
   - 최종 시장구간 `BULL`
   - 활성 정책 `rsi_aggressive_immediate`
   - N1 전 기준 목표 `QLD`
   - RED Router latch 비활성
4. N1이 적용되면 다음 공통 미국 거래일 시가의 `resolved_execution_target`만 `QQQ`로 바꿉니다.
5. 신규진입 V4는 N1 적용 전 기준 목표가 `QLD`이고 QQQ 종가의 SMA50 상방이격률이 5% 이상인지 판정합니다.

N1은 공식 상태머신이나 공식 산출물을 변경하지 않습니다. 대안 JSON에는 `base_execution_target`, `n1_overlay`, `resolved_execution_target`을 모두 남겨 계산 계보를 확인할 수 있습니다.

## 신규진입 V4 표시 범위

현재 일일 파이프라인은 실제 입금 lot를 저장하지 않습니다. 따라서 `entry_filter_v4`는 **오늘 신규 자본으로 시작한다고 가정한 shadow 집행안**입니다.

- 발동 시: 예정 실행 시가에 당시 resolved target 50%, 현금 50%
- 유예 기간: 60개 완료 공통 거래일
- 유예 중: 투자된 절반은 매일의 정상 resolved target을 추종
- 유예 종료: 다음 공통 거래일 시가에 현금 절반도 당시 resolved target에 합류
- 미발동 시: 예정 실행 시가에 resolved target 100%

수수료 편도 0.25%, 슬리피지 편도 0.1%, 거래세 0%는 `cost_assumptions`에 기록합니다. 일일 목표자산 판정 자체에는 비용을 차감하지 않습니다.

## 실행 시간과 데이터

- 본 실행: 매일 07:47 KST
- 재시도: 매일 08:07 KST
- 수동 실행: **Actions > Alternative shadow strategy daily signal > Run workflow**
- Secret: 기존 Repository secret `TIINGO_API_TOKEN` 재사용
- 영구 산출물 브랜치: `alternative-strategy-data`
- 원자료 감사 artifact: `alternative-strategy-audit-<run id>-<attempt>`

공식 파이프라인보다 10분 늦게 실행해 동일 토큰으로 동시에 원자료를 요청할 가능성을 줄입니다.

## 산출물

```text
signals/latest_validated.json
signals/latest_validated.md
signals/history/YYYY-MM-DD.json
signals/history/YYYY-MM-DD.md
runs/latest_run.json
runs/history/<UTC timestamp>-<run slot>.json
state/latest_state.json
normalized/latest_inputs.json
latest_signal.json
latest_signal.md
```

같은 거래일이라도 원자료 해시나 대안 계산 버전이 달라지면 다시 계산합니다. 원자료와 계산 버전이 모두 같으면 `NO_NEW_SESSION`을 남깁니다. 실패 실행은 `runs`에 기록하지만 직전 `signals/latest_validated.*`는 덮어쓰지 않습니다.

## GitHub 알림

대안 결과는 [대안 shadow 전략 일일 판정 알림 Issue #130](https://github.com/PJS-creator/krstock-fear-greed/issues/130)에 게시합니다.

1. Issue #130을 엽니다.
2. 우측 **Subscribe**를 켭니다.
3. GitHub 계정의 **Settings > Notifications**에서 GitHub 및 이메일 알림을 활성화합니다.

알림에는 다음 정보가 포함됩니다.

- 실행 상태와 판정 거래일
- 시장구간
- N1 전 기준 목표
- N1 적용 여부
- 대안 resolved target
- 신규진입 V4 발동 여부와 오늘 시작 가정 배분
- 적용 P, QQQ 종가/SMA50, 상방이격률, RSI 참고 경고

본 실행 성공 후 재시도는 같은 marker의 중복 댓글을 만들지 않습니다. 본 실행이 실패하면 재시도 결과가 최종 알림이 됩니다.

## 최초 배포 확인

1. PR을 병합합니다.
2. Actions에서 **Alternative shadow strategy daily signal**을 수동 실행합니다.
3. `alternative-strategy-data` 브랜치 생성 여부를 확인합니다.
4. `signals/latest_validated.md`에서 N1 전 목표와 resolved target을 확인합니다.
5. Issue #130에 별도 댓글이 게시되는지 확인합니다.
6. 공식 `meta-strategy-data`와 Issue #127이 변경되지 않았는지 확인합니다.
