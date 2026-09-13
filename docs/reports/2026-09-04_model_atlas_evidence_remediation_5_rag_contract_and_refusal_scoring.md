# Model Atlas Evidence Remediation 5: RAG Contract and Refusal Scoring

Date: 2026-09-04 JST  
Case-pack revision: finalized `1.0.2`  
Diagnostic scope: 7 critical cases x 3 configurations x 1 trial  
Decision: `REMEDIATION_REQUIRED`  
Production readiness: `not_production_ready`

## 결론

고정 RAG JSON 계약과 refusal-aware scorer를 구현하고 동일한 7개 critical case를 세 구성에서
재실행했다. 최종 실행의 JSON validity는 기존 `3/21`에서 `20/21`로 상승했고 384 completion
token 상한 도달은 `12/21`에서 `1/21`로 감소했다. 검색 recall은 계속 전 결과 `1.0`이었다.

하지만 RAG 전체 성공은 세 구성 모두 `0/7`이다. 구조화 출력 문제는 대부분 해소됐지만,
정확한 근거 하나를 고르는 능력, 인용 본문에 직접 지지되는 원자적 claim 작성, 일관된 거절
표현이 아직 Gate 기준을 충족하지 못한다. 따라서 이 결과는 개선된 진단 가능성을 증명할 뿐
릴리스 후보나 production-ready 상태를 뜻하지 않는다.

## 구현 범위

- `openai-compatible-v13`: RAG 출력에 `answer`, `citations`, `claims`만 허용하는 strict
  `json_schema`를 적용했다.
- citation 값은 모델에 제공된 retrieved chunk ID enum으로 제한했다.
- version/scope 및 refusal cluster는 direct evidence 하나를 선택하도록 citation 수를 제한했다.
- expected relevant ID, required facts, forbidden claims는 모델 입력에서 제외하고 생성 후
  평가기에만 전달했다.
- `rag-evaluation-trace-v2`: `must_refuse`, refusal detection, required-fact coverage,
  forbidden-claim violations, semantic-contract status를 저장한다.
- `rag-evaluation-scorer-v2`: retrieval, citation, grounding, faithfulness와 semantic contract를
  함께 점수화한다.
- UI의 RAG trace panel에 refusal 및 semantic failure details를 노출했다.

## 진단 단계

| Stage | Scope | 핵심 결과 |
| --- | ---: | --- |
| Original baseline | 21 Results | JSON valid `3/21`, max-token `12/21`, RAG success `0/21` |
| Compact prompt only | 21 Results | JSON valid `1/21`, citation P/R `0/0`, RAG success `0/21` |
| Strict-schema probe | 3 Results | JSON valid `3/3`; schema 지원과 citation enum 동작 확인 |
| Final strict schema | 21 Results | JSON valid `20/21`, max-token `1/21`, RAG success `0/21` |

Prompt만으로 출력 형식을 유도하는 방식은 실패했다. Ollama의 OpenAI-compatible endpoint가
strict JSON schema를 처리하는 것을 한 케이스 probe로 확인한 뒤 전체 실행으로 확장했다.

## 최종 실제 런타임 결과

| Configuration | Model / prompt | JSON | Citation P/R | Grounded | Unsupported | Semantic | Refusal | Mean quality | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 0.5B / v1 | 7/7 | .571 / .571 | .239 | 1.000 | 0/7 | 0/4 | .391 | 6,194.049 |
| `medium-candidate` | 1.5B / v1 | 7/7 | .571 / .571 | .587 | .571 | 3/7 | 2/4 | .610 | 11,229.731 |
| `prompt-variant` | 1.5B / v2 | 6/7 | .286 / .286 | .389 | .786 | 1/7 | 1/4 | .410 | 16,058.030 |

세 실행 모두 retrieval recall `1.0`, timeout 0, OOM 0이다. `prompt-variant`의
`KO-REFUSE-004` 한 건만 384-token 상한에서 JSON이 닫히지 않았다. Runtime reliability의
error는 transport 장애가 아니라 최종 RAG evaluation failure를 나타낸다.

Run IDs:

