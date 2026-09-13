# 핵심 실패 사례 통합 재검증

## 목적과 경계

기존 공식 실패 계획에 포함된 사례를 현재 코드와 검토된 사례 팩으로 다시 실행한다.
각 개선 실험의 결과를 합산하는 대신, 같은 실행 조건에서 현재 남은 문제를 확인한다.
이 절차는 개발용 진단이며 공식 Portfolio, Deployment Gate, 사람 검토를 대체하지 않는다.

2026-09-10 기준 대상은 고유 사례 20개, 설정 3개, 설정별 1회인 60개 관측이다.
과거 공식 실패 110건은 고유 문제 110개가 아닌 설정과 반복 실행별 실패 결과 수다.
새 진단의 분모와 사례 정답, 코드, 토큰 한도가 다르므로 과거 대비 모델 성능 향상률로
계산하지 않는다. 이 사례들은 개발 과정에서 이미 확인한 사례이며 독립 holdout이 아니다.

## 구성

- 실행: 기존 `app.reference_workload.cli run --mode diagnostic` 사용.
- 원본: `reference_workload/revisions/1.0.4/`의 manifest, cases, review manifest.
- 설정: 기존 runtime matrix의 활성 설정 사용. seed 42, 동시성 1, 한도 384 tokens.
- 실행 분리: `local_actual_runtime_diagnostic` 데이터 소스와 진단 전용 configuration.
- 감사: `app.reference_workload.critical_canary`의 `snapshot`, `audit` 명령.
- 판정 재사용: `deployment_gate.metrics.critical_case_outcomes`의 기존 판정 로직.
- 산출물: 실행 전/후 snapshot, runtime matrix 결과, 감사 보고서 JSON.

추가 감사 모듈은 추론, Tool 실행, DB 변경을 하지 않는다. PostgreSQL에서는
`REPEATABLE READ, READ ONLY` 트랜잭션을 사용한다. 실행 명령 자체는 새로운 진단 run과
결과를 저장한다. 감사 결과가 실패해도 생성된 진단 기록을 삭제하거나 정답을 수정하지 않는다.

## 확인하는 항목

1. 실행 전후 공식 비교 해시, Gate, 검토 현황, 공식 run 식별자가 같은지 확인한다.
2. 공식 run/configuration/suite/result/metric/case 컬럼값 전체의 집계 해시를 비교한다.
3. 백엔드 app 소스와 지정된 원본/개정 사례 파일의 SHA-256을 비교한다.
4. 진단 범위와 matrix 해시, 각 설정의 완료 여부와 1회 반복 조건을 확인한다.
5. DB의 run/configuration/suite와 보고서 식별자를 대조한다.
6. 모든 결과와 metric이 진단 데이터 소스인지, sample이 일대일 대응하는지 확인한다.
7. 모든 사례가 해당 suite의 critical 사례인지, 설정 x 사례가 누락/중복 없이 존재하는지 확인한다.
8. 기존 판정기로 유형별/설정별 결과와 잔여 사례 목록을 만든다.

JSON에는 원본 출력, 정규화 출력, 실행 trace, 사례 조건, metric이 포함된다.
`content_sha256`은 이 필드를 제외한 내용의 canonical JSON 해시다. 파일 바이트 해시와는 다르다.
해시는 내용 일관성 검사이며 전자서명이나 검토자 신원 인증이 아니다.

## 재실행

저장 경로는 실행마다 새 디렉터리를 사용한다. 감사 명령은 기존 파일 덮어쓰기를 거절한다.
기존 runtime CLI는 별도의 덮어쓰기 방지 기능이 없으므로 실행 전에 출력 경로를 확인한다.
다음 명령은 프로젝트 루트의 PowerShell에서 실행한다. Docker 서비스가 실행 중이어야 한다.

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$hostDir = "artifacts/critical-canary/$stamp"
$containerDir = "/artifacts/critical-canary/$stamp"
docker compose exec -T backend python -m app.reference_workload.critical_canary snapshot --repository-root /workspace --output "$containerDir/before.json"
if ($LASTEXITCODE -ne 0) { throw 'Snapshot failed' }

$state = Get-Content "$hostDir/before.json" -Raw | ConvertFrom-Json
if (Test-Path -LiteralPath "$hostDir/runtime-matrix.json") { throw 'Output exists' }
$runArgs = @(
  'compose', 'exec', '-T', 'backend', 'python', '-m', 'app.reference_workload.cli',
  '--repository-root', '/workspace',
  '--manifest', '/workspace/reference_workload/revisions/1.0.4/manifest.json',
  '--cases', '/workspace/reference_workload/revisions/1.0.4/cases.jsonl',
  '--reviews', '/workspace/reference_workload/revisions/1.0.4/review_manifest.jsonl',
  'run', '--mode', 'diagnostic',
  '--matrix', '/workspace/reference_workload/runtime_matrix.json',
  '--base-url', 'http://ollama:11434',
  '--small-model', 'qwen2.5:0.5b', '--medium-model', 'qwen2.5:1.5b',
  '--output', "$containerDir/runtime-matrix.json"
)
foreach ($id in $state.expected_case_ids) { $runArgs += @('--case-id', $id) }
& docker @runArgs
if ($LASTEXITCODE -ne 0) { throw 'Runtime diagnostic failed; preserve its records' }

docker compose exec -T backend python -m app.reference_workload.critical_canary snapshot --repository-root /workspace --output "$containerDir/after.json"
if ($LASTEXITCODE -ne 0) { throw 'After snapshot failed' }
docker compose exec -T backend python -m app.reference_workload.critical_canary audit --repository-root /workspace --before "$containerDir/before.json" --after "$containerDir/after.json" --matrix-result "$containerDir/runtime-matrix.json" --output "$containerDir/audit.json"
if ($LASTEXITCODE -ne 0) { throw 'Coverage or provenance audit failed' }
```

감사 성공은 **실행 범위와 증거 일관성 확인**이다. `summary.failure_count`가 0이라는 뜻이
아니며, 공식 Gate를 통과시켰다는 뜻도 아니다. 실제 실패는 JSON에 그대로 보존한다.
감사 중 소스가 바뀌거나 공식 판정이 변경되면 중단하고 원인을 확인한다.

## 해석상의 제한

- RAG의 bounded answer compiler와 Agent plan compiler의 동작은 시스템 성과이지 원시 LLM 능력 자체가 아니다.
- 현재 복구 사례의 과거 정답과 비활성화된 오류 주입은 공정한 복구 능력 비교 조건이 아니다.
  환경 소유 fault fixture 기반 실험을 별도로 사용해야 한다.
- 감사 도구는 판정 로직을 다시 구현하거나 expected answer를 추론에 주입하지 않는다.
  기존 추론 경로 전체의 정답 유출 부재를 이 감사만으로 보증하지는 않는다.
- 소스 해시는 모델 아티팩트나 Python 의존성 lock을 대신하지 않는다.
  모델 digest는 matrix 결과에 기록되며, 완전한 재현을 위해 실행 환경도 보존해야 한다.
- 공식 모델 출력 검토와 참여자 workflow 관측은 각각 별도 절차다.

관련 문서: [프로젝트 상태](project_status.md), [사용자 workflow 검증](request_workflow_validation.md),
[환경 소유 Tool 오류 시나리오](tool_fault_scenarios.md).
