# Model Atlas Evidence Remediation 8

> Historical pre-finalization record. The candidate was approved, finalized, and measured on
> 2026-09-07. See
> `2026-09-07_model_atlas_evidence_remediation_8_finalization_and_actual_diagnostic.md`.

Date: 2026-09-06  
Status: implementation verified; isolated 1.0.4 candidate awaiting human review  
Production readiness: `not_production_ready`

## Decision Summary

Evidence Remediation 8 fixes two distinct problems without weakening evaluation. First, scope
answers are now bounded to a deterministically selected source claim, which prevents a small model
from repeating the user's unsafe proposition and accidentally satisfying a forbidden-claim
matcher. Second, required facts can represent explicitly reviewed, semantically equivalent source
statements through an any-of group contract.

The runtime change was measured against finalized case pack 1.0.3. It improved strict success from
14/21 to 15/21 and achieved 21/21 bounded-answer compliance. The remaining six failures are the two
known scope-label mismatches repeated across three configurations.

An isolated 1.0.4 candidate has been generated for those two cases. It is not finalized, has not
been executed as runtime evidence, and cannot be bootstrapped until a person completes the
hash-bound review.

## Problem Diagnosis

The 1.0.3 diagnostic proved retrieval, selection, citation, and grounding were correct for Scope
002 and Scope 003, but the evaluator required only one historical wording:

| Case | Selected source claim | Legacy required fact |
| --- | --- | --- |
| `KO-RAG-SCOPE-002` | 추천 순위가 곧 배포 승인이 아니라는 UI 문구와 데이터 경계를 검토한다. | 추천은 비구속적 후보 탐색 |
| `KO-RAG-SCOPE-003` | Managed publisher root: `...`, development tier. | development와 external trust 분리 |

Treating those outputs as wrong would conflate a label-coverage limitation with a model failure.
Simply relaxing token thresholds would also hide genuinely incorrect claims. The remedy therefore
uses reviewed alternatives with explicit provenance and preserves the original fact as group 0.

The separate 0.5B Scope 001 failure came from answer generation: a valid selected claim was cited,
but the model copied the question's unsafe proposition. The new answer contract removes that
generation ambiguity while staying inside the public input boundary.

## Implemented Contracts

### Semantic contract v2

`rag-semantic-contract-v2` enforces AND semantics within each fact group and OR semantics between
groups. `required_facts` remains mandatory and must exactly equal the first group. The evaluator
records every group result, the best-matching facts, overall satisfaction, and the satisfied group
index. Legacy v1 cases continue to behave as one group.

### Bounded answer contract v1

`rag-bounded-answer-contract-v1` compiles an exact answer for scope and refusal categories from:

- the public case query;
- the selected retrieved source claim.

It never receives evaluator-only relevant IDs, required facts, forbidden claims, or reference
answers. The OpenAI-compatible adapter consumes the prepared public contract, while the evaluator
checks exact compliance and persists its version and strategy.

### Provenance versions

| Component | Current version |
| --- | --- |
| RAG semantic contract | `rag-semantic-contract-v2` |
| Bounded answer contract | `rag-bounded-answer-contract-v1` |
| RAG evaluation trace | `rag-evaluation-trace-v5` |
| RAG evaluation summary | `rag-evaluation-summary-v5` |
| RAG scorer | `rag-evaluation-scorer-v5` |
| OpenAI-compatible adapter | `openai-compatible-v17` |
| Case revision report | `model-atlas-reference-case-pack-revision-report-v3` |
| Case revision attestation | `model-atlas-reference-case-pack-revision-attestation-v2` |

## Actual 1.0.3 Runtime Evidence

Docker was rebuilt and the finalized 1.0.3 pack was run for three scope cases and four refusal
cases across the small baseline, medium candidate, and prompt variant.

| Configuration | Strict success | Answer contract | Refusal | Timeout / OOM |
| --- | ---: | ---: | ---: | ---: |
| `small-baseline` | 5/7 | 7/7 | 4/4 | 0 / 0 |
| `medium-candidate` | 5/7 | 7/7 | 4/4 | 0 / 0 |
| `prompt-variant` | 5/7 | 7/7 | 4/4 | 0 / 0 |

