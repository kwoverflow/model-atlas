# Reference Workload Aggregate API and Guided UI

## Purpose

Sprint 6A Phase 4 and Phase 5 turn the stored Korean Operator Assistant evaluation evidence into one
reviewable operational surface. The page is designed for an evaluator who needs to determine:

1. what workload and source material were evaluated;
2. which concrete model, runtime, prompt, and context configurations actually ran;
3. how those configurations compare;
4. which critical cases failed and where to inspect them;
5. whether Gate, evidence-trust, release, and production states are complete;
6. how to reproduce the evidence.

Open the page at `http://localhost:3000/reference-workload` while the backend and frontend Compose
services are running.

## Read model

`backend/app/services/reference_workload_read_model.py` is a read-only composition layer. It does
not create evaluation evidence or change Gate state. Every request:

- validates the locked source manifest, deterministic corpus, approved case pack, and runtime
  matrix from repository-owned files;
- resolves the bootstrapped workload and current evaluation suite from PostgreSQL;
- selects the latest completed `local_actual_runtime` run for each current runtime-matrix entry;
- ignores historical runs whose configuration names are no longer in the matrix;
- calculates comparison metrics from the exact selected Result and Inference Metric rows;
- builds the critical-failure queue from the same selected runs;
- calculates source-case coverage and model-output review coverage independently;
- reads the latest Gate for each selected configuration without creating one;
- derives evidence trust and production readiness with the existing trust services.

`local_actual_runtime` remains the raw persisted source label. For evidence-trust interpretation it
maps to the canonical `local_authored` tier. This prevents actual local evidence from being
misclassified as unknown while preserving the original source provenance.

## API

All routes are under `/api/v1/reference-workload`.

| Route | Purpose |
| --- | --- |
| `GET /overview` | Complete evaluator-oriented aggregate response |
| `GET /cases` | Source-case contracts, source-review state, and selected result coverage |
| `GET /configurations` | Current runtime matrix with latest stored run summaries |
| `GET /comparison` | Metric rows and deterministic comparison hash |
| `GET /failures?limit=100&offset=0` | Paginated critical-failure review queue |
| `GET /report` | Structured report bound to selected stored evidence and Gate outcomes |
| `GET /report.md` | Markdown rendered from the structured report object |

Invalid file contracts return HTTP `409` instead of silently displaying partial or stale evidence.
Missing database evidence is represented as `not_run`, `INCOMPLETE`, or `NOT_EVALUATED`; the
file-backed source definition remains visible.

The report routes do not mutate evidence. Gate creation remains in the existing Deployment Gate
service and the explicit `reference-gate` command.

## Status semantics

The UI keeps four states in a dedicated strip:

- **Evaluation**: whether every enabled current matrix entry has a selected completed run with the
  expected case and trial coverage.
- **Gate**: the aggregate of stored Gate outcomes. No Gate is synthesized by this page.
- **Evidence Trust**: provenance and human-review interpretation of the selected Result rows.
- **Production Readiness**: requires verified production-captured evidence and is independent of a
  local policy verdict.

Source-case approval is also separate. The current 64 approved source contracts establish the
evaluation definition; they do not count as review of 384 model outputs.

## UI flow

The page follows this order:

1. workload identity and version;
2. four-state status strip;
3. source and output coverage;
4. two comparison charts and the full configuration table;
5. critical failures with links to Benchmark Run, Judge Review, and Gate detail;
6. Gate outcomes, evidence trust, and portfolio completion checks;
7. reproduction commands and next actions;
8. collapsed limitations, hashes, and source paths.

Wide tables scroll inside their own containers. The desktop sidebar groups primary workflows under
Core Evaluation and Discovery. Advanced Lab remains collapsed unless the user opens it or visits
an advanced route. The same behavior is available in the mobile drawer.

## Current stored evidence

Recorded on 2026-09-01:

| Item | Value |
| --- | ---: |
| Approved source cases | 64 |
| Approved critical source cases | 20 |
| Completed runtime configurations | 3 |
| Actual local-runtime Results | 384 |
| Distinct observed model artifacts | 2 |
| Minimum trials per case | 2 |
| Critical failures in review queue | 110 |
| Human-reviewed model outputs | 0 |
| Stored Gate outcomes | 3 of 3, all `BLOCKED` |

The portfolio checklist passes 7 of 8 checks. Model-output review remains open. Evidence trust is
`needs_judge_review`; release readiness is `BLOCKED`; production readiness is
`not_production_ready`.

## Operator verification

```powershell
docker compose up -d --build backend frontend
Invoke-RestMethod http://localhost:18000/api/v1/reference-workload/overview
Invoke-RestMethod http://localhost:18000/api/v1/reference-workload/failures?limit=10
Invoke-RestMethod http://localhost:18000/api/v1/reference-workload/report
make reference-gate
make reference-report
```

The frontend is available at `http://localhost:3000/reference-workload`. The host backend port is
`18000`; service-to-service traffic uses the Compose backend name and container port `8000`.

## Known boundaries

- The selected evidence is actual local-runtime evidence, not production-captured evidence.
- The tested 0.5B and 1.5B models fail many RAG, Tool, and Agent contracts.
- Model-output review is 0 of the Phase 4 target of 30.
- All three current Gate outcomes are `BLOCKED` by the local acceptance policy.
- The deterministic lexical retriever is not a production vector-search service.
- Phase 6 completed behavior-preserving entity, service, and frontend API-type modularization
  without changing these API contracts.

Phase 7 final portfolio verification reran the real smoke flow, isolated smoke and portfolio
configuration identity, replayed the exact persisted portfolio runs, regenerated and hash-verified
the artifacts, and passed the full test/build/browser surface. The next implementation unit is
model-quality and review-evidence remediation; release and production-readiness claims remain
blocked.
