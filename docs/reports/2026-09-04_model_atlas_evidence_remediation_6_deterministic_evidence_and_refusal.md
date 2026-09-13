# Model Atlas Evidence Remediation 6: Deterministic Evidence and Refusal

Date: 2026-09-04 JST  
Case-pack revision: finalized `1.0.2`  
Diagnostic scope: 7 critical cases x 3 configurations x 1 trial  
Decision: `PARTIAL_REMEDIATION_SUCCESS`  
Production readiness: `not_production_ready`

## 결론

생성 전에 질문과 검색된 top-k 문장만으로 근거를 선택하고, 선택 문장을 claim으로 고정하는
결정론적 계층을 추가했다. 거부 케이스에는 공개 질문과 선택 근거만으로 만든 짧은 거부문을
strict JSON schema로 제한했다. 기대 chunk ID, required fact, forbidden claim은 모델 입력에
포함하지 않았다.

최종 실제 Ollama 실행은 JSON `21/21`, groundedness `21/21`에서 `1.0`, unsupported claim
`21/21`에서 `0.0`, refusal semantic `12/12`를 기록했다. 엄격한 RAG 성공은 이전 `0/21`에서
`11/21`로 증가했다. 다만 이것은 7개 critical case의 진단 결과이며 Portfolio나 Gate 증거가
아니다.

## 구현

- `lexical-sentence-selector-v1`은 query coverage, 제한된 한·영 동의어, 문장 밀도, 제목
  overlap, 순서쌍, 경계 표현, retrieval prior를 결정론적으로 결합한다.
- 표, Mermaid, 환경변수, 짧은 heading 같은 구조 조각은 claim 후보에서 제외한다.
- 선택 결과는 source rank, chunk ID, claim, score, confidence, query coverage, boundary signal,
  abstention recommendation과 함께 `rag-retrieval-trace-v2`에 저장된다.
- `rag_version_or_scope`와 `insufficient_evidence_refusal`은 선택된 chunk 하나만 생성 근거로
  사용한다. 다른 RAG 카테고리는 기존 top-k 생성 동작을 유지한다.
- `openai-compatible-v16`은 citation과 source claim을 strict enum으로 제한한다.
- refusal answer는 공개 query와 선택 claim만으로 만든 bounded enum이다. scorer-only 정답은
  참조하지 않는다.
- `rag-evaluation-trace-v3`, `rag-evaluation-summary-v3`, `rag-evaluation-scorer-v3`가 선택
  provenance와 selection recall을 보존한다.
- RAG trace UI는 선택 근거, confidence, abstention, selection recall을 표시한다.

## 흐름

```text
public query
  -> lexical top-k retrieval
  -> deterministic sentence selection
  -> selected chunk + exact source claim
  -> strict answer/citation/claim schema
  -> local runtime generation
  -> evaluator-only citation, grounding, refusal, and semantic scoring
  -> immutable Result metadata and logs
```

## 최종 결과

| Configuration | Model / prompt | JSON | RAG success | Semantic | Refusal | Citation P/R | Grounded | Unsupported | Mean quality | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 0.5B / v1 | 7/7 | 3/7 | 4/7 | 4/4 | .571 / .571 | 1.000 | .000 | .807 | 5,275.777 |
| `medium-candidate` | 1.5B / v1 | 7/7 | 4/7 | 5/7 | 4/4 | .571 / .571 | 1.000 | .000 | .836 | 9,035.953 |
| `prompt-variant` | 1.5B / v2 | 7/7 | 4/7 | 5/7 | 4/4 | .571 / .571 | 1.000 | .000 | .836 | 9,607.522 |

전체 21개 Result의 평균 quality는 `0.826190`이다. Retrieval recall은 모두 `1.0`, exact
selection recall은 각 구성 `0.571429`이다. 384-token ceiling, timeout, OOM은 모두 0이다.

이전 최종 strict-schema 진단과 비교하면:

| Metric | Remediation 5 | Remediation 6 |
| --- | ---: | ---: |
| Valid JSON | 20/21 | 21/21 |
| RAG success | 0/21 | 11/21 |
| Mean groundedness | .405 | 1.000 |
| Mean unsupported rate | .786 | .000 |
| Refusal requirement/semantic success | 3/12 | 12/12 |
| 384-token ceiling hits | 1/21 | 0/21 |

## 잔여 실패