Aggregate results:

- strict success: 15/21;
- retrieval, deterministic selection, and citation: 21/21 each;
- bounded-answer contract: 21/21;
- refusal: 12/12;
- groundedness: 1.0;
- unsupported-claim rate: 0.0;
- forbidden-claim violations: 0;
- remaining failures: Scope 002 and Scope 003 in all three configurations.

Run IDs:

- small baseline: `5a581802-eea1-4e94-aacc-970267b0cb84`;
- medium candidate: `2aaa0e8a-0263-4d98-8cdd-600e063b2e5b`;
- prompt variant: `fc6c16b2-4752-4479-b1ef-7a85bfd366d8`.

Artifact:

- path: `artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.3-bounded-answer-v1.json`;
- SHA-256: `eda3beec3dd49bffbd5214b732640c17cecb8d73f8dc12495ae3ba191c56769b`;
- evidence class: actual local-runtime diagnostic;
- authoritative Portfolio/Gate evidence: no.

## Isolated 1.0.4 Candidate

Only `KO-RAG-SCOPE-002` and `KO-RAG-SCOPE-003` change. Their evidence contracts, queries, source
corpus, and forbidden claims are preserved. Each semantic v2 contract adds one reviewed alternative
required-fact group matching the already selected and cited source claim.

Candidate state:

- 64 total cases;
- 62 retained approvals;
- 2 draft critical cases;
- retrieval audit: pass, zero blocked;
- `portfolio_ready=false`;
- `bootstrap_allowed=false`;
- attestation: absent;
- finalization report: absent;
- report identity: `6dfc5274162cd5b434e565d6b6683b6b146457c06a9788cff27906235547aec6`.

Important candidate identities:

| Artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `edbeb4cd8b3a92ed5ab501e9a53a28f531476082465f9690a40e5e987d15cc95` |
| `cases.jsonl` | `a8b367fca7a21c6fda20f5086a1bb4180cbbd30f82f7f04937057cad1a4aa4c7` |
| `review_manifest.jsonl` | `5bc4ff9ddedff522801fbd29da123cb1106d35e571a37c699f6c3438c033bdb8` |
| `revision_report.json` file | `91745c4f028d52dfd905fd6b5d3df02acb6c78e716fa9a72d19bac1afdd9dc46` |
| `revision_review.html` | `b3e536852ea6c1df9776c9b15857a89533748b62bffefb63f6eff72d4cab6440` |

Deterministic candidate tests reach evidence group index 1 and required-fact group index 1 for both
draft cases. That supports a post-approval expectation of 21/21 on the same diagnostic, but it is a
projection only. Actual 1.0.4 runtime evidence must wait for approval and finalization.

## Verification

- backend Ruff: pass;
- focused semantic, answer, evaluator, runtime-matrix, and candidate tests: 33 passed;
- full backend suite: 259 passed, 1 skipped;
- Docker-focused tests: 24 passed;
- frontend ESLint: pass;
- frontend TypeScript: pass;
- frontend production build: pass;
- Docker backend/worker/frontend build: pass;
- Alembic: `202608040001 (head)`;
- desktop and mobile execution-detail UI: visually checked;
- candidate validation: intentionally incomplete with exit code 2.

The only warnings were the existing TestClient deprecation and a host pytest-cache permission
warning. Neither changed test outcomes.

## Human Review Boundary

Open `reference_workload/revisions/1.0.4/revision_review.html`, review both cases, record one decision
and a non-empty note per case, enter the reviewer name, confirm the direct-review statement, and
download the generated attestation. Finalization must validate the v2 statement, report identity,
case identities, reviewer, timestamp, and complete decision set.

Until that happens, 1.0.4 must not be bootstrapped or presented as passing runtime evidence. This
remediation does not alter finalized 1.0.3, canonical cases, historical Results, Portfolio runs,
Gates, release decisions, or production-readiness state.
