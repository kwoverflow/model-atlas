# Model Atlas Sprint 6A Phase 4 Aggregate API and UI Report

Recorded: 2026-09-01

## Executive result

Sprint 6A Phase 4 is complete. Model Atlas now exposes a deterministic aggregate read model and a
guided `/reference-workload` page over the Phase 3 Korean Operator Assistant evidence. The page
uses the exact latest stored actual-runtime run for each current matrix entry and separates source
approval, model-output review, Gate verdict, evidence trust, and production readiness.

The live aggregate reports 3 completed configurations, 384 actual local-runtime Results, 110
critical failures, 0 reviewed model outputs, and 0 stored Gate outcomes. Evaluation execution is
complete, but the portfolio remains incomplete, evidence trust is `needs_judge_review`, Gate is
`NOT_EVALUATED`, and production readiness is `not_production_ready`.

## Delivered behavior

### Backend

- Added strict Pydantic read contracts for workload, manifest, corpus, case coverage, review
  coverage, runtime configurations, comparison rows, failures, Gate outcomes, and portfolio checks.
- Added `/overview`, `/cases`, `/configurations`, `/comparison`, and `/failures` routes.
- Revalidates repository contracts on every read and fails with HTTP `409` on contract drift.
- Selects only completed `local_actual_runtime` runs for the current matrix and chooses the newest
  run per entry.
- Reuses existing Gate metrics, evidence trust, supply-chain verification, and release-readiness
  services.
- Normalizes `local_actual_runtime` to the canonical local-authored trust tier without changing raw
  Result provenance.
- Builds failure-first links to Benchmark Run, Judge Review, and existing Gate detail pages.

### Frontend

- Added the evaluator-oriented `/reference-workload` page.
- Added a separate four-state strip for Evaluation, Gate, Evidence Trust, and Production Readiness.
- Added two rendered comparison charts and a full configuration table.
- Added a critical-failure queue with the first 12 failures and operational detail links.
- Added portfolio completion checks, next actions, reproduction commands, evidence hashes, and
  progressive-disclosure limitations.
- Added a prominent Overview entry point with runtime result count, reviewed-output count, best
  observed configuration, and an explicit production-readiness warning.
- Reorganized navigation into Core Evaluation, Discovery, and an active-route-aware collapsible
  Advanced Lab.

## Live evidence state

| Field | Observed value |
| --- | --- |
| Evaluation | `COMPLETE` |
| Gate | `NOT_EVALUATED` |
| Evidence trust | `needs_judge_review` |
| Production readiness | `not_production_ready` |
| Runtime configurations | 3 completed |
| Actual local-runtime Results | 384 |
| Critical failures | 110 |
| Reviewed model outputs | 0 |
| Gate outcomes | 0 of 3 |
| Portfolio checks | 6 of 8 passed |

The strongest observed configuration remains `medium-candidate`, using `qwen2.5:1.5b` and prompt
v1. It is a diagnostic winner, not a release candidate.

## Changed files

- `backend/app/api/v1/api.py`
- `backend/app/api/v1/routes/reference_workload.py`
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/reference_workload.py`
- `backend/app/services/evidence_trust.py`
- `backend/app/services/reference_workload_read_model.py`
- `backend/tests/test_reference_workload_read_model.py`
- `frontend/app/page.tsx`
- `frontend/app/reference-workload/page.tsx`
- `frontend/components/SidebarNav.tsx`
- `frontend/features/reference-workload/ConfigurationCharts.tsx`
- `frontend/features/reference-workload/ConfigurationComparison.tsx`
- `frontend/features/reference-workload/FailureReviewQueue.tsx`
- `frontend/features/reference-workload/GateEvidenceSummary.tsx`
- `frontend/features/reference-workload/ReferenceStatusStrip.tsx`
- `frontend/features/reference-workload/ReproductionPanel.tsx`
- `frontend/lib/api.ts`
- `frontend/tailwind.config.ts`
- `frontend/types/api.ts`
- `docs/reference_workload_aggregate_ui.md`
- `docs/reference_workload.md`
- `docs/project_status.md`
- `docs/reports/2026-09-01_model_atlas_sprint_6a_phase_4_aggregate_ui.md`

## Verification

```text
Docker backend pytest: 215 passed, 1 upstream deprecation warning
Docker backend Ruff: all checks passed
Frontend TypeScript: passed
Frontend ESLint: passed
Frontend Next.js 16.2.10 production build: passed
Docker backend/frontend image build: passed
Docker Compose configuration: passed
Alembic current: 202608040001 (head)
Live aggregate API: 3 configurations, 384 Results, 110 critical failures
Desktop browser: charts rendered, table overflow contained, document overflow 0
390px mobile browser: document overflow 0, mobile navigation and body lock passed
Advanced Lab: collapsed by default and expanded on active advanced route
Failure Run detail navigation: passed
Overview Reference Workload entry point: passed
Browser console: 0 warnings or errors
```

The warning is the existing upstream Starlette TestClient deprecation warning and does not affect
application behavior.

## Phase boundary

Phase 4 does not fabricate Gate outcomes or reports. `/report` and `/report.md` remain absent until
Phase 5 binds existing Gate evaluation and generated report artifacts to the selected stored
evidence. Model-output review, Gate evaluation, bounded module splitting, and final portfolio
verification remain open work.