최종 실패 10건 중 9건은 세 case의 single expected chunk ID와 선택 ID가 구성마다 동일하게
충돌한 결과다.

| Case | Finalized expected ID | Selected ID | 해석 |
| --- | --- | --- | --- |
| `KO-RAG-SCOPE-002` | `ko-247daa1b46cc86363d892938` | `ko-b70165b4b3f47cf87a34ff25` | 선택 문서가 추천 순위와 배포 승인의 분리를 직접 명시한다. |
| `KO-RAG-SCOPE-003` | `ko-5177b421f19ca0909ee719f2` | `ko-9c59bd29a1b754b80c476d62` | 선택 문장이 managed root의 development tier를 직접 명시한다. |
| `KO-REFUSE-002` | `ko-605f4586e724cc70f087851d` | `ko-8b7f33d47228772f0cbba790` | 선택 문서가 실제 조직 production 승인 비주장을 직접 명시한다. |

세 선택 ID 모두 top-k에 존재하고 질문 경계를 직접 뒷받침한다. 따라서 이를 단순 selector
오류로 자동 수정하면 안 된다. `relevant_chunk_ids`가 모두 필수인 현재 계약은 복수의 허용
근거 중 하나를 표현하지 못한다. 후속 `1.0.3` 후보는 `acceptable evidence alternatives`
의미를 별도 필드나 그룹으로 모델링하고 인간 검토를 받아야 한다.

나머지 1건은 0.5B의 `KO-RAG-SCOPE-001` answer가 금지된 proposition을 질문으로 반복해
forbidden match가 발생한 경우다. Citation, claim grounding, required fact는 통과했지만 semantic
contract 때문에 전체 실패로 유지했다.

## 중간 보정

첫 selector 실행은 claim grounding을 `1.0`, unsupported rate를 `0.0`으로 만들었지만 모델이
명시적 거부문을 생략해 refusal 성공이 `0/12`였다. 공통 refusal answer contract를 추가한
다음 실행은 `11/12`였고, 한 결과가 384 token에서 잘렸다. 거부문을 줄인 v16 최종 실행은
`12/12`, ceiling hit 0을 기록했다. 각 단계의 원시 artifact를 보존해 결과 선택 과정을
감추지 않았다.

## 검증

- full backend suite: `241 passed, 1 skipped, 2 warnings`
- final-image focused Docker suite: `27 passed, 2 warnings`
- Ruff check: passed
- frontend lint, typecheck, production build: passed
- desktop 및 390 px mobile browser QA: selection trace가 겹침 없이 표시되고 console error/warning 없음
- final artifact JSON: valid
- API health: `ok`
- Alembic: `202608040001 (head)`
- Docker backend/database/Ollama: healthy, frontend/worker: running
- container contract versions: `openai-compatible-v16`, `rag-retrieval-trace-v2`,
  `rag-evaluation-trace-v3`, `rag-evaluation-summary-v3`, `rag-evaluation-scorer-v3`,
  `lexical-sentence-selector-v1`
- locked `docs/rag_evaluation.md` SHA-256 preserved:
  `c307372fbddca3ebc3e10c03ce48d7938935dfeb1b587a885deb3e1e07f6c40d`

## 증거 식별자

- final run IDs:
  - `small-baseline`: `30b4a30c-cff4-4eda-a557-b722fc0cd9d8`
  - `medium-candidate`: `31199d00-f902-40c2-b9e5-4f9ae2cf68fe`
  - `prompt-variant`: `dbf12ff0-b12f-4a05-b48b-ba4f5981ec4f`
- final artifact:
  `artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.2-evidence-compiler-v3.json`
- final artifact SHA-256:
  `89cc23531ed4a48507434c7143e57debbb8a003673371ea08eb75f72bc179823`
- prior Remediation 5 artifact SHA-256:
  `142922e414ec3ca129cc2df00b8fd81f24663dcad83761ea9b87428e6764c6c3`

## 증거 경계

실행은 모두 `local_actual_runtime_diagnostic`이며 authoritative Portfolio 또는 Gate evidence가
아니다. Canonical workload `1.0.0`, 384 Portfolio Results, 110 critical failures, model-output
review `0/30`, 세 `BLOCKED` Gate와 각 8개 blocker rule은 변경하지 않았다. Production-captured
evidence와 release authorization은 없으며 `production_readiness=not_production_ready`다.
