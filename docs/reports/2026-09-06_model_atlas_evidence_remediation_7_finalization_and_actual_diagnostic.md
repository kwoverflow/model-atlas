# Model Atlas Evidence Remediation 7: Finalization And Actual Diagnostic

Date: 2026-09-06 JST  
Source case pack: finalized `1.0.2`  
Finalized case pack: `1.0.3`  
Decision: `DIAGNOSTIC_CONFIRMED`  
Production readiness: `not_production_ready`

## 결론

사람이 검토한 세 개의 동등 근거 대안을 hash-bound attestation으로 승인하고 `1.0.3`을
최종화했다. 새 팩은 64/64 사례와 20/20 critical 사례가 승인됐으며
`portfolio_ready=true`이다. 이는 평가 팩이 완전하다는 의미이며 실제 production 배포 승인을
뜻하지 않는다.

동일한 3개 구성과 7개 진단 사례를 Ollama에서 재실행한 결과, 예상했던 strict RAG 성공
`14/21`이 실제로 재현됐다. deterministic evidence selection과 citation 계약은 모두
`21/21`을 충족했고, 승인된 alternative group은 총 9회 사용됐다.

## 최종화 증거

- Reviewer: `김대건`;
- reviewed at: `2026-09-06T11:22:05.570Z`;
- approved changes: `KO-RAG-SCOPE-002`, `KO-RAG-SCOPE-003`, `KO-REFUSE-002`;
- rejected changes: none;
- revision report identity: `d2b570fe347967de9b44f90c53276630292f11d814805aaf0ecba778a4e90401`;
- finalization identity: `04308fb5d6e328fc7a6e31caa7b916f782c69390fa236f2f7ba1efa0f1614169`;
- attestation SHA-256: `4c0bfca62d66d44846a435e971f56f5a532d49d92597e7836f8635d526995183`;
- finalized review manifest SHA-256:
  `af0f54b51eb3c893cb0434963cb85fd25d22e083f32d9360836799dd6e36579a`;
- finalization report file SHA-256:
  `e676a821be2e67fa3930e01d19abe219d519cdfbbd9d1b8bfbe6494b7e21e328`.

## 실제 결과

| Configuration | Model / prompt | Before | After | Selection | Citation | Alternative |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 0.5B / v1 | 3/7 | 4/7 | 7/7 | 7/7 | 3 |
| `medium-candidate` | 1.5B / v1 | 4/7 | 5/7 | 7/7 | 7/7 | 3 |
| `prompt-variant` | 1.5B / v2 | 4/7 | 5/7 | 7/7 | 7/7 | 3 |

Aggregate outcomes:

- actual results: `21`;
- strict RAG success: `14/21`;
- retrieval contract: `21/21`;
- deterministic evidence-selection contract: `21/21`;
- citation contract: `21/21`;
- refusal contract: `12/12`;
- alternative-group matches: `9`;
- groundedness: `1.0` for all 21 results;
- unsupported-claim rate: `0.0` for all 21 results;
- timeout/OOM: `0/0`.

## 남은 실패

| Case | Configurations | Cause |
| --- | ---: | --- |
| `KO-RAG-SCOPE-002` | 3 | Alternative evidence and citation pass, required-fact coverage is `0.0`. |
| `KO-RAG-SCOPE-003` | 3 | Alternative evidence and citation pass, required-fact coverage is `0.0`. |
| `KO-RAG-SCOPE-001` | 1 | 0.5B output covers the fact but repeats one forbidden proposition. |

`KO-REFUSE-002` now passes in all three configurations with required-fact coverage `1.0` and
alternative selection/citation group index 1. Therefore the prior single-ID evidence limitation is
resolved. The six scope failures are a separate source-expression versus required-fact-label
alignment problem; weakening citation rules would not solve them.

## 실행 식별자

- small run: `c8d49bfe-e718-4e3d-98c8-591901ea5c4c`;
- medium run: `f9ef7a50-0edb-4f86-8b9c-0d5ada67f6f2`;
- prompt-variant run: `14480877-f617-4f9e-859f-89b398be4871`;
- artifact:
  `artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.3-any-of-v2.json`;
- artifact SHA-256: `4ef70ace00c2c494e995d07fcc7a404a0f000229af1c7507c79da5eac94f1240`;
- runtime: Ollama `0.31.1`, `qwen2.5:0.5b`, `qwen2.5:1.5b`;
- trace contracts: retrieval v3, evaluation v4, summary v4, scorer v4.

## 증거 경계와 다음 작업

이 실행은 `diagnostic`이며 `authoritative_portfolio_evidence=false`와 `gate_evidence=false`를
유지한다. canonical case pack, 과거 Results, Portfolio evidence, Gate는 수정하지 않았다.

다음 작업은 Evidence Remediation 8로 분리한다. `KO-RAG-SCOPE-002/003`의 source 문구와
required-fact 표현을 의미 단위로 대조하고, 사람 검토 가능한 semantic contract revision을
새 버전 후보로 만든다. 0.5B 금지 문구 반복은 prompt/scorer를 변경하기 전에 원문 응답과
원자 claim 분해를 먼저 감사한다.
