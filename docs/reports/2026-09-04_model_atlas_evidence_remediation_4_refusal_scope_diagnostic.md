# Model Atlas Evidence Remediation 4: Refusal and Scope Diagnostic

Date: 2026-09-04 JST  
Case-pack revision: finalized `1.0.2`  
Diagnostic scope: 7 critical cases x 3 configurations x 1 trial  
Decision: `REMEDIATION_REQUIRED`  
Production readiness: `not_production_ready`

## 결론

`1.0.2`의 단일 변경 케이스는 사람 검토와 해시 검증을 통과했고, 최종 검색 계약 감사에서
7개 케이스 모두 기대 근거를 `top_k=5` 안에서 찾았다. 따라서 이전의 검색 계약 blocker는
해소됐다.

그러나 실제 Ollama 진단 21건은 RAG 전체 성공이 `0/21`이었다. 검색 recall은 모든 구성에서
`1.0`이었고 timeout과 OOM도 없었다. 실패 지점은 검색 이후의 JSON 출력, 정확한 chunk ID
인용, 원자적 claim 작성, claim-grounding 단계다. 이 결과는 모델 또는 프롬프트 품질 문제이며
검색 파이프라인 장애가 아니다.

이 실행은 `local_actual_runtime_diagnostic`이며 Portfolio, Gate 또는 production 증거가 아니다.
기존 `1.0.0` Portfolio 384건과 세 Gate는 변경하지 않았다.

## 1.0.2 최종화

검토자 `김대건`이 `KO-RAG-SCOPE-001` 변경을 승인했다. 승인 파일은 revision report와 변경
case hash에 묶여 있으며 최종 상태는 다음과 같다.

- 승인 case: 64/64
- 승인 critical case: 20/20
- draft / rejected: 0 / 0
- `portfolio_ready=true`
- 변경 범위: `KO-RAG-SCOPE-001`의 expected evidence identity 1건
- 사용자 query 변경: 없음
- canonical case pack 또는 과거 Result 변경: 없음

## 최종 검색 계약 감사

| Case | Expected rank | Recall | Contract status |
| --- | ---: | ---: | --- |
| `KO-RAG-SCOPE-001` | 1 | 1.0 | reachable |
| `KO-RAG-SCOPE-002` | 2 | 1.0 | reachable |
| `KO-RAG-SCOPE-003` | 1 | 1.0 | reachable |
| `KO-REFUSE-001` | 2 | 1.0 | reachable |
| `KO-REFUSE-002` | 2 | 1.0 | reachable |
| `KO-REFUSE-003` | 1 | 1.0 | reachable |
| `KO-REFUSE-004` | 1 | 1.0 | reachable |

감사 결과는 reachable 7, blocked 0, critical blocked 0이다. Expected chunk ID는 평가 전용
계약이며 모델 입력에는 포함하지 않았다.

## 실제 런타임 결과

| Configuration | Model / prompt | RAG success | JSON valid | Max-token hits | Citation P/R | Grounded | Unsupported | Mean quality | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 0.5B / v1 | 0/7 | 0/7 | 2/7 | 0.000 / 0.000 | 0.000 | 1.000 | 0.250 | 42,362.161 |
| `medium-candidate` | 1.5B / v1 | 0/7 | 1/7 | 5/7 | 0.048 / 0.143 | 0.019 | 1.000 | 0.279 | 40,225.300 |
| `prompt-variant` | 1.5B / v2 | 0/7 | 2/7 | 5/7 | 0.119 / 0.286 | 0.156 | 0.929 | 0.356 | 20,255.902 |

세 실행 모두 7/7 retrieval recall `1.0`, timeout 0, OOM 0이다. Runtime reliability의 error
21건은 transport 또는 자원 실패가 아니라 최종 `rag_evaluation_failed`를 반영한다.

Run IDs:

- `small-baseline`: `8841202d-56d8-4162-886a-bb7844e5d048`
- `medium-candidate`: `2f4fb93e-0be8-44f8-a2e0-61860a64f882`
- `prompt-variant`: `311db47a-9a09-43cc-87bc-6811f3135f14`

## 실패 분석

### 1. JSON 생성과 길이 제어

