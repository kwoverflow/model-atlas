# Model Atlas Evidence Remediation 7: Any-of Evidence Candidate

Date: 2026-09-04 JST  
Source case-pack: finalized `1.0.2`  
Candidate case-pack: draft `1.0.3`  
Decision: `HUMAN_REVIEW_REQUIRED`  
Production readiness: `not_production_ready`

## 결론

단일 `relevant_chunk_ids` 목록만 정답으로 인정하던 RAG 평가 계약을 확장해, 사람이 명시적으로
승인한 복수의 동등한 근거 그룹을 표현할 수 있게 했다. 기존 목록은 첫 번째 primary 그룹으로
보존되며, 그룹 내부는 모두 충족해야 하고 그룹 간에는 하나만 완전히 충족하면 된다.

최종화된 `1.0.2`에서 세 critical case만 복사해 `1.0.3` 후보로 격리했다. 후보 감사 결과는
`3/3` reachable, blocked `0`, best-group recall `1.0`이다. 세 변경은 아직 draft이며 사람의 직접
검토 없이 승인·최종화하거나 실제 진단 증거로 사용하지 않는다.

## 계약

```json
{
  "evidence_contract_version": "rag-evidence-contract-v2",
  "relevant_chunk_ids": ["primary-a", "primary-b"],
  "acceptable_evidence_groups": [
    ["primary-a", "primary-b"],
    ["alternative-c"]
  ]
}
```

- 첫 그룹은 기존 `relevant_chunk_ids`와 정확히 같아야 한다.
- 그룹과 그룹 내부 chunk ID는 중복될 수 없다.
- 선언된 모든 chunk ID는 잠긴 corpus에서 확인돼야 한다.
- retrieval, deterministic selection, citation은 같은 best-group matcher를 사용한다.
- citation precision은 전체 허용 ID 합집합 밖의 인용을 계속 실패 처리한다.
- expected ID와 그룹은 adapter 입력에서 제거되므로 evaluator-only 경계를 유지한다.
- 기존 계약은 자동으로 `rag-evidence-contract-v1` 단일 그룹으로 해석된다.

## 구현

- `rag_evidence_contract.py`: 계약 파싱, 불변 표현, best-group matching, descriptor.
- `rag_evaluation.py`: retrieval/selection/citation의 동일한 any-of 의미와 trace provenance.
- `contract_audit.py`: 모든 허용 그룹의 순위와 도달 가능성 감사.
- `case_revision.py`: revision spec v2와 대체 그룹이 포함된 격리 후보 생성.
- `case_revision_review.py`: 모든 그룹·원문·순위가 표시되는 동적 검토 HTML.
- RAG API schema와 UI: contract version, matched group, alternative match 표시.
- contract/scorer versions: `rag-retrieval-trace-v3`, `rag-evaluation-trace-v4`,
  `rag-evaluation-summary-v4`, `rag-evaluation-scorer-v4`.

## 후보 변경

| Case | Primary | Alternative | 근거 의미 |
| --- | --- | --- | --- |
| `KO-RAG-SCOPE-002` | `ko-247daa1b46cc86363d892938` | `ko-b70165b4b3f47cf87a34ff25` | 후보 추천과 배포 승인의 분리 |
| `KO-RAG-SCOPE-003` | `ko-5177b421f19ca0909ee719f2` | `ko-9c59bd29a1b754b80c476d62` | managed root의 development 경계 |
| `KO-REFUSE-002` | `ko-605f4586e724cc70f087851d` | `ko-8b7f33d47228772f0cbba790` | 실제 조직 production 승인 비주장 |

Candidate summary:

- total cases: `64`;
- retained approvals: `61`;
- pending critical reviews: `3`;
- retrieval contracts reachable: `3/3`;
- blocked retrieval contracts: `0`;
- Portfolio bootstrap allowed: `false`.

## 예상 영향과 한계

이전 실제 21-result 진단에서 위 alternative ID는 각 구성에서 동일하게 선택됐다. 따라서
사람이 세 대체 근거를 승인하고 같은 런타임 출력을 다시 얻는다는 조건 아래 selection과
citation identity는 `21/21`로 개선될 것으로 예상된다. 이는 새 실행 결과가 아닌 과거 trace에
대한 projection이다.

엄격 RAG 성공의 projection은 `11/21`에서 `14/21`이다. `KO-REFUSE-002` 세 결과는 citation과
semantic 계약을 함께 충족하지만, `KO-RAG-SCOPE-002`와 `KO-RAG-SCOPE-003`은 source 표현과
required-fact label의 의미 정렬 문제가 남는다. 0.5B의 `KO-RAG-SCOPE-001` 금지 명제 반복도
별도 문제다. Any-of 계약은 이 실패를 숨기거나 자동 통과시키지 않는다.

## 검증

- focused compatibility and contract tests: `28 passed`;
- full backend suite: `247 passed, 1 skipped, 2 warnings`;
- final-image focused Docker suite: `24 passed, 2 warnings`;
- Ruff: passed;
- frontend lint, typecheck, production build: passed;
- deployed desktop and 390 px mobile RAG trace UI: passed, console error/warning `0`;
- candidate JSON and review HTML structure: validated;
- API health: `ok`; Alembic: `202608040001 (head)`;
- Docker backend/database/Ollama: healthy; frontend/worker: running;
- local `file://` browser visual QA: unavailable because the in-app browser blocks local file URLs.

## 식별자

- revision report identity hash: `d2b570fe347967de9b44f90c53276630292f11d814805aaf0ecba778a4e90401`;
- revision report file SHA-256: `6ec86d60b4bd9076f5de48ffc34fd873c988a000cd5d4e60244440d237cb6c14`;
- retrieval audit identity hash: `0683ba78463353309fc485dd988aef4699a92536ae48376b696425a2737dd78d`;
- retrieval audit file SHA-256: `be00dc3965897aeb786a18a2b831e1bbac46cf794aab1711d36f382acc88524a`;
- revision spec file SHA-256: `23eef2aa6bea61f9782aa52885b4734e9bc2b9009a663e1434527a2c1191439f`;
- review HTML file SHA-256: `c0f89f9d9ed900425ac5e94a05714b0072c5bdc5e598e75ca732dcaab8422ccd`;
- candidate manifest SHA-256: `019aa1e32f1190e8fbac7951503fa2c2b4a631c73e04adfbd69291a2dd485d18`;
- candidate cases SHA-256: `e69ae7835d64daeec5c37f0eb1ce492e5b5fe9235f62135d0694dc82bf06f0d0`;
- candidate retained reviews SHA-256: `dead46fdea2a24bdc962c69c0d90aa1ca9ba0ce5a1162aae9d7ad3d1588dd49b`;
- source `1.0.2` cases SHA-256: `cff43222bd8cb4823cc39fcf9c1ffe54fc5d31734053b4f44e9ce605830c240d`.

## 다음 승인 경계

검토자는 `reference_workload/revisions/1.0.3/revision_review.html`에서 세 사례의 primary와
alternative 원문을 직접 확인하고 승인 또는 거절을 기록해야 한다. 생성된 attestation을
`review_attestation.json`으로 둔 뒤에만 hash-bound finalization과 21-result 실제 재실행을
진행한다. 그 전에는 candidate, diagnostic, Portfolio, Gate 상태를 승인 증거로 해석할 수 없다.
