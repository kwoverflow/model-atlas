# Model Atlas Evidence Remediation 1: Output Review Plan

Recorded: 2026-09-02

## Result

The first post-Phase 7 evidence-remediation unit is complete. Model Atlas now converts the exact
110-reference-failure queue into 20 deterministic clusters and a balanced 30-output human-review
plan without writing labels or upgrading evidence trust.

The live plan covers all 20 critical cases, all eight critical categories, and all three portfolio
configurations. Each configuration contributes ten selected outputs. Seventeen clusters reproduce
across every configuration and are P0; three repeated Tool clusters are P1.

## Delivered behavior

- Versioned `model-atlas-reference-output-review-plan-v1` API contract.
- Stable cluster and candidate-assessment hashes over exact Result IDs.
- Deterministic P0, P1, and P2 priority rules.
- One-per-cluster-first selection followed by configuration-balanced filling.
- Read-only candidate assessments with `applied=false` and `human_reviewed=false`.
- Heuristic-only Judge rows now correctly require review.
- Result-scoped Judge Review API and deep links.
- Responsive `/reference-workload/review-plan` UI with cluster and selected-output tables.
- JSON artifact persisted for evaluator inspection.

## Actual evidence

```text
Plan hash: 587c35dbf6d4dba85b221551103e683ef903f82e8bdca37e4ab65cd81008a65e
Artifact SHA-256: 65146e64040169b439da165471c9635aa25c1e6d2eeb601514ee21a290a705d5
Failures / clusters / selected: 110 / 20 / 30
Cluster priorities P0 / P1 / P2: 17 / 3 / 0
Selected priorities P0 / P1 / P2: 27 / 3 / 0
Selection by configuration: 10 / 10 / 10
Unique cases / categories: 20 / 8
Human reviewed: 0
Remaining target: 30
Production readiness: not_production_ready
```

Repeated API reads returned the same plan hash. A focused Judge Review deep link returned exactly
one row with `score_source=heuristic`, `needs_review=1`, `candidate_label_count=0`, and
`human_reviewed_count=0`.

## Compatibility and verification

No database migration, Gate recomputation, report mutation, or evidence-source normalization was
introduced.

```text
Backend targeted tests: 13 passed
Backend full suite: 222 passed, 2 warnings
Backend Ruff: passed
Frontend ESLint: passed
Frontend TypeScript and Next.js production build: passed
Backend, Agent worker, and frontend Docker builds: passed
Desktop 1280x720 UI: passed; no document-level horizontal overflow
Mobile 390x844 UI: passed; no document-level horizontal overflow
Focused result navigation: passed; one Judge row
Browser console: 0 warnings or errors
```

The warnings are the existing upstream Starlette TestClient deprecation and container pytest-cache
permission warnings. Neither affects the test result or runtime behavior.

## Next remediation unit

Human review remains required. The next engineering step is to use the plan's P0 clusters to fix
the response contracts in this order: Agent execution and policy compliance, refusal and scope
handling, RAG citation grounding, then Tool argument and recovery behavior. Each bounded change
should rerun only its affected cases first and then the complete three-configuration matrix before
any Gate claim is reconsidered.
