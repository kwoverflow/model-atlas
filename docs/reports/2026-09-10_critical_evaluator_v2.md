# Evidence Remediation 22: Agent 판정 계약 수정 후보

검증일: 2026-09-10. 적용 범위: 명시적으로 선택하는 per-result critical 판정기 v2.

## 결론

Agent 계획에 단일 Tool 플래그를 적용하던 충돌을 별도 버전에서 수정했다.
이전 통합 진단의 **동일한 60개 출력**을 비교한 결과, 12개 Agent 결과만 실패에서 통과로
변경됐다. 새 후보 판정은 **34개 통과, 26개 실패**다.

이는 평가 계약의 수정이지 모델 성능 향상이 아니다. 원본 출력, Tool 플래그, 모델 가중치,
공식 결과는 변경하지 않았다. 새 모델 호출이나 재학습도 없었다.
기본 Gate와 공식 화면은 기존 판정기를 사용하며 계속 BLOCKED다.

## 구현

| 파일 | 역할 |
| --- | --- |
| services/deployment_gate/critical_evaluation.py | 판정 버전 선택, Agent 증거 검증, 버전별 결정과 사유 반환 |
| services/deployment_gate/metrics.py | 내부 단일 Tool 플래그 검사 인자 추가, 기본값 true 유지 |
| reference_workload/critical_evaluator_comparison.py | 저장된 진단의 무결성 검사와 읽기 전용 버전 비교 |
| tests/test_critical_evaluation.py | 타입/누락/실패/정책/버전/무결성/기존 Agent 회귀 검사 |

`critical-output-contract-v1`은 기존 per-result 동작의 비교용 이름이다.
v2는 명시적으로 전달해야 실행되며, 알 수 없는 버전은 거절한다.
기존 `critical_case_outcomes`, `calculate_metrics`, Gate 평가, 공식 overview 호출은
변경하지 않았다. 집계 Tool 지표나 Gate 계산 버전을 이번에 승격한 것은 아니다.

새 validator는 기존 `AgentExecutionTraceRead`를 strict 모드로 재사용한다.
정상 Agent 계획일 때만 단일 Tool 플래그를 적용하지 않으며 다음 조건은 계속 차단한다.

- 누락/잘못된 타입/지원하지 않는 버전/다른 사례 ID의 trace.
- parse/plan 실패, 실제 단계 실패, 정책 위반, 승인 대기/거부, 미복구 실패.
- 선언된 계획과 실행 단계의 순서·개수·인덱스·카운터 불일치.
- 잘못된 관측, 허용되지 않은 동작, Tool 선택/인자/출력 검증 실패.
- 복구 단계 연결 오류, 메모리/승인 provenance 오류, 최종 응답 누락.
- 기존 error_type, exact_match, quality, JSON/RAG/Tool/runtime 공통 실패 조건.

`tool_call_valid=false`는 DB에 그대로 남는다. true로 덮어써서 통과시키는 방식이 아니다.
이 검사는 실행 증거의 구조적 일관성을 확인하며 의미적 답변 정확성이나 신원 인증을
대신하지 않는다. expected_steps가 없는 계약 또는 오래된 trace의 자동 호환도 보장하지 않는다.

## 같은 출력의 비교

| 항목 | 기존 v1 | 후보 v2 |
| --- | ---: | ---: |
| 전체 통과 | 22 | 34 |
| 전체 실패 | 38 | 26 |
| Agent/RAG+Tool 12개 통과 | 0 | 12 |
| 나머지 48개 결과 변경 | 해당 없음 | 0 |
| 기존 통과가 실패로 변경 | 해당 없음 | 0 |

변경된 사례는 `KO-AGENT-001`, `KO-RAG-TOOL-001/002/003`의 세 설정별 결과다.
원본과 사례의 해시, 양쪽 판정 버전, 적용 가능한 플래그, 변경 사유를 comparison.json에 기록했다.
60개 관측은 개발 과정에서 확인한 사례이며 독립 holdout이 아니다.

## 남은 실패

