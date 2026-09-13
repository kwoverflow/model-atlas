# Model Atlas Evidence Remediation 8 Finalization

Date: 2026-09-07  
Status: 1.0.4 finalized and actual bounded diagnostic completed  
Production readiness: `not_production_ready`

## Outcome

The two-case 1.0.4 semantic revision was personally reviewed, hash-validated, and finalized. The
approved pack contains 64/64 approved cases and 20/20 approved critical cases. A subsequent actual
Ollama diagnostic passed all 21 executions across the small baseline, medium candidate, and prompt
variant.

This closes the narrow refusal/version-scope evidence-contract remediation. It does not replace the
384-result Portfolio matrix, recalculate existing Gates, prove general model intelligence, or grant
production approval.

## Human Review And Finalization

The downloaded attestation passed all enforced identity checks:

- schema: `model-atlas-reference-case-pack-revision-attestation-v2`;
- revision: `1.0.4`;
- reviewer: `김대건`;
- reviewed at: `2026-09-06T23:56:20.070+09:00`;
- decisions: Scope 002 approved, Scope 003 approved;
- rejected cases: none;
- revision report identity:
  `6dfc5274162cd5b434e565d6b6683b6b146457c06a9788cff27906235547aec6`;
- attestation file SHA-256:
  `21a7212e8a26ff8356517834b4ca3817d7c3eb719a2f65054ca2be714c4459c8`.

Finalization state:

| Check | Result |
| --- | --- |
| Approved cases | 64/64 |
| Approved critical cases | 20/20 |
| Draft / rejected | 0 / 0 |
| Retrieval audit | pass, zero blocked |
| Portfolio case-pack eligibility | true |
| Bootstrap allowed | true |
| Authoritative Portfolio evidence | false |
| Production readiness | `not_production_ready` |

Finalization identities:

- review manifest SHA-256:
  `f98bbb165f5a35d09e5e640f1ff5c6a9bf416758becb016963a1a671e8aaa8f0`;
- finalization identity:
  `5ab6e4f02479c11182b9163544a786a0c21e578f067eee14eeb48cdf4886a950`;
- finalization report file SHA-256:
  `79e4525d9634c690b9337863ffb66b7b90c458d5fc0b2b7869fde00a2e4fbcff`.

## Actual Runtime Evidence

The finalized 1.0.4 pack was bootstrapped as evaluation suite
`e51668dd-b098-42f5-8787-c2f2de2184ec`. The diagnostic executed three scope cases and four refusal
cases once per runtime configuration.

| Configuration | Model / prompt | Success | Semantic | Bounded answer | Alt semantic |
| --- | --- | ---: | ---: | ---: | ---: |
| `small-baseline` | qwen2.5:0.5b / v1 | 7/7 | 7/7 | 7/7 | 2 |
| `medium-candidate` | qwen2.5:1.5b / v1 | 7/7 | 7/7 | 7/7 | 2 |
| `prompt-variant` | qwen2.5:1.5b / v2 | 7/7 | 7/7 | 7/7 | 2 |

Aggregate evidence:

- strict RAG success: 21/21;
- semantic contract: 21/21;
- required-fact contract: 21/21;
- bounded-answer contract: 21/21;
- retrieval, deterministic selection, and citation contracts: 21/21 each;
- reviewed alternative semantic matches: 6;
- refusal: 12/12;
- groundedness: 1.0;
- unsupported-claim rate: 0.0;
- forbidden-claim violations: 0;
- timeout / OOM / other errors: 0 / 0 / 0.

Database trace inspection confirmed that Scope 002 and Scope 003 used
`rag-semantic-contract-v2`, required-fact group index 1, and citation group index 1 in every
configuration. All other semantic cases used their preserved v1 primary group; Refuse 002 retained
its previously approved alternative citation group.

Run and artifact identities:

- small baseline run: `69973089-6e68-4fea-bfc6-ea79b341f6bd`;
- medium candidate run: `0ecdbbe9-6e82-44dd-ac5c-aa5e97e66406`;
- prompt variant run: `f48df4b4-2e69-4821-9b0d-426ae55a1641`;
- artifact:
  `artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.4-semantic-v2.json`;
- artifact SHA-256:
  `054b5163ccbdf0f2da934b3bb9c0cdd1caa82b72a4020c8d32d2d3e6c46a7182`.

## Interpretation

The 21/21 result proves the tested contract path is internally consistent: retrieval can reach the
reviewed evidence, deterministic selection cites it, answer construction stays inside that source
boundary, and the semantic evaluator accepts one explicitly approved meaning group without
weakening forbidden-claim checks.

It does not prove that qwen2.5:0.5b or qwen2.5:1.5b is broadly production-ready. These seven cases
use constrained JSON enums and deterministic selected claims by design. The larger historical
Portfolio still contains poor Agent, Tool, and general RAG quality, all three canonical Gates remain
blocked, 30 planned model outputs remain unreviewed, and no verified production-captured evidence
exists.

## Verification

- explicit 1.0.4 validation: `ready`;
- focused finalization/semantic/answer tests: 9 passed;
- full backend suite: 259 passed, 1 skipped;
- backend Ruff: pass;
- rebuilt Docker backend and Agent worker: pass;
- Docker focused tests: 24 passed;
- Docker Ruff: pass;
- Alembic: `202608040001 (head)`;
- Docker runtime entries completed: 3/3;
- actual Results / Metrics: 21 / 21;
- runtime timeout / OOM: 0 / 0;
- 1.0.4 execution-detail UI: 7/7 rendered, semantic v2 and alternative-group state visible;
- browser console warnings/errors: 0;
- canonical cases mutated: no;
- finalized 1.0.3 mutated: no;
- historical Results mutated: no;
- authoritative Portfolio/Gate evidence changed: no.

The next remediation target is Tool argument validity and failure recovery. Any improvement should
again begin with failure clustering, isolate contract changes from runtime changes, and preserve the
same human-review and non-authoritative diagnostic boundaries.
