# Model Atlas Sprint 6A Phase 1-2 Implementation Report

Recorded: 2026-08-04

Historical snapshot: this report records the mandatory stop state that existed on 2026-08-04.
Human source review and Phase 3 were completed on 2026-09-01; see
`2026-09-01_model_atlas_sprint_6a_phase_3_runtime_matrix.md` for the current evidence state.

## Executive result

Sprint 6A was implemented through the specification's mandatory human-approval boundary. The
repository now has a deterministic Korean reference-workload corpus, a 64-case draft pack, a
hash-bound human-review contract, an idempotent bootstrap path, and fail-closed readiness checks.

The implementation intentionally stopped before runtime-matrix orchestration, aggregate API/UI,
Gate/report generation, and bounded modularization. There are no real human-approved source cases,
so continuing past Phase 2 or claiming portfolio readiness would violate the Sprint 6A stop rule.

## Phase status

| Phase | Status | Evidence |
| --- | --- | --- |
| 0. Baseline verification | Complete | Baseline tests, frontend checks, Docker health, and Alembic head recorded |
| 1. Contracts and corpus | Complete | Locked manifest, secure loader, deterministic chunks and hashes, tests |
| 2. Draft cases and policy gate | Complete | 64 drafts, 20 critical drafts, review worksheet, no-write bootstrap gate |
| Human source review | Incomplete | 0 approved cases and 0 approved critical cases |
| 3. Runtime matrix | Not started by stop rule | No actual-runtime configuration executed |
| 4. Aggregate API and UI | Not started by stop rule | No `/reference-workload` route claimed |
| 5. Gate and report integration | Not started by stop rule | No Gate outcome or generated portfolio report |
| 6. Bounded modularization | Not started by stop rule | Existing public modules remain unchanged |
| 7. Portfolio verification | Not eligible | Required approved cases and real evidence are absent |

## Workstream A: reference workload

### Versioned source contract

Created under `reference_workload/`:

- `manifest.json`: repository-relative Markdown allowlist with locked SHA-256 values;
- `cases.jsonl`: 64 generated draft case contracts;
- `review_manifest.jsonl`: intentionally empty human-decision ledger;
- `review_worksheet.csv`: 64-row review aid with all human evidence fields blank;
- `runtime_matrix.example.json`: three environment-driven future configuration examples;
- `README.md`: ownership, safety, and review boundary.

### Backend modules

Created under `backend/app/reference_workload/`:

- `contracts.py`: strict manifest, case, review, and readiness contracts;
- `manifest.py`: secure repository path resolution and manifest locking;
- `corpus.py`: deterministic Markdown section chunking and corpus provider;
- `cases.py`: case/review parsing, hash binding, taxonomy validation, and worksheet export;
- `draft_cases.py`: deterministic draft-case authoring;
- `bootstrap.py`: no-write readiness gate and idempotent import using existing entities;
- `cli.py`: lock, draft, worksheet, validate, and bootstrap commands;
- `__init__.py`: bounded public exports.

No primary Sprint 6A Python implementation file exceeds 800 lines. The largest is
`draft_cases.py` at 692 lines.

### Corpus evidence

| Property | Observed value |
| --- | --- |
| Workload slug | `model-atlas-operator-assistant-ko` |
| Workload version | `1.0.0` |
| Corpus ID | `model-atlas-operator-handbook-ko` |
| Source documents | 14 |
| Markdown chunks | 200 |
| Manifest SHA-256 | `151126c85c0a1ad71eff5da90cfaf2df977fdfb3cbea16e6bcc5a174c3f76711` |
| Corpus SHA-256 | `b6db4643768f1e9735507747aa88e54f93c7a3099dcb98ffbf6e9ac3e322e3cf` |

The loader rejects absolute paths, traversal, missing files, source-hash mismatch, non-UTF-8
content, and resolved symlink escape. It does not use a database session or network access. The
existing default RAG fixture registry remains unchanged.

### Draft taxonomy and review state

| Category | Draft cases | Critical drafts |
| --- | ---: | ---: |
| `rag_single_document` | 12 | 2 |
| `rag_multi_document` | 10 | 3 |
| `rag_version_or_scope` | 6 | 3 |
| `insufficient_evidence_refusal` | 8 | 4 |
| `tool_single_step` | 10 | 2 |
| `tool_failure_recovery` | 6 | 2 |
| `rag_tool_combined` | 6 | 3 |
| `agent_multi_step` | 6 | 1 |
| **Total** | **64** | **20** |

All 64 source cases have `review.status="draft"`. Approved cases: **0/64**. Approved critical
cases: **0/20**. Reviewer identities, timestamps, decisions, and notes were not generated.

An external review is accepted only when it contains a known case ID, the exact normalized case
SHA-256, a decision, a real reviewer identity, a timezone-aware timestamp, and notes. Stale hashes,
unknown IDs, duplicates, or missing provenance fail validation.

## Bootstrap and policy behavior

