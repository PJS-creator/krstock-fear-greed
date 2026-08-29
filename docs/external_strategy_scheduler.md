# 메타전략 cron-job.org 보충 실행과 미수신 감시

## 목적

GitHub Actions의 `schedule` 이벤트가 지연되어도 외부의 `cron-job.org`가 전용 `workflow_dispatch`를 호출해 아침 판정 누락을 보충합니다. 기존 GitHub 예약은 그대로 유지합니다.

| 경로 | KST 시각 | 동작 |
|---|---:|---|
| 기존 공식 예약 | 07:37 / 07:57 | 공식 메타전략 계산 및 재시도 |
| 기존 대안 예약 | 07:47 / 08:07 | 대안 shadow 전략 계산 및 재시도 |
| cron-job.org 보충 실행 | 07:50 | 당일 GitHub 알림이 없는 전략만 `workflow_dispatch` |
| cron-job.org 미수신 감시 | 08:20 | 누락 전략 재호출 후 해당 알림 Issue에 경고 댓글 게시 |

`cron-job.org`는 `.github/workflows/external-strategy-watchdog.yml`만 호출합니다. 전용 워크플로는 GitHub 기본 토큰으로 Issue #127과 #130의 당일 marker를 확인하고, 필요한 전략 워크플로만 실행합니다. Cloudflare 계정과 Worker는 사용하지 않습니다.

이 구조는 GitHub 예약 이벤트의 지연을 우회하지만 GitHub Actions 서비스 전체가 실행 불가능한 상황까지 독립적으로 감시하지는 못합니다.

## 중복 방지

- 공식 알림은 `<!-- meta-strategy-notification:YYYY-MM-DD:` 표시를 확인합니다.
- 대안 알림은 `<!-- alternative-strategy-notification:YYYY-MM-DD:` 표시를 확인합니다.
- 이미 당일 알림이 있으면 07:50 보충 실행을 생략합니다.
- 08:20 경고는 전략별 `strategy-schedule-watchdog` 표시로 하루 한 번만 게시합니다.
- 외부 호출과 뒤늦은 GitHub 예약 실행이 겹쳐도 기존 워크플로의 concurrency와 알림 marker 검사가 중복 댓글을 막습니다.

## GitHub fine-grained token

`cron-job.org`가 GitHub workflow dispatch API를 호출할 토큰을 만듭니다.

- Resource owner: `PJS-creator`
- Repository access: `PJS-creator/krstock-fear-greed`만 선택
- Actions: Read and write
- Metadata: Read

Issue 댓글 조회와 작성은 전용 워크플로의 GitHub 기본 토큰이 담당하므로 외부 토큰에 Issues 권한을 부여할 필요가 없습니다. 만료일을 설정하고 만료 전에 교체합니다.

## cron-job.org 공통 요청 설정

두 작업 모두 아래 URL과 헤더를 사용합니다.

```text
URL
https://api.github.com/repos/PJS-creator/krstock-fear-greed/actions/workflows/external-strategy-watchdog.yml/dispatches

Request method
POST

Request headers
Accept: application/vnd.github+json
Authorization: Bearer <GitHub fine-grained token>
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

토큰에는 따옴표를 붙이지 않습니다. 요청 응답 저장은 필요하지 않으면 끄고, 토큰을 GitHub 코드나 Streamlit Secrets에 기록하지 않습니다.

### 07:50 KST 보충 실행

작업 이름 예: `JisungPort strategy fallback 07:50`

Request body:

```json
{"ref":"main","inputs":{"mode":"ensure"}}
```

### 08:20 KST 미수신 감시

작업 이름 예: `JisungPort strategy watchdog 08:20`

Request body:

```json
{"ref":"main","inputs":{"mode":"watchdog"}}
```

cron-job.org 시간대를 `Asia/Seoul`로 설정합니다. UTC로 설정해야 한다면 전날 `22:50`과 `23:20`에 실행합니다.

## 확인 방법

1. PR을 병합한 뒤 두 cron 작업을 활성화합니다.
2. cron-job.org에서 각 작업을 한 번 수동 실행하고 HTTP 2xx 응답을 확인합니다.
3. GitHub Actions의 **External strategy schedule watchdog** 실행 기록에서 `ensure` 또는 `watchdog` 입력을 확인합니다.
4. 실제로 누락된 전략이 있으면 해당 전략 Actions run의 `run_slot`이 `external-0750-kst` 또는 `external-watchdog-0820-kst`인지 확인합니다.
5. 08:20까지 누락된 경우 [Issue #127](https://github.com/PJS-creator/krstock-fear-greed/issues/127) 또는 [Issue #130](https://github.com/PJS-creator/krstock-fear-greed/issues/130)의 경고 댓글을 확인합니다.

정상일에는 08:20 경고가 게시되지 않습니다.
