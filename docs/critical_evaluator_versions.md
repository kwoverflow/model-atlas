# Critical 판정기 버전 분리

## 현재 적용 범위

`critical-output-contract-v2`는 Agent 계획과 단일 Tool 출력을 구분하는 **명시적 선택형
비교 판정기**다. 기본 Gate, 공식 overview, 공통 metric 집계는 기존 로직을 유지한다.
따라서 화면의 공식 실패 수가 자동으로 줄어들지 않는 것이 의도된 동작이다.

`critical-output-contract-v1`은 기존 per-result 판정 동작에 부여한 비교용 이름이다.
과거 DB에 이 문자열을 추가하지 않았고, 기존 Gate의 계산 버전이나 해시를 바꾸지 않았다.
새 판정 결과를 운영에 반영하려면 새 Gate 계산/증거 버전과 명시적 재평가 경로가 필요하다.

## 해결한 문제

Agent 실행 결과는 계획, 각 단계, 관측, 정책 위반 여부로 판단해야 한다. 단일 Tool 호출의
`tool_call_valid`는 Agent 전체 계획의 유효성을 나타내는 필드가 아니다.
기존 공통 판정기는 Tool schema가 있는 Agent 사례에도 이 플래그를 적용해 정상 계획을
실패로 분류할 수 있었다.

v2는 사례 계약으로 출력 유형을 결정하고, 유효한 Agent 증거가 있는 경우 단일 Tool
플래그를 적용 대상에서 제외한다. 원본 플래그를 true로 바꾸거나 결과를 보정하지 않는다.
Agent trace가 출력 metadata에 있다는 이유만으로 일반 Tool 사례를 Agent로 바꾸지 않는다.

## 검사 항목

- 기존 `AgentExecutionTraceRead`를 strict 모드로 파싱한다. 문자열 true, 숫자형 문자열,
  bool 형태의 카운터를 정상 타입으로 자동 변환하지 않는다.
- Agent trace v2, runtime v2, context v2와 사례 ID를 확인한다.
- 주요 필드 누락, parse/plan 실패, 정책 위반, 미복구 실패, 승인 대기/거부, 중단 상태를 차단한다.
- 선언된 expected_steps, 실제 계획의 순서, 단계 인덱스/개수, 실행 한도, 집계 카운터를 대조한다.
- 단계별 허용 동작, 상태, 관측, Tool 선택/인자/출력 검증 결과와 입력의 일관성을 확인한다.
- 재계획 복구 단계의 연결과 성공 여부, 메모리 provenance, 승인 단계의 provenance를 확인한다.
- error_type, exact_match, quality, JSON/RAG/Tool trace, runtime 실패 등 기존 공통 조건을 유지한다.
- 알 수 없는 판정 버전은 예외로 거절한다. non-critical 사례는 not_applicable로 반환한다.

이 검사는 저장된 실행 증거의 구조와 일관성을 확인한다. 모든 답변의 의미적 정확성,
검토자의 신원, 외부 승인 권한, 증거의 암호학적 진위를 인증하는 절차는 아니다.
유효한 trace가 없는 오래된 Agent 결과는 v2에서 자동 통과하지 않는다.

## 코드 사용

```python
from app.services.deployment_gate.critical_evaluation import (
    AGENT_AWARE_VERSION,
    evaluate_critical_result,
)

# Explicit candidate comparison only. No DB write or Tool execution occurs.
candidate = evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION)
print(candidate.to_dict())

# Omitted version keeps the legacy per-result behavior.
legacy = evaluate_critical_result(result, case)
```

공통 `_is_critical_failure`에는 내부용 `check_single_tool_flag` 인자를 추가했으며 기본값은
true다. 이를 일반 호출자가 false로 사용해서는 안 된다. v2의 Agent 검증과 함께 사용한다.
기존 `critical_case_outcomes`, `calculate_metrics`, Gate 평가 호출은 수정하지 않았다.

## 저장된 Canary 비교

프로젝트 루트의 PowerShell에서 실행한다. 출력 경로는 항상 새 파일을 사용한다.
before/after는 이번 수정 전후 `critical_canary snapshot`으로 수집한 실제 파일이다.

```powershell
docker compose exec -T backend python -m app.reference_workload.critical_evaluator_comparison --input /artifacts/critical-canary/2026-09-10/audit.json --expected-sha256 e52a229859b9f07b9918d038b5ebdb151b86612df466f5915f362e1231c2e29e --before /artifacts/critical-evaluator/2026-09-10/before.json --after /artifacts/critical-evaluator/2026-09-10/after.json --output /artifacts/critical-evaluator/2026-09-10/comparison-rerun.json
```

비교 CLI는 입력 파일의 고정 SHA-256, 내부 content hash, 진단 출처, 사례/결과/run 연결,
누락/중복, 원래 판정과 v1의 일치, 공식 기록의 전후 동일성을 확인한다.
별도의 JSON에 두 버전의 결과, 변경 이유, 원본 결과/사례 해시, 구현 해시를 기록한다.
모델 호출, DB 쓰기, Tool 실행은 없다. 검사 실패나 파일 충돌 시 기존 파일은 보존한다.

이 CLI는 과거 보고서의 내용을 새 판정으로 덮어쓰지 않는다. **같은 출력에서 판정이 달라진
것은 모델 성능 향상이 아니다.** v2의 per-result 개선을 전체 Gate나 집계 지표의 변경으로
확대 해석해서도 안 된다.

## 검증 후 순서

일반 RAG의 검색 누락과 답변/인용 문제를 다음 후보 개선으로 진행한다. 공식 승격은 별도로
판정/증거 버전 고정, 집계 지표의 유형별 적용 범위, 최신 정식 실행과 사람 검토를 확인한 뒤
진행한다. 기존 `BLOCKED` 기록과 미검토 출력은 그대로 남는다.

[이전 통합 진단](reports/2026-09-10_critical_canary.md)
