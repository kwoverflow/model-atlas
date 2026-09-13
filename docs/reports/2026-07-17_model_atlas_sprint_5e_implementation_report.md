# Model Atlas Sprint 5E Implementation Report

Date: 2026-07-17

## Executive Summary

Sprint 5E completes the five production-hardening items planned after Sprint 5D:

1. OIDC discovery, JWKS rotation, and asymmetric JWT verification;
2. worker heartbeat, queue observability, dead-letter, and requeue operations;
3. a signed reference traffic collector with replay protection;
4. stale release-decision operational actions, revocation, and replacement lineage;
5. durable real local-model validation campaigns and evidence reports.

The implementation preserves the central Model Atlas separation:

```text
candidate ranking != runtime validation != Gate approval != release authorization
```

No component added in this sprint can directly authorize a release.

## 1. OIDC And JWKS

### Implemented

- strict `HS256` and `RS256` algorithm allowlist;
- OpenID Connect discovery document loading;
- direct JWKS URI configuration;
- HTTPS-by-default provider URLs;
- bounded HTTP timeouts and response sizes;
- persistent discovery and JWKS caches;
- unknown-`kid` forced refresh for signing-key rotation;
- issuer, audience, `exp`, `nbf`, and `iat` validation;
- legacy static HS256 compatibility;
- middleware-level verifier reuse.

### Main files

- `backend/app/services/operator_identity.py`
- `backend/app/middleware/operator_identity.py`
- `backend/app/core/config.py`
- `backend/tests/test_operator_identity_jwt.py`

### Boundary

The verifier is production-shaped, but the repository does not bundle an identity-provider server
or browser login flow.

## 2. Worker Operations

### Implemented

- job heartbeat timestamps and counts;
- renewable leases for long-running work;
- worker registration, current-job state, and last-seen timestamps;
- online/offline/stopped worker interpretation;
- queue depth, lease, retry, latency, duration, success, and failure summaries;
- terminal dead-letter metadata;
- verified-role manual requeue with an audit identity snapshot;
- Agent Jobs UI with worker and traffic-source views.

### Main files

- `backend/app/services/agent_jobs.py`
- `backend/app/workers/agent_control_worker.py`
- `backend/app/models/entities.py`
- `frontend/app/agent-jobs/page.tsx`
- `frontend/components/AgentJobTable.tsx`

### Migration

`202607170001_worker_operations`

## 3. Traffic Collector

### Implemented

- `hmac-sha256-v2` signature over source, key ID, nonce, sent time, and normalized batch;
- active and retiring key IDs;
- clock-skew validation;
- gzip request support with compressed and decompressed size bounds;
- source/batch and source/nonce replay protection;
- exact retry idempotency;
- signature conflict rejection;
- traffic receipt and source-health persistence;
- reference collector with outbox, stable retry identity, exponential retry, and status state;
- optional Compose `collector` profile.

### Main files

- `backend/app/services/agent_traffic_ingestion.py`
- `backend/app/collectors/agent_traffic_collector.py`
- `backend/app/api/v1/routes/agent_execution.py`
- `backend/tests/test_agent_evidence_import.py`

### Migration

`202607170002_traffic_collector`

### Boundary

The reference collector is an HTTP outbox client. Kafka, streaming retention, and fleet-wide
telemetry management remain outside the MVP.

## 4. Release Operations

### Implemented

- append-only `ReleaseDecisionAction` records;
- automatic `stale_detected` action when Gate evidence becomes stale;
- manual `review_requested`, `acknowledged`, and `revoked` actions;
- verified role checks for review and revocation;
- replacement release-decision links;
- operational states: recorded, active, needs review, revoked, and replaced;
- Release Decision detail timeline and controls;
- operational status on the decision list.

### Main files

- `backend/app/services/release_decisions.py`
- `backend/app/services/deployment_gate/staleness.py`
- `backend/app/api/v1/routes/release_decisions.py`
- `frontend/components/ReleaseDecisionOperations.tsx`

### Migration

`202607170003_release_operations`

### Boundary

Operational revocation changes release-control state; it does not delete or rewrite the historical
signed decision.

## 5. Local Model Validation

### Implemented

