# 메타전략 외부 스케줄러와 미수신 감시

## 목적

GitHub Actions의 `schedule` 이벤트가 지연되어도 아침 판정과 누락 경고를 별도 경로로 실행합니다. 기존 GitHub 예약은 그대로 유지하고 Cloudflare Worker Cron을 보조 경로로 사용합니다.

| 경로 | KST 시각 | 동작 |
|---|---:|---|
| 기존 공식 예약 | 07:37 / 07:57 | 공식 메타전략 계산 및 재시도 |
| 기존 대안 예약 | 07:47 / 08:07 | 대안 shadow 전략 계산 및 재시도 |
| 외부 보충 실행 | 07:50 | 당일 GitHub 알림이 없는 전략만 `workflow_dispatch` |
| 외부 미수신 감시 | 08:20 | 누락 전략 재호출 후 해당 알림 Issue에 경고 댓글 게시 |

Worker는 GitHub Actions 안에서 실행되지 않습니다. 따라서 GitHub의 예약 이벤트 큐가 밀려도 GitHub REST API를 통해 별도로 실행을 요청하고, 08:20 경고 댓글도 Worker가 직접 게시합니다. GitHub API 전체가 중단된 경우에는 호출과 댓글 모두 실패할 수 있으며 이 실패는 Cloudflare Worker 로그에서 확인합니다.

## 중복 방지

- 공식 알림은 `<!-- meta-strategy-notification:YYYY-MM-DD:` 표시를 확인합니다.
- 대안 알림은 `<!-- alternative-strategy-notification:YYYY-MM-DD:` 표시를 확인합니다.
- 이미 당일 알림이 있으면 07:50 보충 실행을 생략합니다.
- 08:20 경고는 전략별 `strategy-schedule-watchdog` 표시로 하루 한 번만 게시합니다.
- 외부 호출과 뒤늦은 GitHub 예약 실행이 겹쳐도 기존 워크플로의 concurrency와 알림 marker 검사가 중복 댓글을 막습니다.

## 최초 설정

### 1. Cloudflare 준비

Cloudflare 계정에서 Workers를 사용할 수 있어야 합니다. 배포용 API Token에는 해당 계정의 **Workers Scripts: Edit** 권한만 부여합니다.

### 2. GitHub fine-grained token 준비

외부 Worker가 이 저장소만 조작할 수 있는 fine-grained personal access token을 만듭니다.

- Repository access: `PJS-creator/krstock-fear-greed`만 선택
- Actions: Read and write
- Issues: Read and write
- Metadata: Read

Contents 쓰기, Administration, Supabase, Streamlit 비밀값 권한은 필요하지 않습니다. 만료일을 설정하고 토큰을 코드나 `wrangler.toml`에 기록하지 않습니다.

### 3. GitHub Actions secrets 등록

저장소 **Settings > Secrets and variables > Actions**에 다음 Repository secrets를 등록합니다.

| Secret | 값 |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Workers Scripts 편집용 Cloudflare API Token |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Account ID |
| `EXTERNAL_SCHEDULER_GITHUB_TOKEN` | 위에서 만든 최소 권한 GitHub fine-grained token |

### 4. Worker 배포

1. PR 병합 후 저장소의 **Actions**로 이동합니다.
2. **Deploy external strategy scheduler**를 선택합니다.
3. **Run workflow**를 한 번 실행합니다.
4. Cloudflare Workers의 `jisungport-strategy-scheduler`에서 Cron Triggers 두 개와 `GITHUB_TOKEN` secret을 확인합니다.

배포 워크플로는 `EXTERNAL_SCHEDULER_GITHUB_TOKEN`을 실행 중에만 존재하는 권한 제한 파일로 전달해 Worker 코드와 Cloudflare의 암호화된 `GITHUB_TOKEN` secret을 함께 배포합니다. 임시 파일은 배포 단계가 끝날 때 삭제되며, 토큰은 GitHub 코드나 Worker 일반 변수에 기록하지 않습니다.

## 확인 방법

- 로컬 단위 테스트: `cd external-scheduler` 후 `npm test`
- 외부 보충 실행 기록: 각 전략 Actions run의 `run_slot`이 `external-0750-kst`
- 감시 재호출 기록: `run_slot`이 `external-watchdog-0820-kst`
- 공식 누락 경고: [Issue #127](https://github.com/PJS-creator/krstock-fear-greed/issues/127)
- 대안 누락 경고: [Issue #130](https://github.com/PJS-creator/krstock-fear-greed/issues/130)

정상일에는 08:20 경고가 게시되지 않습니다. 경고가 게시되면 링크된 Actions 화면에서 실행 대기 여부를 확인하고, 당일 판정 댓글이 뒤늦게 도착했는지 확인합니다.
