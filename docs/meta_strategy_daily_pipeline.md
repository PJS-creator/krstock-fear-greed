# 메타전략 공식 일일 파이프라인

## 운영 구조

메타전략은 두 경로를 동시에 유지합니다.

1. **GitHub Actions 공식 판정**
   - 매일 07:37 KST에 실행합니다.
   - 원자료가 아직 준비되지 않았거나 검증에 실패하면 07:57 KST에 다시 확인합니다.
   - Tiingo 조정주가와 FRED 지표 전체 이력을 다시 계산합니다.
   - 검증을 통과한 결과만 `meta-strategy-data` 브랜치의 공식 판정을 갱신합니다.
2. **Streamlit 앱 미리보기**
   - 기존 Yahoo/FRED 즉시 조회 코드를 삭제하지 않습니다.
   - 사용자가 가격·환율 갱신을 누르면 앱 프로세스에서 별도로 계산합니다.
   - 공식 판정이 있으면 화면의 주 판정은 공식 결과를 사용하고 앱 계산은 `미리보기`로 표시합니다.

공식 계산이 끝나면 [공식 메타전략 일일 알림 Issue](https://github.com/PJS-creator/krstock-fear-greed/issues/127)에 `@PJS-creator` 판정 요약을 게시합니다. 본 실행이 실패하면 07:57 재시도 결과까지 기다린 뒤 최종 상태를 알리고, 본 실행이 성공한 날의 재시도는 중복 알림을 만들지 않습니다.

Streamlit 공개 앱에는 Tiingo 토큰을 넣지 않습니다. `TIINGO_API_TOKEN`은 GitHub 저장소의 **Settings > Secrets and variables > Actions**에만 저장합니다.

## 데이터 기준

### 가격

- 공식 가격 공급자: Tiingo
- 사용 가격: adjusted close
- 공식 신호 종목: QQQ
- Router 가격 종목: GLD
- Yahoo 가격은 앱 미리보기 및 비교 확인용이며 공식 판정을 자동 대체하지 않습니다.

### 유동성

- `WALCL`과 `WDTGAL`은 같은 수요일 관측치만 결합합니다.
- `RRPONTSYD`도 같은 수요일 값을 사용하고, 해당 날짜가 비어 있으면 0으로 처리합니다.
- 다른 주의 값을 앞으로 채우지 않습니다.
- 수요일 관측치를 금요일 신호 행으로 표시합니다.
- 26주 로그 성장률, 13주 평균, 직전 260주 순위를 계산합니다.
- 현재 주는 순위 모집단에서 제외하고 동률은 0.5 가중치로 계산합니다.
- 계산된 P는 한 주 뒤 신호 행에 적용합니다.
- `rank_less`, `rank_equal`, 분모 260을 산출물에 함께 기록합니다.

검증 기준 예시는 다음과 같습니다.

- 2026-07-10 원 P: `210 / 260 * 100 = 80.7692307692`
- 2026-07-17 적용 행, 2026-07-20 거래일부터 사용
- 2026-07-17 원 P: `213 / 260 * 100 = 81.9230769231`
- 2026-07-24 적용 행, 2026-07-27 거래일부터 사용

### RED Router-S1

- 최종 시장구간이 `BEAR`이고 비교1 확정 상태가 `RED`로 새로 진입할 때만 Router를 평가합니다.
- 우선순위는 `QQQ > GLD > XLV`입니다.
- 필요한 Router 입력 하나라도 없으면 전략 규칙에 따라 `XLV`를 선택하되, 산출물에는 결측 사유 코드를 별도로 기록합니다.
- 선택 결과는 비교1 RED 또는 최종 BEAR를 벗어날 때까지 유지합니다.
- `router_target`과 전체 전략의 `overall_execution_target`은 별도 필드입니다.

### 신규 진입 제한

다음 두 조건을 모두 충족하면 신규 자금 유입 시에만 50/50 분할 안내를 표시합니다.

- 전체 실행 목표자산이 QLD
- QQQ의 SMA50 상방이격률이 5% 이상

즉시 50%는 예정 실행일의 QLD를 전제로 합니다. 나머지 50%의 기준일은 최초 예정 실행 거래일을 인덱스 0으로 보고 60번째 이후 XNYS 거래일입니다. 유예분은 QLD로 고정하지 않고 그날의 Router/전체 전략 판정을 다시 사용합니다.

현재 버전은 실제 신규 입금 lot를 저장하지 않는 **가정형 안내**입니다. 자동 주문, 실제 유예 자금 상태, 체결 원장은 생성하지 않습니다.

### RSI 참고 경고

- QQQ Wilder RSI14가 60 이상이면 참고 경고를 표시합니다.
- 최근 5거래일 종가, 일간 수익률, RSI, 5일 누적 수익률, 상승일과 하락일 수를 기록합니다.
- 최근 흐름은 `상승 지속`, `상승 둔화`, `횡보`, `하락 전환`, `혼조` 중 하나로 표시합니다.
- 이 경고는 시장구간, 목표자산, Router, 신규 진입 제한 계산에 영향을 주지 않습니다.

## 산출물

`meta-strategy-data` 브랜치 구조는 다음과 같습니다.

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

- `signals/latest_validated.*`: 마지막 검증 완료 판정
- `runs/latest_run.json`: 마지막 유효 실행 상태
- `state/latest_state.json`: 다음 감사와 상태 비교에 필요한 최소 상태
- 루트의 `latest_signal.*`: ChatGPT 작업과 기존 외부 소비자를 위한 호환 별칭
- 원 응답 파일: 저장소에 커밋하지 않고 Actions artifact로 90일 보관

`SOURCE_FAILED`, `VALIDATION_FAILED`, `CONFIG_FAILED` 실행은 `runs/history`에 남지만 `signals/latest_validated`를 덮어쓰지 않습니다. 07:57 재시도 시 같은 거래일의 검증 완료 결과가 이미 있으면 `NO_NEW_SESSION` 기록만 추가하고 `runs/latest_run.json`의 성공 상태를 유지합니다.

## 배포 설정

1. GitHub 저장소 **Settings > Secrets and variables > Actions**로 이동합니다.
2. Repository secret `TIINGO_API_TOKEN`을 추가합니다.
3. 이 PR을 병합합니다.
4. **Actions > Meta strategy daily signal > Run workflow**에서 최초 수동 실행을 합니다.
5. `meta-strategy-data` 브랜치와 Actions artifact 생성 여부를 확인합니다.

필요하면 Streamlit Cloud Secrets에 공식 JSON 위치만 재정의할 수 있습니다.

```toml
META_STRATEGY_SIGNAL_URL = "https://raw.githubusercontent.com/PJS-creator/krstock-fear-greed/meta-strategy-data/signals/latest_validated.json"
```

기본값이 같은 공개 URL이므로 일반적으로 추가 설정은 필요 없습니다.

## ChatGPT 작업 연결

ChatGPT 예약 작업은 08:10 KST에 먼저 아래 파일을 읽습니다.

1. `runs/latest_run.json`
2. `signals/latest_validated.json`

실행 실패 또는 신규 데이터 없음 상태를 먼저 설명하고, 마지막 검증 완료 신호를 임의로 새 계산하지 않습니다. 실제 작업 생성용 프롬프트는 `docs/chatgpt_meta_strategy_task_prompt.md`를 사용합니다.

## GitHub 및 이메일 알림

1. [공식 메타전략 일일 알림 Issue #127](https://github.com/PJS-creator/krstock-fear-greed/issues/127)를 엽니다.
2. 우측의 **Subscribe**가 활성화되어 있는지 확인합니다.
3. GitHub **Settings > Notifications**에서 `On GitHub`와 `Email`을 활성화합니다.

워크플로는 별도 SMTP 비밀번호나 개인 액세스 토큰 없이 저장소 기본 `GITHUB_TOKEN`의 `issues: write` 권한으로 댓글을 게시합니다. 댓글에는 실행 상태, 판정일, 시장구간, 전략, 목표자산, P, 신규 자금 집행 방식, RSI 참고 경고와 상세 산출물 링크가 포함됩니다. 알림 댓글 게시가 실패하더라도 공식 신호 계산과 `meta-strategy-data` 저장은 유지됩니다.

## 장애 처리

- Tiingo 최신 QQQ 기준일이 마지막 완료 XNYS 거래일과 다르면 공식 신호를 갱신하지 않습니다.
- 유동성 계보를 계산할 수 없으면 직전 공식 신호를 유지합니다.
- 다음 거래일 시가는 07:37 KST에 아직 존재하지 않으므로 `execution_audit.raw_open`은 `null`과 `PENDING_NEXT_OPEN`으로 둡니다.
- 데이터 공급자 실패 시 Yahoo를 공식 판정으로 자동 승격하지 않습니다.
- GitHub Actions 로그와 raw-source artifact에서 원자료 해시와 실패 원인을 확인합니다.
