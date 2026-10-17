# KingMiso 로컬 Playwright 안전 테스트

이 도구는 운영 Firebase·인증 서버·외부 API에 접속하지 않는 Windows Chromium 검사입니다. 제품 HTML은 가짜 `.invalid` origin에서 메모리로 제공하고, 저장 데이터는 새 격리 컨텍스트의 가짜 계정에만 만듭니다. 원본 81개 시나리오와 P1 18개의 기존 기대값을 그대로 사용합니다.

## 이전 검증 기록과 이번 도구의 관계

- 2026-10-18 작업 기록의 `timer-p1-regression-final-20261018`: P1 18/18 통과. 10초 타이머 지연은 식량 +24이며 저장·재접속·중복 처리와 12시간 상한도 확인했습니다.
- 그 이후 `timer-p1-final81-20261018`: 같은 최종 HTML로 원본 81개 전체를 한 번 연속 실행하여 81/81 통과, 실패·건너뜀·미실행 0건. 이전에 실패했던 영웅 완료/전투 진입 사례도 포함합니다. 모든 외부 TCP/DNS/UDP 전송은 0건이었습니다.
- 제품 소스는 로컬 커밋 `ffba7305bd2d655e2c9e306a5c0711b865bb9b57`에 보존되어 있습니다. 위 두 검사는 커밋 전에 실행됐지만 HTML 내용은 커밋과 같습니다. LF 정규화 SHA-256은 `a3ec5cd152b756f7e6008d0871195eec07d13f3eed7a48c04e0a9bcdf0ad9661`입니다.
- 위 기록은 이번 실행의 새 결과가 아닙니다. 새 도구의 결과와 시각은 각 실행의 `job.json`, `summary.json`, `*-network.json`에서 확인합니다. 기존 로그는 삭제하거나 덮어쓰지 않습니다.

## Windows 준비 — 네트워크 설치를 자동 실행하지 않음

검증된 환경은 Python 3.12, `playwright==1.62.0`, Playwright 번들 Chromium `151.0.7922.34`입니다. 별도 라이브러리는 필요하지 않습니다. Chrome 사용자 설치본·기존 사용자 프로필은 사용하지 않습니다.

기존 `.venv`와 브라우저 캐시가 있으면 그대로 사용합니다. 새 환경에서는 미리 확보한 로컬 wheel과 해당 Playwright 버전의 브라우저 캐시가 필요합니다. 이 도구는 pip 다운로드나 `playwright install`을 호출하지 않습니다. 오프라인 파일이 없으면 실행을 중단하고 준비해야 합니다.

저장소 루트에서 PowerShell 변수부터 지정합니다.

```powershell
$Repo = (Get-Location).Path
$Tool = Join-Path $Repo 'tools\kingmiso-tests-15b0ce6'
$Python = Join-Path $Tool '.venv\Scripts\python.exe'
# 기존 환경의 캐시를 명시적으로 선택하는 예:
$Browsers = Join-Path $Tool 'results\safety-run\browsers'
# 새 환경에서는 확보한 오프라인 캐시 디렉터리를 지정합니다.
# $Browsers = 'C:\offline\playwright-browsers'
```

가상환경도 없는 경우에만, 미리 확보한 wheel로 다음처럼 준비할 수 있습니다. 실행 전 파일을 확보해야 하며 인터넷 대체 경로는 사용하지 않습니다.

```powershell
py -3.12 -m venv (Join-Path $Tool '.venv')
& $Python -m pip install --no-index --find-links 'C:\offline\wheels' -r (Join-Path $Tool 'requirements.txt')
```

브라우저 캐시에는 해당 버전의 `chromium-*`, `chromium_headless_shell-*` 디렉터리가 있어야 합니다. 다른 브라우저 버전이면 제품 탐색 전에 차단합니다. 캐시 위치가 우연히 `results/`에 있어도 실행 가드와 manifest는 그곳에서 읽지 않으며, 캐시는 `--browsers`로 명시한 외부 실행 의존성입니다.

## 먼저 브라우저 없는 검사

```powershell
& $Python -B (Join-Path $Tool 'run_safe.py') --self-test
& $Python -B (Join-Path $Tool 'run_safe.py') --check --repo $Repo
```

`--self-test`는 네트워크·Chromium 실행 없이 정책/감사/우회 차단 검사를 수행합니다. `--check`는 제품 해시, 원본 4개 시나리오 파일, P1 검사 함수/관찰 코드, 가드 import와 설치된 Python 의존성을 확인합니다.

## 안전 실행 명령

다음 하나의 진입점에서 실행합니다. 출력 디렉터리는 매번 **존재하지 않는 새 디렉터리**여야 합니다.

```powershell
$Output = Join-Path $Tool 'results\my-safe-run-001'
& $Python -B (Join-Path $Tool 'run_safe.py') --repo $Repo --browsers $Browsers --output $Output --suite all
```

- `--suite all`: 안전 사전 검사 → P1 18개 → 원본 44+3+20+14 = 81개. 합계는 99개입니다.
- `--suite p1`: 안전 사전 검사 → P1 18개.
- `--suite legacy81`: 안전 사전 검사 → 원본 81개.
- `--repo`: 제품 `index.html`을 읽을 저장소 루트. 생략하면 실행기 위치에서 계산합니다. Git 디렉터리나 특정 HEAD는 필요하지 않습니다.
- `--output`: 결과를 쓸 새 디렉터리. 임의 위치를 지정할 수 있으며 생략하면 도구의 `results/portable-시각-PID`를 사용합니다. 외부 출력 위치를 지정하면 해당 위치의 버전 관리 제외도 직접 확인해야 합니다.
- `--browsers`: 기존 오프라인 캐시. `PLAYWRIGHT_BROWSERS_PATH`를 대신 명시할 수도 있습니다. 자동 다운로드는 없습니다.

