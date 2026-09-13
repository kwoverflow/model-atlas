# Evidence Remediation 21: 핵심 사례 통합 진단

검증일: 2026-09-10. 범위: 현재 기본 실행 경로, 승인된 사례 팩 1.0.4, 로컬 Ollama.

## 결론

핵심 사례 20개를 3개 설정에서 각각 한 번씩 실행했다. **현재 공통 critical 판정은
60건 중 22건 통과, 38건 실패**다. 실패한 고유 사례는 13개다.
실행/reliability 요약은 34건 성공으로 나타나며, 이 차이 12건은 Agent 실행 결과와
단일 Tool 호출 플래그를 함께 적용하는 판정 조건의 충돌로 확인했다.

지금 필요한 것은 기능 확대나 공식 승인 전환보다 **평가 유형별 판정 조건 정리**다.
그 다음에 일반 RAG의 검색 누락, 답변 사실 충족, 인용 정확성을 개선해야 한다.
진단 결과는 공식 Gate에 반영하지 않았고 과거 결과를 다시 쓰지 않았다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 범위 | 기존 공식 실패 계획의 고유 사례 20개, 8개 유형 |
| 사례 팩 | 검토 완료 1.0.4; 전체 64개 중 핵심 20개 |
| 설정 | small-baseline, medium-candidate, prompt-variant |
| 모델 | qwen2.5:0.5b, qwen2.5:1.5b |
| 런타임 | Ollama 0.31.1, openai-compatible-v21 기본 어댑터 |
| 생성 | temperature 0, seed 42, max_tokens 384, 동시성 1 |
| 반복 | 설정 x 사례당 1회, 총 60개 결과와 60개 metric |
| 저장 구분 | local_actual_runtime_diagnostic |
| 실행 시간 | 2026-09-10 11:34:15 ~ 11:40:46, +09:00 |
| 토큰 | 저장된 prompt + completion 합계 117,316 |
| timeout / OOM | 0 / 0 |

설정상의 context_length는 런타임이 실제 사용하는 context 용량의 별도 검증을 뜻하지 않는다.
토큰 수는 저장된 계측값이며 이 작업 전체의 API 사용량이나 청구 비용이 아니다.
모델 다운로드, 가중치 학습, 기본 어댑터 변경, 외부 Tool 실행은 하지 않았다.

## 유형별 결과

아래 표는 Agent trace의 성공률이 아니라 **현재 공통 critical 판정기**의 결과다.

| 유형 | 관측 수 | 통과 | 실패 |
| --- | ---: | ---: | ---: |
| 근거 부족 거절 | 12 | 12 | 0 |
| 문서 버전·범위 | 9 | 9 | 0 |
| 일반 단일 문서 RAG | 6 | 0 | 6 |
| 다중 문서 RAG | 9 | 0 | 9 |
| 단일 Tool | 6 | 1 | 5 |
| Tool 실패 복구 | 6 | 0 | 6 |
| RAG + Tool Agent | 9 | 0 | 9 |
| 다단계 Agent | 3 | 0 | 3 |
| 합계 | 60 | 22 | 38 |

설정별 critical 통과는 small 8/20, medium 7/20, prompt variant 7/20이다.
이 작은 개발 사례 집합으로 모델 순위를 정하거나 일반화된 모델 성능을 주장하지 않는다.

## 발견 사항

### 1. Agent 판정 조건 충돌: 12건

`KO-AGENT-001`, `KO-RAG-TOOL-001/002/003`이 세 설정 모두에서 같은 현상을 보였다.

- Agent trace: successful=true, plan_valid=true, policy violation 0.
- 결과: quality_score=1, exact_match=true, json_valid=true, error_type=null.
- 실행/reliability trace: success.
- 단일 Tool 결과 필드: tool_call_valid=false.
- 공통 critical 결과: fail.

`services/deployment_gate/metrics.py`의 `_is_tool_case`는 category의 `tool` 문자열 또는
expected Tool schema의 존재로 유형을 판별한다. `_is_critical_failure`는 이에 해당하면
Agent trace를 확인하기 전에 `tool_call_valid=false`를 실패 조건으로 사용한다.
`services/agent_execution/evidence.py`의 `attach_agent_execution`은 계획 결과의
exact_match/json_valid 등을 갱신하지만 단일 Tool 플래그를 Agent 결과로 바꾸지 않는다.

원본을 바꾸지 않은 메모리 복사본에서 단일 플래그만 true로 가정하면 12건 모두 이 실패가
사라지는 것을 확인했다. 이는 **원인 분리용 가정 검사**이며 점수 수정이나 승인 근거가 아니다.
모든 원본 플래그와 critical 실패는 audit.json에 그대로 남아 있다.

다음 변경은 플래그를 일괄 true로 만드는 방식이 아니라, 단일 Tool과 Agent 계획의
서로 다른 출력 계약을 구분해야 한다. 누락되거나 잘못된 Agent trace, 실제 실패,
정책 위반은 계속 차단해야 한다. 또한 판정 버전과 적용 범위를 분리해 과거 Gate가
새 판정기 때문에 조용히 달라지지 않도록 먼저 회귀 테스트를 준비해야 한다.

### 2. 일반 RAG: 15건