| 유형 | 실패 관측 | 고유 사례 |
| --- | ---: | ---: |
| 일반 단일 문서 RAG | 6 | 2 |
| 다중 문서 RAG | 9 | 3 |
| 단일 Tool | 5 | 2 |
| 과거 조건의 Tool 복구 | 6 | 2 |
| 합계 | 26 | 9 |

다음 우선순위는 일반 RAG의 검색 누락과 답변/인용 문제를 분리해서 개선하는 것이다.
기존 진단에서 다중 문서 두 사례는 필수 근거가 top-5 밖에 있었고, 나머지 세 일반 RAG
사례는 근거가 검색돼도 답변/인용 조건에 실패했다. 이 부분은 이번 변경으로 해결하지 않았다.
과거 복구 조건과 환경 소유 fault fixture의 차이도 그대로 남아 있다.

## 검증 결과

- 추가 테스트 85개 통과. 기존 canary 테스트 포함 120개 통과.
- Docker 전체 백엔드 **720개 통과**, upstream deprecation 경고 2개.
- 호스트/Docker 전체 Ruff 통과. Docker backend 빌드 및 재배포 완료.
- 기존 기본 Agent 8개와 adaptive Agent 5개 fixture를 실행해 재시도, 메모리,
  재계획 복구, 승인 checkpoint가 새 검사 때문에 잘못 차단되지 않는지 확인했다.
  이는 테스트 DB의 합성 실행이며 실사용자 승인이나 새로운 모델 평가가 아니다.
- 기존 canary 파일의 고정 SHA-256과 내부 content hash를 검증했다.
- 60개 결과 전부에서 v1 판정이 저장된 이전 판정과 동일했다.
- 공식 run/configuration/suite/result/metric/case의 집계 해시가 수정 전후 동일했다.
- 추론 어댑터, 사례 팩, 이전 진단 소스는 그대로다. 소스 snapshot 차이는 기존 metrics.py
  한 파일 수정과 새 모듈 두 파일 추가뿐이며 삭제된 app 소스는 없다.
- 공식 상태는 BLOCKED / 실패 110 / 결과 384 / 모델 출력 검토 0/30 /
  not_production_ready로 동일하다.
- workflow는 기존 automated_qa 15건, 참여자 관측 0건이다. 새 UI/API/migration은 없다.
- 실행 중인 workflow 페이지 HTTP 200을 확인했다. UI 변경이 없어 시각 회귀 검사는 재실행하지 않았다.
- 원격 CI는 실행하지 않았다. 추가 테스트는 기존 backend pytest 수집 범위에 포함된다.

## 증거 파일

`artifacts/critical-evaluator/2026-09-10/`:

| 파일 | SHA-256 |
| --- | --- |
| before.json | 2467da7cb48efca2ae2870a90536e96113762730c96c2cfc8cdd2cef29e65e61 |
| after.json | d5942f6993181d41ce5b6777f316c9e91b8b239a3a01880655e56a3e28b5d2f0 |
| comparison.json | 343208e34e5b6c83bbce6f1c068eaa9a6c55b34093f9a4779a1bd2b3cfa58449 |

입력은 `artifacts/critical-canary/2026-09-10/audit.json`이다.
입력 파일 SHA-256은 `e52a229859b9f07b9918d038b5ebdb151b86612df466f5915f362e1231c2e29e`로 유지된다.

비교 도구는 결과 파일의 덮어쓰기를 거절하고, 공식 상태가 변경되면 성공 보고서를 생성하지 않는다.
해시는 내용 검증이며 전자서명이나 검토자 신원 증명이 아니다.

## 승격 경계

현재 구현은 검증된 후보 판정기다. 기본 Gate에서 사용하려면 per-result 판정뿐 아니라
유형별 집계 지표, 계산/증거 버전, 과거 snapshot 재현, 명시적 새 평가 경로를 함께 검증해야 한다.
공식 출력 검토나 배포 승인을 이번 비교 결과로 대체하지 않는다.

[구조와 재현 명령](../critical_evaluator_versions.md)
