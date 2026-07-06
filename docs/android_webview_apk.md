# Android WebView 테스트 APK

이 문서는 Streamlit 공개 앱을 Android WebView로 감싼 테스트용 APK를 만드는 방법을 설명합니다.

## 범위

- WebView 기본 URL: `https://jisungport.streamlit.app`
- APK 유형: debug APK
- 앱 이름: `JisungPort`
- 패키지명: `com.pjscreator.jisungport`

이 wrapper는 기존 Streamlit 앱 코드, Supabase 구조, 배포 Secrets를 변경하지 않습니다. Play Store 배포, release signing, AAB 생성은 포함하지 않습니다.

## GitHub Actions에서 APK 만들기

### PR에서 확인

1. Android wrapper 변경 PR을 엽니다.
2. PR의 **Android debug APK / Build WebView debug APK** 체크가 끝날 때까지 기다립니다.
3. 해당 workflow run을 열고 **Artifacts**에서 `jisungport-debug-apk`를 내려받습니다.
4. 압축을 풀면 `app-debug.apk`가 있습니다.

### main 병합 후 수동 생성

1. GitHub 저장소에서 **Actions**를 엽니다.
2. **Android debug APK** workflow를 선택합니다.
3. **Run workflow**를 누릅니다.
4. 실행이 끝나면 workflow run의 **Artifacts**에서 `jisungport-debug-apk`를 내려받습니다.
5. 압축을 풀면 `app-debug.apk`가 있습니다.

`Run workflow` 버튼은 workflow 파일이 main에 들어간 뒤 표시됩니다. PR에서 `android-webview/**` 또는 `.github/workflows/android-debug-apk.yml`이 바뀌면 같은 workflow가 자동으로 APK 빌드를 확인합니다.

## Android 기기에 설치

### 파일로 설치

1. `app-debug.apk`를 Android 기기로 옮깁니다.
2. 파일 앱에서 APK를 엽니다.
3. Android가 요청하면 해당 파일 앱 또는 브라우저의 **알 수 없는 앱 설치**를 허용합니다.
4. 설치 후 `JisungPort` 앱을 실행합니다.

### ADB로 설치

PC에 Android platform-tools가 있으면 아래 명령으로 설치할 수 있습니다.

```bash
adb install -r app-debug.apk
```

## 수동 QA 체크리스트

- [ ] APK가 Android 기기에 설치된다.
- [ ] 앱 실행 시 `https://jisungport.streamlit.app`이 열린다.
- [ ] 로그인 화면이 표시된다.
- [ ] 로그인할 수 있다.
- [ ] 총괄현황, 세부내역, 사용자입력, 자산추이, 매매일지, 리밸런싱 탭을 이동할 수 있다.
- [ ] 가격·환율 갱신 버튼을 누를 수 있다.
- [ ] 다크/라이트 전환이 표시된다.
- [ ] Android 뒤로가기 버튼이 WebView 이전 페이지로 먼저 이동한다.
- [ ] 상단 상태바와 하단 내비게이션바 영역에 화면 내용이 겹치지 않는다.
- [ ] 네트워크 오류 상태에서 재시도 화면이 표시된다.

## 제한

- 테스트용 debug signing APK입니다.
- Play Store 배포용 signing 설정은 없습니다.
- AAB는 생성하지 않습니다.
- Streamlit Cloud, Supabase Auth/RLS, 저장 구조는 기존 웹앱 설정을 그대로 사용합니다.
