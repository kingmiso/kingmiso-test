# P1 타이머 회귀 18개

환경 준비·안전 가드·경로/출력 설정·이전 18/18 및 최종 81/81 기록의 구분은 상위 `README.md`를 따릅니다.

`cases.py`에는 기존 18개 검사의 함수와 assert를 기대값 변경 없이 옮겼습니다. 10초/65초 지연, 완료 콜백 순서, 완료 시각 ±1ms, 동시/순차 완료, 중복 콜백, 저장 전후 새로고침/재접속, 오프라인 생산, 가속 소급 방지, 12시간 상한, 구버전 가짜 저장, 이전 전투 실패 사례를 포함합니다.

```powershell
& $Python -B (Join-Path $Tool 'timer-regression\run.py') --repo $Repo --browsers $Browsers --output $Output
```

이 진입점도 상위 `run_safe.py --suite p1`과 같은 안전 사전 검사 및 NetLog gate를 반드시 거칩니다. 직접 `cases.py`를 실행하는 방법은 지원하지 않습니다. 과거의 위치 인자 `regression OUTPUT`, `--child`, `legacyremaining`은 제거했습니다. `results/safety-run/sitecustomize.py`, 과거 baseline, 절대 경로 및 고정 HEAD는 더 이상 필요하지 않습니다.