- durable `model_validation_campaign` job type;
- verified maintenance-role campaign creation;
- existing benchmark engine reuse;
- raw credential rejection and environment-only API key reference;
- JSON and Markdown reports;
- source-specific evidence cohorts and comparisons;
- quality, correctness, latency, throughput, error, OOM, and review metrics;
- canonical Evidence Trust reuse;
- candidate judge-label calibration;
- configured artifact versus observed runtime model-size check;
- CLI report export;
- `/model-validation` UI with job polling and report visualization;
- Ollama Compose profile and model pull helper.

### Main files

- `backend/app/services/model_validation.py`
- `backend/app/api/v1/routes/model_validation.py`
- `backend/app/validation/local_model_validation.py`
- `frontend/components/ModelValidationConsole.tsx`
- `frontend/app/model-validation/page.tsx`
- `docs/model_validation.md`

### Migration

`202607170004_model_validation`

## Actual Runtime Evidence

The final verification used Ollama and the actual `qwen2.5:0.5b` model:

```text
job: e3d43db3-5ba8-41b7-aa7a-0dd8fdd11e66
run: 0ceff4b9-3b82-474c-a206-629d3fa9c44e
new results: 5
new metrics: 5
attempts: 1
job status: completed
```

Focus-cohort measurements:

| Metric | Value |
| --- | ---: |
| Average heuristic quality | 1.0000 |
| JSON validity | 1.0000 |
| P50 latency | 1,944.428 ms |
| P95 latency | 2,817.942 ms |
| P50 throughput | 72.24 tokens/s |
| Error rate | 0 |
| OOM rate | 0 |

The report is `needs_attention`, not `validated`, because the configured deployment artifact is
`qwen2.5-7b-instruct-int4` while the observed runtime model is `qwen2.5:0.5b`, and judge-review
coverage is zero. This is the intended fail-honest behavior.

Generated reports:

- `artifacts/model-validation/2026-07-17_qwen2.5-0.5b_0ceff4b9.json`
- `artifacts/model-validation/2026-07-17_qwen2.5-0.5b_0ceff4b9.md`

The model weights remain in the Docker volume and are not part of the repository.

## API Additions

| Method | Path |
| --- | --- |
| `GET` | `/api/v1/agents/jobs/overview` |
| `POST` | `/api/v1/agents/jobs/{job_id}/requeue` |
| `GET` | `/api/v1/agents/evidence/traffic-sources` |
| `GET` | `/api/v1/release-decisions/{id}/actions` |
| `POST` | `/api/v1/release-decisions/{id}/actions` |
| `POST` | `/api/v1/model-validation/campaigns` |
| `GET` | `/api/v1/model-validation/report` |
| `GET` | `/api/v1/model-validation/report.md` |

## Verification

```text
Backend local pytest: 151 passed, 1 upstream warning
Backend container pytest: 151 passed, 1 upstream warning
Backend Ruff: passed
Frontend typecheck: passed
Frontend ESLint: passed
Frontend production build: passed
Frontend container ESLint: passed
Alembic: 202607170004 (head)
Docker Compose: db/backend/frontend/agent-worker running
API health: ok
Online workers: 1
Model Validation page: HTTP 200
Ollama model: qwen2.5:0.5b, 397 MB
Actual validation job: completed on first attempt
```

The only warning is an upstream Starlette TestClient deprecation notice.

## Runtime URLs

Windows reserved port ranges prevented host port `8000`, so Compose now maps:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:18000`
- OpenAPI: `http://localhost:18000/docs`

The backend container still listens on port `8000`; only the host mapping changed.

## Residual Risks

- No bundled IdP or end-user browser SSO flow.
- JWKS uses in-process cache rather than a shared multi-replica cache.
- The durable worker is not a general distributed workflow engine.
- Collector delivery is HTTP/outbox, not streaming infrastructure.
- Model identity uses a parameter-size name check until digest attestation is available.
- Actual evidence still requires reviewed labels and target-artifact execution.
- No Kubernetes, production alert manager, model registry attestation, or live GPU agent.

## Recommended Sprint 5F

1. Add model digest/manifest attestation and create a configuration matching the observed 0.5B
   runtime.
2. Run the configured 7B artifact or update the deployment scope before Gate evaluation.
3. Import and review judge labels, prioritizing critical cases.
4. Add browser OIDC login/session integration and production IdP deployment examples.
5. Export worker, collector, and release-operation metrics to a monitoring backend with alerts.