다른 현재 작업 경로에서도 `$Tool`, `$Repo`, `$Browsers`, `$Output`을 명시하면 같습니다. 도구 디렉터리와 제품을 다른 체크아웃으로 옮겨도 상대 경로로 동작합니다. 사용자 이름·드라이브·이전 결과 디렉터리·고정 Git HEAD는 실행 조건이 아닙니다.

기존 진입점 `tests/run_all.py`는 같은 안전 실행기의 `legacy81`, `timer-regression/run.py`는 `p1`로 연결됩니다. 인자는 위와 같습니다. 개별 시나리오 파일이나 `cases.py` 직접 실행/import는 안전 가드가 없어 거부됩니다. `--chrome`, `--headed`, 임의 Chromium 인자, CSP/TLS 해제, 외부 프로필 옵션은 지원하지 않습니다.

## 차단 구성과 결과 확인

1. 버전 관리된 `safety/runtime.py`를 명시적으로 초기화합니다. 가드 누락·초기화 실패 시 테스트를 중단합니다. 환경 변수만으로 가드를 활성화하거나 검증을 생략할 수 없습니다.
2. 브라우저를 실행하기 **전에** upstream 소켓을 만들지 않는 로컬 deny-only 프록시를 설치합니다. Chromium 프로세스에는 강제 프록시·외부 DNS 차단·QUIC/백그라운드 통신 억제·WebRTC 비프록시 UDP 차단을 적용합니다. TLS와 브라우저 보안은 유지합니다.
3. 빈 컨텍스트·Service Worker 차단을 강제하고 정확한 HTML GET만 허용합니다. 나머지 HTTP·WebSocket과 APIRequest, persistent profile, CDP, sync 브라우저 등 우회 경로를 거부합니다.
4. 사전 검사에서 실제 제품 응답 CSP, SDK/인증 부재, 가짜 저장 격리, HTTP/쓰기/WebSocket 차단을 확인합니다. 제품 CSP를 끄지 않고 별도 `about:blank`에서 라우트 차단도 확인합니다. 프록시 단독 HTTP/HTTPS 검사에서는 사전 검사 전용 컨텍스트의 renderer 라우트만 제거하고 하위 프록시·DNS 차단은 유지합니다.
5. Chromium 종료 후 NetLog의 원격 TCP 시도·DNS wire transaction·UDP payload 및 가드 위반이 모두 0인지 확인한 뒤에만 `safety-gate.json`을 만듭니다. 이 실행/가드와 일치하는 gate 없이는 게임 테스트가 시작되지 않습니다.
6. 각 그룹 종료 후 다시 네트워크·컨텍스트 수·종료 상태와 제품/도구 무변경을 검사합니다. 실패하면 중단하며 기대값 수정·자동 재실행은 없습니다.

정상 종료는 코드 0과 `summary.json`의 `passed: true`로 확인합니다. `groups`에서 P1 18개 및 원본 81개의 통과·실패·건너뜀·미실행을 구분합니다. `preflight.json`은 차단 검사, `*-network.json`은 프로세스별 NetLog 감사, `*.log`는 원본 실행 로그입니다. 초기화 실패는 종료 코드 0이 아니며 `failure.json` 또는 터미널/해당 stage 로그를 확인합니다. 차단된 요청은 실제 시도로 기록하며, 전송되지 않았다고 해서 시도 자체가 없었다고 판정하지 않습니다.

## baseline과 버전 관리

이전 `results/safety-run/baseline.json`은 HTML·기존 도구 9개 파일의 raw SHA-256/이전 HEAD를 고정하던 무결성 자료였습니다. 경제 수치나 저장 데이터의 정답이 아닙니다. 이제 `fixtures/source-manifest.json`이 검토된 최종 HTML의 LF 정규화 해시, 원본 시나리오의 해시, 그대로 옮긴 P1 함수와 관찰 코드의 해시/사례명을 보관합니다. 현재 파일을 실행 때마다 새 정답으로 채택하지 않습니다. 제품 변경 시에는 코드 검토와 별도 승인을 거쳐 manifest의 소스 식별자를 명시적으로 갱신해야 합니다. 경제 기대값은 시나리오 소스에 그대로 남습니다.

버전 관리 대상은 실행기·호환 진입점·시나리오·`safety/`·manifest fixture·README·requirements·ignore 규칙입니다. fixture에는 실제 저장 상태·계정·토큰·인증 정보가 없습니다. `results/`, `.venv/`, 브라우저/오프라인 다운로드, 캐시, 로그, 실제 데이터는 포함하지 않습니다.

## 제한

Windows의 검토된 번들 Chromium과 로컬 가짜 저장 환경을 대상으로 합니다. 실제 iPhone/Android의 백그라운드 복귀, 터치/화면, 외부 CDN 리소스 표시 및 실제 클라우드 동기화를 입증하지 않습니다. 가드는 이 도구의 정상 진입점과 검토된 시나리오를 보호하며, 임의의 악성 Python 프로그램에 대한 OS 전체 방화벽을 제공하는 것은 아닙니다. 네트워크 차단 수준을 확인할 수 없으면 제품 테스트를 실행하지 않습니다.