- `small-baseline`: `8d73c7e5-3cd0-4093-81ec-ad379fba7093`
- `medium-candidate`: `4c8a7cd4-ea91-405e-8ec7-4b4005f9a712`
- `prompt-variant`: `a3c38205-5c6a-491b-8dce-224102a2b3c1`

## 실패 해석

### 구조화 출력

Strict schema는 가장 큰 병목을 제거했다. 세 구성 중 두 구성은 `7/7` valid JSON이며,
전체 길이 초과도 한 건만 남았다. Prompt-only 결과와 비교하면 출력 구조는 런타임 제약으로
강제하는 편이 훨씬 안정적이다.

### 근거 선택과 claim grounding

중간 v1은 7건 중 4건에서 기대 single citation을 골랐지만 나머지 3건은 top-k 안의 다른
chunk를 선택했다. 정확한 citation을 고른 경우에도 모델이 본문을 길게 복사하거나 근거와
다른 결론을 붙이면 groundedness 또는 unsupported-claim rule에서 실패했다. 다음 병목은
생성 전 evidence selection과 생성 후 claim normalization이다.

### Refusal semantics

네 refusal case 중 중간 v1은 2건, prompt v2는 1건에서 refusal requirement를 충족했다.
작은 모델은 질문을 답변으로 반복하거나 금지된 단정을 수행했다. 중간 모델도 거절 자체는
맞지만 required-fact label과 다른 표현을 사용해 semantic coverage가 낮아지는 사례가 있었다.

현재 semantic scorer는 bilingual token normalization과 명시적 negation pattern을 쓰는
설명 가능한 휴리스틱이다. 동의어, 추상적인 review label, `NOT_PRODUCTION_READY` 같은 compound
token에는 오탐 또는 미탐 가능성이 있으므로 semantic pass count를 인간 또는 judge-model
정답과 동일하게 해석해서는 안 된다. 이 제한은 trace의 per-fact score와 matched text로
감사할 수 있다.

## 다음 개선 순서

1. top-k 결과에서 질문과 직접 답변 문장을 함께 반환하는 deterministic evidence selector
   또는 reranker를 추가한다.
2. 선택한 근거 문장을 바탕으로 claims를 추출하고 짧게 정규화하는 단계를 생성과 분리한다.
3. refusal phrase와 required-fact synonym set을 별도 calibration set으로 검증한다.
4. 동일 7개 케이스를 다시 실행해 citation P/R과 unsupported rate 개선을 확인한다.
5. 이 cluster가 안정된 뒤 Tool argument/recovery cluster로 이동한다.

## 검증

- backend full suite: `236 passed, 1 skipped, 2 warnings`
- Docker focused RAG tests: `22 passed, 2 warnings`
- backend/Docker Ruff: passed
- frontend ESLint and production build: passed
- API health: `ok`
- Alembic: `202608040001 (head)`
- running container contracts: `openai-compatible-v13`, `rag-evaluation-trace-v2`,
  `rag-evaluation-summary-v2`, `rag-evaluation-scorer-v2`
- locked `docs/rag_evaluation.md` SHA-256 preserved:
  `c307372fbddca3ebc3e10c03ce48d7938935dfeb1b587a885deb3e1e07f6c40d`

## 증거 식별자

- prompt-only artifact SHA-256:
  `04d910978b16fcb30e6cac7e8840d5f723a3f3ebad5ff849cb52b87f2c08530b`
- strict-schema probe artifact SHA-256:
  `dcc103fadcc2e298216c75f00c1e0460d4691440f5f3f4ee7832d88afd84e31`
- final strict-schema artifact SHA-256:
  `142922e414ec3ca129cc2df00b8fd81f24663dcad83761ea9b87428e6764c6c3`

## 증거 경계

모든 실행은 `local_actual_runtime_diagnostic`이며 authoritative Portfolio 또는 Gate evidence가
아니다. Canonical workload `1.0.0`, 384 Results, 110 critical failures, model-output review
`0/30`은 변경하지 않았다. 세 reference Gate는 모두 `BLOCKED`이고 각각 blocker rule 8개를
실패한다. Production-captured evidence와 release authorization은 없으며
`production_readiness=not_production_ready`다.
