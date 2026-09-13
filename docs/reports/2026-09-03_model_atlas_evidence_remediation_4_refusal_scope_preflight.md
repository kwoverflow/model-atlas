# Model Atlas Evidence Remediation 4: Refusal and Scope Preflight

Date: 2026-09-03 JST  
Execution source: finalized revision `1.0.1`  
Revision candidate: `1.0.2`  
Decision: `HUMAN_REVIEW_REQUIRED`  
Production readiness: `not_production_ready`

> Completion notice (2026-09-04 JST): reviewer `김대건` approved the single revision, `1.0.2`
> finalized at 64/64 approvals, and the 21-result diagnostic completed. The final audit and
> diagnostic are documented in
> `docs/reports/2026-09-04_model_atlas_evidence_remediation_4_refusal_scope_diagnostic.md`.

## Intended Diagnostic

This remediation unit targets seven critical cases before the next actual-runtime run:

- three `rag_version_or_scope` cases;
- four `insufficient_evidence_refusal` cases;
- three configured runtime entries;
- one trial per case, for 21 planned actual Results.

The scope tests whether the model distinguishes Gate approval, recommendation rank, development
trust, external production approval, connected paging state, and real customer data. No runtime
diagnostic was started until every declared retrieval contract passed preflight.

## Preflight Finding

The finalized `1.0.1` preflight found six reachable contracts and one blocked critical contract.
`KO-RAG-SCOPE-001` expected `EVALUATOR_GUIDE_KO.md > Evidence Trust`, which ranked 15 under the
declared lexical retriever and did not directly answer whether a local `APPROVED` Gate can be
represented as production-ready.

The query already retrieved `docs/deployment_gate.md > Sprint 4A Status Separation` at rank 1.
That section directly states that a Gate verdict does not authorize production deployment and
shows `APPROVED` together with `NOT_PRODUCTION_READY`. The problem was therefore an expected-label
identity mismatch, not a query-generation failure.

Preflight evidence:

- reachable / blocked / critical blocked: 6 / 1 / 1;
- initial audit logical SHA-256:
  `3d96e8312bcb7bf02c03f633ef00a736b88821dedd2b91b4ea1d17599930dcc9`;
- initial audit file SHA-256:
  `5498795e3843853fd59c6ada3db196155cf1476e4ce98aa28964540686551b1c`.

## Revision Candidate 1.0.2

Candidate `1.0.2` changes exactly one case:

| Case | Old evidence | Old rank | Revised evidence | Revised rank |
| --- | --- | ---: | --- | ---: |
| `KO-RAG-SCOPE-001` | `EVALUATOR_GUIDE_KO.md / Evidence Trust` | 15 | `docs/deployment_gate.md / Sprint 4A Status Separation` | 1 |

The user query is unchanged. The revised contract reaches its expected chunk with recall `1.0`
inside `top_k=5`. The candidate retains all 63 unaffected approvals and returns only this changed
critical case to draft:

- approved cases: 63 of 64;
- approved critical cases: 19 of 20;
- pending human review: 1;
- `portfolio_ready=false`;
- bootstrap and runtime execution disabled until finalization.

Logical revision report SHA-256:
`7f337920ab26ec388c5c8f2692f43883024cc7513ef1268dddf33320cac739d1`.

## Revision-Chain Safety

The revision generator now supports a finalized revision as the source of a newer revision. Before
copying any case or approval, it verifies the parent manifest version, revision report logical
hash, finalization report logical hash, manifest/cases/review file hashes, and
`portfolio_ready=true`. An unfinalized or modified parent fails closed.

Non-Agent RAG contracts can now be revised without requiring an Agent `expected_steps` block. When
an Agent block exists, its single retrieval step remains hash-bound to the revised expected chunk.
The review display also falls back to `input_payload.query`, so non-Agent cases show the exact user
question rather than an empty request.

The Make targets accept `REFERENCE_CASE_REVISION` and currently default to `1.0.2`, removing the
hard-coded revision directory while preserving explicit version selection.

## Verification

```text
Revision-chain and non-Agent finalization tests: 2 passed, 2 warnings
Backend full suite: 231 passed, 1 skipped, 2 warnings
Backend Ruff: passed
Docker focused tests: 25 passed, 2 warnings
Docker Ruff and backend/worker image build: passed
1.0.2 changed-contract audit: pass, rank 1, recall 1.0
Review HTML: one case, exact question present, old/new ranks present
Canonical workload / historical Results mutated: false / false
Production readiness: not_production_ready
```

The live canonical overview remains version `1.0.0` with 384 selected Results, 110 critical
failures, zero of 30 model outputs reviewed, and three of three Gates `BLOCKED`.

## Human Review and Next Run

The reviewer must inspect the single old/new evidence pair in
`reference_workload/revisions/1.0.2/revision_review.html`, record an approval or rejection, enter a
human name, accept the attestation, and download the JSON. After a valid attestation finalizes the
pack at 64 approved cases and 20 approved critical cases, rerun the seven-case preflight and then
execute the isolated 21-result diagnostic. Those Results must remain
`local_actual_runtime_diagnostic`, not portfolio or Gate evidence.
