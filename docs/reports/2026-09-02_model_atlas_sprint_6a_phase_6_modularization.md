# Model Atlas Sprint 6A Phase 6 Bounded Modularization

Recorded: 2026-09-02

## Executive result

Sprint 6A Phase 6 is complete. Four concentrated implementation surfaces were converted into
bounded packages without adding product capability, changing API routes, changing database schema,
or upgrading any evidence or release-readiness claim.

The refactor preserves the 47-table SQLAlchemy metadata contract, all existing top-level model and
service imports, all 142 frontend API type exports, Agent execution semantics, operational
reliability endpoint behavior, and the existing Alembic revision history.

## Delivered structure

### SQLAlchemy entities

`backend/app/models/entities.py` is now a compatibility facade. Primary ownership is split across:

| Module | Ownership |
| --- | --- |
| `base.py` | GUID, UTC datetime, declarative base, timestamp mixin |
| `identity.py` | OIDC sessions, cache, and lifecycle events |
| `operations.py` | metric snapshots, SLOs, incidents, actions, and deliveries |
| `catalog.py` | hardware, logical models, artifacts, and artifact attestations |
| `trust.py` | supply-chain, trust roots/sources, transparency, and production receipts |
| `evaluation.py` | tasks, runs, results, workloads, suites, policies, Gates, and baselines |
| `agent.py` | checkpoints, durable jobs, workers, and traffic receipts |
| `release.py` | release decisions and operational actions |

`app.models`, `app.models.entities`, and `app.db.base` resolve the same declarative classes and
`Base.metadata`. Timestamp listener registration remains centralized in `app.models`.

### Agent execution

`app.services.agent_execution` is now a compatibility package with bounded modules for contracts,
planning, callbacks, checkpoints, steps, execution, recovery, trace construction, evidence,
semantic comparison, replay, approval projection, presentation, and utilities.

The public import path remains unchanged. The canonical four-step Agent fixture produced the same
semantic trace SHA-256 before and after the split:

```text
c21f106d5f1da8d2e6bd768ccd815368ee8d8278d75550e83616a4dcaf052fb6
```

The trace, context, runtime, recovery, observation, approval, summary, and live-replan version
constants are unchanged.

### Operational reliability

`app.services.operational_reliability` now owns separate snapshot, SLO, burn-rate, incident,
escalation, paging, readiness, read-model, permission, command, overview, contract, and utility
modules. Existing routes, durable jobs, and tests continue to import from the package facade.

The live rebuilt service returned `200` for health, the operational reliability overview, and the
frontend Operations page. The overview retained RBAC policy
`operational-reliability-rbac-v2` and the existing staging-readiness contract.

### Frontend API types

The former `frontend/types/api.ts` implementation is replaced by `frontend/types/api/index.ts` and
nine domain modules: common, catalog, evaluation, gate, release, agent, identity, trust, and
operations. Existing `@/types/api` imports resolve through the barrel without caller changes.

## Compatibility evidence

| Contract | Result |
| --- | --- |
| SQLAlchemy table count | 47 application tables before and after |
| SQLAlchemy metadata signature | `fba1f807c636ea5c4178db7b391a2300dbd6743118d5c989e23592d23a115c6a` before and after |
| Empty-schema Alembic upgrade | Passed through head `202608040001` |
| Empty-schema physical table count | 48, including `alembic_version` |
| Agent semantic trace hash | Exact pre/post match |
| Agent targeted tests | 22 passed |
| Operational reliability targeted tests | 23 passed |
| Backend full suite | 219 passed |
| Backend Ruff | Passed |
| Frontend ESLint | Passed |
| Frontend TypeScript/Next.js build | Passed |
| Backend, worker, and frontend Docker builds | Passed |

The test count increased from Phase 5 because model-module compatibility and metadata-contract
checks are now explicit regression tests.

## Alembic note

The clean-database upgrade proves that every historical revision still applies with the split
model package. An exact pre/post metadata signature test additionally proves that the refactor did
not change tables, columns, keys, indexes, relationships, or constraints represented by the ORM.

`alembic check` is not currently clean because the repository already has historical
autogenerate-name differences between migration-created indexes/unique constraints and ORM naming.
This pre-existing naming debt is outside the behavior-preserving Phase 6 scope. No rename/drop
migration was generated or applied, and the metadata signature did not change.

## Deliberately unchanged

- No database migration or schema rename was introduced.
- No Agent action, tool, recovery branch, checkpoint mode, or memory capability was added.
- No operational paging, SLO, escalation, readiness, or RBAC behavior was changed.
- No frontend workflow or visible design was changed.
- Gate outcomes remain three of three `BLOCKED`.
- Model-output review remains the only failing portfolio-completion check.
- Local actual-runtime evidence remains non-production evidence.

## Next phase

Phase 7 is final portfolio verification: rerun the reference smoke path, verify the persisted
runtime matrix and report artifacts, run all tests and builds, and publish only actual evidence.
The final package must continue to list the missing 30-output review target and production evidence
without upgrading readiness claims.
