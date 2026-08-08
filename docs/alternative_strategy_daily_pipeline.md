# 대안 N1/A1/V4 shadow v3.0 일일 파이프라인

## 목적과 분리 원칙

전략 `qqq_meta_v1_red_router_s1_n1_a1_v4_shadow_v3_0`을 기존 공식 메타전략과 별도로 매일 판정합니다.

- 공식 판정은 기존 `.github/workflows/meta-strategy-daily.yml`, `meta-strategy-data`, Issue #127을 그대로 사용합니다.
- 쉐도우 판정은 `.github/workflows/alternative-strategy-daily.yml`, `alternative-strategy-data`, Issue #130만 사용합니다.
- 두 경로는 같은 Tiingo adjusted 가격과 FRED 원자료를 사용하지만 결과 파일, 실행 이력, 알림 marker가 서로 다릅니다.
- v3.0은 shadow 검증 전용이며 실제 주문, 계좌 연동, 자동 매매를 수행하지 않습니다.

전략 원본 계약은 다음 파일에 보존합니다.

```text
config/strategies/qqq_meta_v1_red_router_s1_n1_a1_v4_shadow_v3_0.kis.yaml
```

## 판정 순서

1. 공식 계산 규칙으로 Meta-v1.0, 유동성 P, 히스테리시스, SMA20 회복, 비교1·비교3, RED Router-S1을 계산합니다.
2. 공식 `overall_execution_target`을 N1 전 `base_execution_target`으로 기록합니다.
3. `BULL`, 비교3 정책, 기준 목표 `QLD`, Router 비활성 조건이 모두 맞으면 N1이 `QLD`를 `QQQ`로 바꿉니다.
4. 2010-02-11 고정 anchor부터 완료 거래일 전체를 재생해 A1 상태를 결정합니다.
5. A1 적용 후 최종 목표가 `QLD`이고 QQQ 종가/SMA50이 1.05 이상일 때만 신규진입 V4를 평가합니다.

공식 상태머신과 공식 산출물은 수정하지 않습니다. 쉐도우 JSON에는 `base_execution_target`, `post_n1_execution_target`, `a1_overlay`, `resolved_execution_target`을 모두 남깁니다.

## A1 레버리지 단조성 래치

A1은 위험 상태가 약해지는 순간 실행 레버리지가 커지는 특정 경로만 차단합니다.

- 진입: 직전 subtype `BULL`, 현재 `UP_MIXED`, 직전 실행/가상 목표 `QQQ`, post-N1 목표 `QLD`, 비교3 목표 `QLD`, Router 비활성
- 동작: 최종 shadow target을 `QQQ`로 래치
- 유지: `UP_MIXED`, 비교3가 `TQQQ`가 아님, Router 비활성
- 해제: `UP_MIXED` 이탈, 비교3 `TQQQ`, Router 활성 중 하나
- 재진입 제한: 같은 `UP_MIXED` episode에서는 다시 진입하지 않으며, 해당 subtype을 벗어난 뒤 재무장

매일 최신 한 행만 전일 산출물과 비교하지 않고, 고정 anchor부터 전체 기술 상태를 결정론적으로 재생합니다. 따라서 최초 v3.0 배포나 중간 실행 실패 뒤에도 A1 상태가 동일 입력에서 동일하게 복원됩니다. `a1_overlay.event_history`에는 ENTER, RELEASE, REARM 계보를 남깁니다.

## 신규진입 V4 표시 범위

`entry_filter_v4`는 **오늘 신규 자본으로 시작한다고 가정한 shadow 집행안**입니다.

- 발동 조건: post-A1 최종 목표 `QLD` 및 QQQ SMA50 상방이격률 5% 이상
- 발동 시: 예정 실행 시가에 최종 목표 50%, 현금 50%
- 유예 기간: 60개 완료 공통 거래일
- 유예 중: 투자된 절반은 매일의 post-A1 목표를 추종
- 유예 종료: 다음 공통 거래일 시가에 현금 절반도 당시 post-A1 목표에 합류
- 미발동 시: 예정 실행 시가에 post-A1 목표 100%

수수료 편도 0.25%, 슬리피지 편도 0.1%, 거래세 0%는 `cost_assumptions`에 기록합니다. 일일 목표자산 판정 자체에는 비용을 차감하지 않습니다.

## 실행 시간과 데이터

- 본 실행: 매일 07:47 KST
- 재시도: 매일 08:07 KST
- 수동 실행: **Actions > Alternative shadow v3.0 strategy daily signal > Run workflow**
- Secret: Repository secret `TIINGO_API_TOKEN`
- 영구 산출물 브랜치: `alternative-strategy-data`
- 원자료 감사 artifact: `alternative-strategy-audit-<run id>-<attempt>`

공식 파이프라인보다 10분 늦게 실행해 같은 토큰으로 원자료를 동시에 요청할 가능성을 줄입니다.

## 산출물과 실패 정책

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

같은 거래일이라도 원자료 해시, v3.0 YAML 해시, 계산 버전이 달라지면 다시 계산합니다. 원자료와 계약이 모두 같으면 `NO_NEW_SESSION`을 남깁니다. 실패 실행은 `runs`에 기록하지만 직전 검증 완료 결과를 덮어쓰지 않습니다.

## GitHub 알림과 Streamlit 표시

대안 결과는 [대안 shadow 전략 일일 판정 알림 Issue #130](https://github.com/PJS-creator/krstock-fear-greed/issues/130)에 게시합니다.

알림에는 시장구간, N1 전·후 목표, A1 이벤트와 subtype 전이, 최종 shadow target, 신규진입 V4, 적용 P, QQQ/SMA50, RSI 참고 경고가 포함됩니다. Issue의 **Subscribe**와 GitHub 알림 설정에서 이메일을 켜면 매일 별도 알림을 받을 수 있습니다.

공개 Streamlit 앱은 `alternative-strategy-data/signals/latest_validated.json`에서 **검증 완료된 현재 v3.0 전략 ID**만 읽습니다. 총괄현황의 공식 메타전략 아래에 별도 `쉐도우 전략 v3.0` 카드로 표시하며, v2.1 산출물이나 검증 실패 결과를 v3.0으로 표시하지 않습니다.

## 배포 확인

1. PR을 병합합니다.
2. Actions에서 **Alternative shadow v3.0 strategy daily signal**을 수동 실행합니다.
3. `alternative-strategy-data/signals/latest_validated.md`에서 N1, A1, 최종 target을 확인합니다.
4. Issue #130에 v3.0 별도 댓글이 게시되는지 확인합니다.
5. Streamlit 앱을 재부팅하거나 캐시 TTL 이후 새로고침해 공식 메타전략 아래 쉐도우 카드를 확인합니다.
6. 공식 `meta-strategy-data`와 Issue #127이 변경되지 않았는지 확인합니다.