일반 단일/다중 문서 RAG는 세 설정에서 모두 실패했다. 15건 중 required fact 조건
미충족은 14건, citation precision 1 미만은 13건이다. 이 항목들은 서로 겹친다.

별도의 기존 retrieval contract audit를 실행한 결과, 다섯 사례 중 세 사례는 필수 근거가
top-5에 포함되고 두 사례는 그렇지 않았다.

| 사례 | 필수 근거 검색 순위 | 현재 top-5 recall |
| --- | --- | ---: |
| KO-RAG-MULTI-001 | 1, 19 | 0.5 |
| KO-RAG-MULTI-002 | 9, 7 | 0.0 |

이 검사는 예상 근거 식별자의 검색 도달 가능성만 측정한다. 예상 근거 자체가 질문과
의미적으로 맞는지, 답변의 모든 주장을 실제로 뒷받침하는지는 별도 검토가 필요하다.
`KO-RAG-001/002`, `KO-RAG-MULTI-003`은 근거가 top-5에 있어도 답변/인용 조건에 실패했다.
따라서 단순히 top-k를 늘리는 것만으로 모든 실패를 해결할 수 있다고 보지 않는다.

### 3. Tool 및 복구: 11건

일반 Tool은 6건 중 1건만 통과했다. 복구 사례 6건은 모두 실패했다.
이번 통합 진단은 현재 기본 어댑터를 실행했으며, v3 optional-presence 후보나
사용자 확인 계약 Lab을 기본 경로에 자동 적용하지 않았다.

복구 사례는 과거 정답 조건과 현재 비활성화된 오류 주입의 불일치가 남아 있다.
이는 환경 소유 fault scenario 실험과 같은 조건이 아니므로 모델의 복구 능력 0%로
일반화하지 않는다. 단일 Tool의 인자 실패와 fixture 조건 문제를 분리해서 다뤄야 한다.

## 무결성과 검증

- 새 감사 모듈 테스트 35개 통과. Docker 전체 백엔드 635개 통과, upstream 경고 2개.
- 호스트의 추가 코드 검사와 Docker 전체 Ruff 통과.
- Docker backend 빌드 및 재배포 완료. 새 API, UI, DB migration은 없음.
- 공식 run/configuration/suite/result/metric/case 컬럼값 집계 해시가 실행 전후 동일.
- 백엔드 소스 및 지정한 사례 파일 총 254개 해시가 실행 전후 동일.
- 3개 새 run의 시작/종료 시각이 전후 snapshot 구간 안에 있음을 별도 확인.
- audit.json을 다시 읽어 canonical content hash 검증 성공.
- 공식 상태: BLOCKED, critical 실패 110, 결과 384, 모델 출력 검토 0/30,
  not_production_ready로 동일.
- workflow 관측: automated_qa 15건, 참여자 관측 0건으로 동일.
- 검색 contract audit의 종료 코드 1은 두 도달 불가 사례를 보고한 정상적인 차단 결과이며,
  도구 실행 장애가 아니다. 결과 파일은 보존했다.

감사 CLI는 PostgreSQL 읽기 전용 트랜잭션을 사용하고, 다른 판정기를 만들지 않고 기존
`critical_case_outcomes`를 재사용한다. 실제 실패를 숨기지 않고 누락/중복/범위 혼입을 거절한다.
실행 전후 해시는 파일과 레코드의 동일성을 확인하지만 신원, 서명, 전체 시스템 보안을 인증하지 않는다.

## 보존한 증거

디렉터리: `artifacts/critical-canary/2026-09-10/`

| 파일 | SHA-256 |
| --- | --- |
| before.json | 726b12c0b43de7626895810d22f8526af3d8ce352fe5a0d0c1cac145bb05b53b |
| after.json | f32b109a4cc0f6cdcef1d217a3d8ba75394db3a02dbae2f114cd10afbc1f16e7 |
| runtime-matrix.json | 29b1cefb5c535100a1db8bf389109b368b91944856876a168292c04431464d79 |
| audit.json | e52a229859b9f07b9918d038b5ebdb151b86612df466f5915f362e1231c2e29e |
| retrieval-contract-audit.json | b3fcedd187c6883a9951c824c0fd94a7a271febc40a17cb4bb69d64e454f75d7 |

audit.json의 내부 content hash:
`51dece45f53cfda85571d9c8d75300523a3d0d132429565f3a79d5a2386d6320`.
이는 파일 바이트 해시와 다른 값이다.

## 다음 순서

1. 판정기 버전 분리를 전제로 Agent/단일 Tool 계약 충돌을 재현하고 수정 후보를 검증한다.
2. RAG 검색 도달 가능성과 답변/인용 품질을 분리해서 개선 후보를 비교한다.
3. Tool 인자 문제와 환경 소유 복구 fixture를 별도 검증한다.
4. 별도 참여자 workflow 관측과 실제 모델 출력 검토를 수집한다.
5. 조건이 충족되면 새 버전의 정식 평가를 실행하고 명시적 검토 후 승격 여부를 결정한다.

기존 110건과 새 38건은 조건과 분모가 달라 감소율로 비교할 수 없다.
이번 통과 22건도 bounded compiler가 포함된 시스템 결과이며 새로운 모델 학습 성과가 아니다.

[사용 및 재현 명령](../critical_canary.md)