The bootstrap path reuses the existing `WorkloadProfile`, `EvaluationSuite`, `EvaluationCase`,
`MetricDefinition`, `AcceptancePolicy`, and `AcceptancePolicyRule` entities. It does not create a
parallel evaluation or Gate engine.

Readiness is checked before any database write. With the current empty review manifest, bootstrap
returns a nonzero status and creates no workload, suite, case, metric, policy, or rule rows. A
test-only fully approved fixture verifies that a valid import creates one workload, one suite, 64
active cases, 11 metrics, one policy, and 11 rules, and that a second import creates no duplicates.
Changed inputs conflict with an existing immutable version rather than silently rewriting lineage.

The final CLI check returned `blocked_human_review_required`; a direct read-only database query
confirmed zero `workload_profiles` rows for `model-atlas-operator-assistant-ko`.

The policy name is `Model Atlas Operator Assistant Local Evaluation Policy v1`. Even a future
locally passing policy remains separate from production readiness.

## Repository integration

- Added Make targets: `reference-lock`, `reference-draft`, `reference-review-worksheet`,
  `reference-validate`, and `reference-bootstrap`.
- Added Docker mounts for the versioned workload and read-only corpus documentation.
- Added `MODEL_ATLAS_REPOSITORY_ROOT=/workspace` to backend and Agent worker services.
- Included `reference_workload/` in `tools/build_evaluation_package.ps1`.
- Added `docs/reference_workload.md` and updated the next-sprint boundary in
  `docs/project_status.md`.
- Added four focused backend test modules for manifest, corpus, cases, and bootstrap behavior.

## Database and migration status

- Baseline and current Alembic head: `202608040001 (head)`.
- `alembic upgrade head`: passed.
- Sprint 6A Phase 1-2 adds no database table, entity, or migration.
- `backend/app/models/entities.py` is byte-identical to the Sprint 5H-H package:
  `fcc20cb0e1ec504ce583b9f21e5acacc4057351f915d58f7138eb7a36d65bf2a`.
- All 31 baseline files under `backend/alembic/` were compared with the Sprint 5H-H package and
  had zero mismatches.

`alembic check` currently reports the repository's pre-existing index/constraint naming diff.
Because both the entity file and migration tree are unchanged from the supplied baseline, this is
recorded as baseline migration drift rather than a Sprint 6A schema change. No migration was
generated to hide or normalize it.

## Verification results

### Pre-change baseline

```text
backend pytest: 186 passed, 1 warning
backend and tools Ruff: passed
frontend typecheck: passed
frontend lint: passed
frontend production build: passed
Alembic current: 202608040001 (head)
```

### Sprint 6A Phase 1-2 final verification

```text
Docker backend pytest: 202 passed, 1 warning
Docker backend Ruff: all checks passed
Local backend pytest: 201 passed, 1 skipped, 1 warning
Docker frontend typecheck: passed
Docker frontend lint: passed
Docker frontend production build: passed
Docker compose config: passed
Alembic fresh-database base-to-head upgrade: passed
```

The local skip is the Windows environment's unavailable symlink creation. The same symlink-escape
security test passed in the Linux Docker suite. The warning is the existing upstream Starlette
`TestClient` deprecation warning. The isolated migration database was removed after the successful
base-to-head verification.

## Operator commands

Generate or validate versioned source artifacts:

```powershell
docker compose run --rm backend python -m app.reference_workload.cli lock-manifest
docker compose run --rm backend python -m app.reference_workload.cli draft-cases --force
docker compose run --rm backend python -m app.reference_workload.cli review-worksheet
docker compose run --rm backend python -m app.reference_workload.cli validate
docker compose run --rm backend python -m app.reference_workload.cli bootstrap
```

The final two commands must fail with a review shortfall in the current state. This is expected and
is the evidence that draft cases cannot silently become active.

Run regression verification:

```powershell
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
docker compose run --rm backend alembic upgrade head
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm run lint
docker compose run --rm frontend npm run build
docker compose config --quiet
```

## Evidence and decision status

| Required final item | Current result |
| --- | --- |
| Actual runtime configurations executed | None; Phase 3 is blocked by the required review gate |
| Distinct actual model artifacts | 0 |
| Human-approved source cases | 0 of at least 60 |
| Human-approved critical source cases | 0 of at least 20 |
| Manually reviewed model outputs | 0 of at least 30 |
| Configuration comparison metrics | Not generated |
| Gate outcomes | Not generated |
| Release decision | Not generated |
| Production-captured evidence | 0 |
| Reference-workload portfolio status | `incomplete` |
| Production readiness | `not_production_ready` |

## Required next action

A person must review `reference_workload/review_worksheet.csv` against the locked source chunks and
provide real decisions in `reference_workload/review_manifest.jsonl`. The minimum gate is 60
approved cases including all 20 required critical cases. After validation and idempotent bootstrap
pass, Sprint 6A may continue with Phase 3 runtime-matrix orchestration.
