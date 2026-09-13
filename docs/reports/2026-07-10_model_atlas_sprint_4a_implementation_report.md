# Model Atlas Sprint 4A Implementation Report

Date: 2026-07-10

Status note: This report preserves the Sprint 4A completion state. Sprint 4B has since implemented
the recommended Tool Calling pack; see `2026-07-10_model_atlas_sprint_4b_implementation_report.md`.

## Implemented

- Central Evidence Trust classification for source provenance and score provenance.
- Trust-aware Gate snapshots, scorecards, Release Readiness, and frozen Release Decisions.
- A non-persisting Gate Preflight API and three-step Gate evaluation flow.
- A workflow-oriented control-plane Overview and Discover/Validate/Release/Audit navigation.
- Separate Gate Verdict, Evidence Trust, Release Readiness, and Production Readiness states.
- Decision-first Gate reports, Judge Review coverage, and progressive disclosure for raw evidence.
- Versioned adapter and scorer descriptors plus documented future extension contracts.
- Golden Demo and evaluator-facing documentation for deterministic and Ollama paths.

## Architecture Decisions

- Evidence Trust is a centralized domain service. Gate, Release, Judge Review, and Overview consume the same classification rules and threshold settings.
- Source trust and score trust are independent. Human review is score provenance, never a source type.
- `captured_local` is normalized to `local_authored`; only `production_captured` contributes production evidence.
- Existing JSON metadata and snapshot columns carry the new provenance. Sprint 4A does not require a database enum or trust table migration.
- Preflight reuses Gate evidence selection but never runs final policy evaluation or persists a `GateEvaluation`.
- Extension support stops at descriptors and contracts. Dynamic plugin loading and a marketplace remain out of scope.

## Files Added

Backend domain and API:

- `backend/app/services/evidence_trust.py`
- `backend/app/services/control_plane_overview.py`
- `backend/app/services/deployment_gate/preflight.py`
- `backend/app/schemas/evidence_trust.py`
- `backend/app/schemas/gate_preflight.py`

Backend tests:

- `backend/tests/test_evidence_trust.py`
- `backend/tests/test_gate_preflight.py`
- `backend/tests/test_control_plane_overview.py`

Frontend components:

- `frontend/components/AppShell.tsx`
- `frontend/components/SidebarNav.tsx`
- `frontend/components/MobileNav.tsx`
- `frontend/components/WorkflowStepper.tsx`
- `frontend/components/StatusSummaryGrid.tsx`
- `frontend/components/NextActions.tsx`
- `frontend/components/EvidenceTrustPanel.tsx`
- `frontend/components/GatePreflightPanel.tsx`
- `frontend/components/DecisionExplanation.tsx`
- `frontend/components/DisclosurePanel.tsx`

Documentation:

- `docs/extension_contracts.md`
- `docs/golden_demo.md`
- `docs/reports/2026-07-10_model_atlas_sprint_4a_evaluator_guide.md`
- `docs/reports/2026-07-10_model_atlas_sprint_4a_implementation_report.md`

## Files Modified

- Backend settings, benchmark execution, inference adapters, scorer registry, Gate evidence/policy/evaluator/reporting, Release Readiness/Decision, Judge Review, analytics schemas/routes, and seed defaults.
- Frontend API types/client, status presentation, layout/navigation, Overview, Gate creation/detail, Release Readiness/Decision detail, Judge Review, benchmark execution, and global focus styling.
- `README.md`, `SUBMISSION_README.md`, `.env.example`, `docker-compose.yml`, and the architecture, data-contract, deployment-gate, and project-status documents.

## API Changes

- Added `POST /api/v1/deployment-gates/preflight`.
- Added `GET /api/v1/analytics/control-plane-overview`.
- Added Evidence Trust, implementation provenance, and structured decision explanation fields to Gate responses.
- Added Evidence Trust and Production Readiness to Release Readiness and frozen Release Decision snapshots.
- Added heuristic, candidate, applied, human-reviewed, and critical-review coverage fields to Judge Review summaries.

All additions preserve the existing route paths. The legacy `GET /api/v1/analytics/overview` endpoint remains available.

## Compatibility Notes

- New response fields are additive.
- Existing snapshot keys are retained; new Gate snapshots use `gate-evidence-snapshot-v2`.
- Legacy source value `captured_local` remains readable through centralized normalization.
- Legacy snapshots without trust metadata render an explicit fallback instead of failing.
- Canonical JSON hashing is retained. New snapshot fields intentionally produce a new decision hash.
- Release snapshot diff now reports trust changes after judge-label application while preserving the frozen decision state.

## Tests Added

- Source-tier mapping and score-tier priority coverage.
- Synthetic-only, judge-review-needed, local-demo-ready, and production-evidence-ready transitions.
- Gate snapshot schema/provenance/trust assertions and structured decision explanations.
- Preflight evidence counts, critical cases, baseline precedence, invalid inputs, and non-persistence.
- Release Readiness trust mappings, production readiness, frozen snapshots, and trust diff behavior.
- Control-plane Overview latest state, prioritized actions, counts, and empty-state behavior.

## Verification Results

```text
Backend pytest: 84 passed, 1 upstream deprecation warning
Backend Ruff: passed
Frontend typecheck: passed
Frontend ESLint: passed
Frontend production build: passed
Docker Compose configuration validation: passed
```

The warning comes from Starlette TestClient's current `httpx` compatibility shim. Live Docker service health was not re-run from this sandbox because Docker named-pipe access was unavailable; Compose structure itself validated successfully.

## Manual UX Verification

- Desktop Overview at 1440 x 1000: fixed workflow navigation, status hierarchy, next actions, and inventory sections rendered without horizontal overflow or clipped visible elements.
- Mobile Overview at 390 x 844: desktop sidebar collapsed, workflow remained visible, tables stayed inside their overflow container, and the page had no body-level horizontal overflow.
- Mobile navigation drawer opened with an accessible expanded state, visible close control, and background scroll lock.
- Production build generated all Gate, Release, Judge Review, Overview, and Audit routes successfully.
- A final repeat of local-browser navigation was blocked by the host browser policy, so the last Gate and Release screen pass is supported by the earlier visual checks plus type, lint, and production-build verification.

## Known Limitations

- Bundled data is synthetic or locally authored and cannot establish production readiness.
- Heuristic scoring is deterministic but still requires calibrated judge or explicit human review.
- Production Readiness is an evidence-policy interpretation, not an infrastructure deployment action.
- Trusted identity headers are an integration boundary, not full SSO/OIDC.
- Snapshot diff is structural rather than domain-semantic.
- Executable tool workflows, RAG, runtime stress testing, and production monitoring remain out of scope.

## Recommended Next Sprint

Sprint 4B should add an executable Tool Calling Evaluation Pack through the existing extension and governance contracts: tool selection correctness, argument schema validation, real execution outcomes, failure and retry behavior, recovery, multi-step sequences, and tool-specific acceptance policies.