0.5B v1은 malformed JSON 2건과 필수 필드가 비어 있는 JSON 5건을 만들었다. 1.5B v1은
malformed 5건, incomplete schema 1건이었고 v2는 malformed 5건이었다. 두 1.5B 구성은 각각
5/7 응답이 진단 상한 384 completion token에 닿았다. 검색된 문서 본문을 citation 객체 안에
다시 복사하면서 응답이 길어지고 JSON이 닫히지 않는 패턴이 주원인이다.

### 2. 인용 계약

평가기의 citation 계약은 정확한 `chunk_id` 목록을 요구한다. 모델은 citation 객체, 제목,
문서 본문 또는 `citation_text`를 함께 생성하는 경우가 많았다. JSON이 유효해도 관련 chunk만
정확히 인용하지 못해 precision 또는 recall이 1.0에 도달하지 못했다.

### 3. Claim grounding

유효 JSON 3건도 모두 실패했다. 가장 좋은 결과인 v2 `KO-RAG-SCOPE-001`은 citation recall
1.0과 groundedness 0.756을 기록했지만 citation precision 0.5와 unsupported claim rate 0.5로
계약을 통과하지 못했다. v1/v2 `KO-RAG-SCOPE-003`은 핵심 결론 방향은 맞았지만 claims가
인용 문장과 충분히 겹치지 않아 groundedness가 각각 0.133과 0.333에 머물렀다.

### 4. Refusal 평가 경계

네 refusal case 모두 실패했다. 일부 출력은 “확인할 수 없습니다”라는 올바른 방향을 보였지만
JSON truncation 또는 `answer=null`, 빈 citations/claims 때문에 RAG 계약을 충족하지 못했다.
또한 현재 RAG scorer는 non-empty answer/citations/claims와 retrieval/citation/grounding을
엄격히 검사하지만 `must_refuse`, `required_facts`, `forbidden_claims`를 별도 의미 규칙으로
직접 채점하지 않는다. 따라서 이번 결과는 refusal 응답의 구조와 근거 실패를 증명하지만,
refusal 정책 의미 전체를 검증한 것으로 해석하면 안 된다.

## 다음 개선 순서

1. RAG 전용 출력 템플릿을 `{"answer":"...","citations":["chunk-id"],"claims":["..."]}`
   형태로 고정하고, citation에 원문을 복사하지 못하게 제한한다.
2. `must_refuse`, `required_facts`, `forbidden_claims`를 평가 trace에 포함하는 contract-aware
   refusal scorer와 테스트를 추가한다.
3. 같은 7개 case로 bounded diagnostic을 재실행해 JSON validity, citation precision/recall,
   unsupported claim rate를 먼저 확인한다.
4. 이 cluster가 안정된 뒤 Tool argument/recovery cluster를 개선한다.
5. 여러 critical cluster가 개선되기 전에는 새 전체 Portfolio와 Gate를 생성하지 않는다.

## 증거 식별자

- review attestation file SHA-256:
  `6f7576ec944952b84b0e75422a3023a168e51e89c9ed554cd37b29ba8aa23811`
- finalization report file SHA-256:
  `952fb6ed63a4cc07c060770f671df1662624efa79639ce4b6c7e9b60a3f36834`
- finalization logical SHA-256:
  `805088e42a0c06433355d58ac401d9a1a347a8495eb399bd4b4a8046054761ce`
- finalized review manifest SHA-256:
  `408f0a8fa341806f720e3f230b29486981f33fb5e21b15be5672b2c26499ab02`
- retrieval audit file SHA-256:
  `23c93add86648e1fdd661e2814973581272af77c075af609785c5b02774e2b18`
- retrieval audit logical SHA-256:
  `9a49fb29258703323a7315144a8ee66c43d4b5f2da3da1c6e6b3e901cad71b6e`
- diagnostic result file SHA-256:
  `53ed7857453ddb82fa95bd7014dc25f92cf2947389799cdc891681262d4b4878`
- runtime matrix SHA-256:
  `cfcf986f8e3a884a385a9873e370ccbe6f544b9628b15036db067033504845aa`

## 현재 권위 상태

Live overview는 canonical workload `1.0.0`, selected Results 384, critical failures 110,
human-reviewed model outputs 0/30을 유지한다. 세 reference Gate는 모두 `BLOCKED`이며 각각
8개 blocker rule을 실패했다. Production-captured evidence와 release authorization은 없고
`production_readiness=not_production_ready`다.
