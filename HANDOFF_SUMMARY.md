# Model Atlas Handoff Summary

Updated: 2026-08-04, Sprint 5H-H

## Project Scope

Model Atlas is a local-first EvalOps control plane. It separates model candidate discovery from
deployment authorization, executes versioned workload evidence through local adapters, evaluates a
concrete deployment configuration against acceptance policy, and preserves an auditable release
decision.

The current implementation supports deterministic fixtures, OpenAI-compatible local runtimes,
Evidence Trust, Gate Preflight, baseline and regression controls, judge review, release readiness,
signed release decisions, lineage, and executable local Tool Calling evaluation.
It also includes deterministic RAG retrieval, citation, groundedness, and unsupported-claim
evaluation plus repeated-trial runtime reliability, timeout/OOM evidence, and runtime comparison.
It now also includes plan-first Agent execution, operational-memory provenance, authenticated
persistent checkpoints, observation-driven bounded recovery, resumable result revisions, metered
live-replan callbacks, production Agent evidence import, Agent Gate metrics, and semantic replay.
Sprint 5D adds append-only child revisions, durable worker jobs, automatic Gate staleness,
JWT/trusted-proxy hardening, production-shaped live replanning, and signed traffic ingestion.
Sprint 5E adds OIDC discovery/JWKS rotation, worker heartbeat/dead-letter operations, the reference
traffic collector, stale release-decision actions, and durable real local-model validation reports.
Sprint 5F adds server-observed artifact digests, matching immutable runtime configurations,
append-only reviewed judge decisions, browser OIDC PKCE sessions, Prometheus metrics/alerts, and
Tool/RAG isolation preflight plus deployment examples.
Sprint 5G adds configured-JWKS JWS verification, in-toto-style model provenance, CycloneDX SBOM
binding, separated append-only revocation, and signed receipts required for production-captured
evidence to satisfy production thresholds.
Sprint 5H-A adds a purpose-scoped public-key trust registry, append-only key lifecycle, signed
transparency checkpoints, Merkle inclusion verification, and dynamic production eligibility.
Sprint 5H-B adds allowlisted remote JWKS sources, Preview/Apply receipts, atomic public-key import,
source lineage, freshness-aware fail-closed eligibility, health metrics, and operator UX.
Sprint 5H-C adds PostgreSQL-backed opaque browser sessions, hash-only CSRF state, encrypted
provider logout hints, exact Origin enforcement, RP-initiated logout, untrusted-forwarded-header
rejection, and shared discovery/JWKS caching for API replicas.
Sprint 5H-D adds PostgreSQL-backed trust-source policies, replica-safe enqueue leases, durable
execution leases, deterministic interval jitter and retry, per-attempt sync receipts, dead-letter
handling, scheduling metrics, and automation controls in the Trust Registry UI.
Sprint 5H-E adds verified-role browser-session audit and scoped containment, provider-token
minimization, hash-linked lifecycle events, replica-deduplicated durable retention cleanup,
identity metrics/alerts, and the Browser Sessions operator console.
Sprint 5H-F adds durable interval metric history, missing-interval-aware identity/worker SLOs,
open/resolved incident history, HMAC-signed paging through durable jobs, delivery receipts,
outage/dead-letter/requeue recovery, and the expanded Operations console.
Sprint 5H-G adds paired long/short burn rates, verified acknowledgement and assignment, hash-linked
response history, automatic escalation, delivery-pinned HMAC key identity, private-CA-verified
HTTPS paging, and incident-response controls in the Operations console.
Sprint 5H-H adds bounded runtime secret projection, no-restart HMAC rotation, strict provider
receipt correlation, persisted provider evidence, seven-check staging readiness, and executable
qualification and outage-recovery drills.

## Completed Work

- Model, artifact, hardware, benchmark, workload, policy, and deployment configuration records.
- Candidate Discovery with filters, weighted scoring, evidence confidence, and Pareto ranking.
- Mock and OpenAI-compatible benchmark execution with result, metric, and log persistence.
- Deterministic JSON, grounded-reference, text, and executable tool scorers.
- Deployment Gate, active baseline promotion, critical-case blocking, and reports.
- Judge-label import/review, prompt regression, experiment lineage, and release governance.
- Evidence Trust source/score separation and production-readiness interpretation.
- Non-persisting Gate Preflight and workflow-oriented control-plane Overview.
- Discover / Validate / Release / Audit application navigation.
- Versioned local Tool Registry, argument and output validation, actual handler execution, retry
  recovery, multi-step traces, Tool Calling metrics, and a dedicated policy pack.
- Versioned RAG corpus/retriever, sanitized pre-generation retrieval, citation/claim traces, RAG
  metrics, and a dedicated policy pack.
- Repeated trials, detached concurrent adapter snapshots, timeout/OOM capture, latency/variance and
  context-stress metrics, Runtime A/B comparison, and a dedicated reliability policy pack.
- Bounded Agent plans, memory/retrieval/tool/response actions, task-local memory writes, retry
  recovery, Agent metrics/policy, trace UI, and semantic replay.
- Versioned observations, one-shot recovery branches, guarded actions, external human checkpoint
  decisions, decision hashes, Adaptive Agent Gate metrics, and a dedicated 5B policy pack.
- Verified role-scoped approvers, separation of duties, durable checkpoint transitions, expiry,
  revocation, resume, optimistic versions, and transition hashes.
- One-call live-replan provider boundary with token, latency, cost, model, and response-hash
  evidence.
- Verified production-captured Agent trace import contract with source integrity and duplicate
  rejection.
- Append-only parent/root execution lineage with evidence revision hashes and latest-revision Gate
  aggregation.
- PostgreSQL-backed resume, reconciliation, and traffic jobs with dedupe, leases, retry, and lease
  recovery.
- Gate evidence snapshot v8, automatic stale/readiness blocking, and superseding Gate links.
- Strict HS256 bearer verification and trusted proxy exact-host/CIDR enforcement.
- OpenAI-compatible one-shot live-replan provider with recorded, network-free semantic replay.
- HMAC-signed production traffic batches with verified machine identity and atomic import.
- RS256 OIDC discovery/JWKS verification with cache refresh on signing-key rotation.
- Worker registration, heartbeats, queue latency/duration summaries, dead letters, and audited
  requeue.
- HMAC v2 collector receipts with nonce replay protection, gzip bounds, key rotation, and source
  health.
- Release review, acknowledgement, revocation, and replacement action history.
- Durable model-validation campaigns, source cohorts, judge calibration, model identity checks,
  JSON/Markdown export, CLI, and dedicated UI.
- Verified Ollama artifact manifests and SHA-256 attestations with SSRF bounds, actor provenance,
  idempotent storage, and digest-pinned deployment configurations.
- Verified human judge review decisions with RBAC, separation of duties, immutable prior/applied
  score snapshots, rationale, and stable review hashes.
- Browser Authorization Code + PKCE, state/nonce checks, RS256 ID-token verification, HttpOnly
  application sessions, navigation identity controls, and a Keycloak development profile.
- Operational JSON and Prometheus metrics, derived alerts, Operations UI, Prometheus/Alertmanager
  examples, and a reference alert sink.
- Tool/RAG isolation policy registry, fail-closed execution preflight, persisted audit details,
  isolation UI, and hardened Docker examples.
- Publisher-signed model supply-chain attestations bound to the observed artifact, runtime
  manifest, runtime attestation, and canonical CycloneDX SBOM digest.
- Append-only supply-chain revocations with verifier/revoker separation of duties.
- Signed production capture receipts with replay protection, exact run/result/metric validation,
  and trust removal when linked provenance is revoked.
- Model Validation report v4, Supply Chain and Trust Registry UIs, and operational metrics for
  managed, transparent, eligible, revoked, and development-only evidence states.
- Public-JWK-only trust roots with validity windows, purpose isolation, idempotent rotation,
  retirement, and registrar-separated revocation.
- RFC 6962-style inclusion proof verification with signed checkpoints and replay protection.
- HTTPS-by-default remote JWKS sources with host, redirect, content, time, and payload bounds.
- Non-mutating Preview and atomic Apply with append-only success/failure receipts.
- Source-backed root lineage, snapshot-aware rotation, freshness status, metrics, alerts, and UI.
- Durable interval policies with `SKIP LOCKED` due scans, one enqueue per schedule window, and
  lease recovery across worker replicas.
- Scheduled Apply lineage through policy, job, attempt, and sync receipt identifiers, with
  authenticated Run now and no raw schedule lease secret persisted in job payloads.
- Browser-session audit for verified Admin, SRE Lead, and ML Ops Lead identities, with mutation
  restricted to Admin and SRE Lead.
- Single, subject, and provider-session-hash revocation with current-session preservation.
- Provider token and raw `sid` purge on revocation or inactive-session cleanup.
- Keyed client fingerprints and provider-session hashes without raw client descriptors.
- Hash-linked issuance, migration, revocation, purge, and retention-deletion events that survive
  session-row deletion.
- Replica-deduplicated `oidc_session_cleanup` jobs with bounded `SKIP LOCKED` retention passes.

## Main Sprint 4 Through 5H-F APIs

- `GET /api/v1/benchmark-executions/tool-registry`
- `POST /api/v1/benchmark-executions`
- `GET /api/v1/benchmark-executions/{benchmark_run_id}`
- `GET /api/v1/benchmark-executions/{benchmark_run_id}/logs`
- `GET /api/v1/rag/corpora`
- `GET /api/v1/rag/retriever`
- `GET /api/v1/runtime-reliability/compare`
- `GET /api/v1/agents/runtime`
- `GET /api/v1/agents/memory-registry`
- `POST /api/v1/agents/replay/{benchmark_result_id}`
- `GET /api/v1/agents/checkpoints`
- `POST /api/v1/agents/checkpoints/{checkpoint_record_id}/decision`
- `POST /api/v1/agents/checkpoints/{checkpoint_record_id}/revoke`
- `POST /api/v1/agents/checkpoints/{checkpoint_record_id}/resume`
- `POST /api/v1/agents/checkpoints/{checkpoint_record_id}/resume-jobs`
- `POST /api/v1/agents/jobs/reconciliation`
- `GET /api/v1/agents/jobs`
- `GET /api/v1/agents/jobs/{job_id}`
- `GET /api/v1/agents/jobs/overview`
- `POST /api/v1/agents/jobs/{job_id}/requeue`
- `POST /api/v1/agents/evidence/import`
- `POST /api/v1/agents/evidence/traffic-batches`
- `GET /api/v1/agents/evidence/traffic-sources`
- `POST /api/v1/model-validation/campaigns`
- `POST /api/v1/model-validation/observed-runtime-configurations`
- `GET /api/v1/model-validation/artifact-attestations`
- `GET /api/v1/model-validation/report`
- `GET /api/v1/model-validation/report.md`
- `GET /api/v1/supply-chain/overview`
- `GET /api/v1/supply-chain/model-attestations`
- `POST /api/v1/supply-chain/model-attestations`
- `POST /api/v1/supply-chain/model-attestations/{id}/revocations`
- `GET /api/v1/supply-chain/production-receipts`
- `POST /api/v1/supply-chain/production-receipts`
- `GET /api/v1/trust-registry/overview`
- `GET|POST /api/v1/trust-registry/roots`
- `GET|POST /api/v1/trust-registry/sources`
- `POST /api/v1/trust-registry/sources/{id}/sync`
- `GET /api/v1/trust-registry/source-syncs`
- `GET /api/v1/trust-registry/source-schedules`
- `PUT /api/v1/trust-registry/sources/{id}/schedule`
- `POST /api/v1/trust-registry/sources/{id}/schedule/run`
- `POST /api/v1/trust-registry/roots/{id}/actions`
- `GET|POST /api/v1/trust-registry/transparency-proofs`
- `GET /api/v1/judge-labels/review-decisions`
- `POST /api/v1/judge-labels/review-decisions`
- `GET /api/v1/operator-identity/browser-config`
- `GET /api/v1/operator-identity/login`
- `GET /api/v1/operator-identity/callback`
- `POST /api/v1/operator-identity/logout`
- `GET /api/v1/operator-identity/sessions/overview`
- `GET /api/v1/operator-identity/sessions`
- `GET /api/v1/operator-identity/session-events`
- `POST /api/v1/operator-identity/sessions/{session_id}/revoke`
- `POST /api/v1/operator-identity/subjects/{subject_id}/sessions/revoke`
- `POST /api/v1/operator-identity/provider-sessions/{provider_session_hash}/revoke`
- `POST /api/v1/operator-identity/sessions/cleanup`
- `GET /api/v1/operations/metrics`
- `GET /api/v1/operations/alerts`
- `GET /api/v1/operations/reliability`
- `POST /api/v1/operations/reliability/cycles`
- `POST /api/v1/operations/reliability/test-pages`
- `GET /api/v1/isolation/policies`
- `POST /api/v1/isolation/preflight`
- `POST /api/v1/deployment-gates/preflight`
- `POST /api/v1/deployment-gates/evaluations`
- `GET /api/v1/release-readiness/snapshot`
- `POST /api/v1/release-decisions`
- `GET /api/v1/release-decisions/{id}/actions`
- `POST /api/v1/release-decisions/{id}/actions`
- `GET /api/v1/experiment-lineage/report`

## Run Locally

```bash
make up
make seed
make seed-tool-calling
make seed-rag
make seed-reliability
make seed-agent
make seed-agent-adaptive
```

Optional captured local suite:

```bash
docker compose run --rm backend python -m app.seed.captured_local
```

Development-only signed supply-chain bundle:

```bash
make supply-chain-demo
make trust-registry-demo
```

Development-only remote JWKS fixture:

```bash
make trust-source-up
```

Services:

- Frontend: http://localhost:3000
- Backend API: http://localhost:18000
- OpenAPI: http://localhost:18000/docs
- PostgreSQL: localhost:55432 by default (`POSTGRES_HOST_PORT` is configurable)

## Verification

```text
Backend pytest: 186 passed, 1 upstream deprecation warning
Backend and tools Ruff: passed
Frontend ESLint: passed
Frontend typecheck: passed
Frontend production build: passed
Docker Compose build/configuration and migration 202608040001: passed
Backend, 2 Agent workers, HTTPS paging sink, and trust-source fixture healthy
TLS and paging secret initializers: exit 0
Staging readiness: 7 passed, 0 failed
No-restart rotation to 2026-08-04-rotated: passed
Strict provider schema/event/receipt correlation and persistence: passed
Controlled outage, dead letter, SRE requeue, same-job recovery, and incident reconciliation: passed
Final operations health healthy; open incidents 0; dead letters 0
Recovered trust-source backlog: 26 failed jobs requeued; 3 incidents resolved
Migrated historical paging rows remain readable with key ID legacy
Verified acknowledgement and assignment action hash chain: passed
Desktop and 390px mobile 5H-H Operations QA: no document overflow or clipped controls
Docker db/backend/frontend/Keycloak/JWKS fixture: running; 2 Agent workers online
Two-worker OIDC cleanup bucket: exactly 1 durable job
Periodic cleanup: completed attempt 1; 3 inactive provider tokens purged; 0 backlog remaining
Session administration RBAC: ML Ops audit passed, cleanup 403; Admin cleanup passed
Post-login session state: active 1, expired 1, revoked 2, audit events 7
Two-worker due scan: exactly 1 durable sync job and 1 scheduled receipt for run sequence 1
Scheduled job: completed on attempt 1; lease cleared; next run advanced
Schedule metrics: enabled 1, due 0, retrying 0, failed 0
Runtime/IdP/observability and isolation Compose validation: passed
Prometheus endpoint: HTTP 200
Operational snapshot dedupe: 12 snapshots, 12 buckets, 12 jobs, 12 unique dedupe keys
Prometheus target: up; rules loaded: 10
Signed paging HTTP 202 and receiver payload-hash match: passed
Paging outage: 4 attempts exhausted; verified Admin requeue after recovery: passed
Operations RBAC: ML Ops audit passed; capture/test-page controls disabled
Live Keycloak PKCE login and ML Ops Lead role mapping: passed
CSRF-protected POST logout, DB revocation, IdP logout, and frontend return: passed
Desktop Operations browser QA: passed
Operations page-level horizontal overflow: 0; wide tables use internal scrolling
Final browser console: 0 warnings or errors
Attested qwen2.5:0.5b campaign: completed first attempt, 5 results, 5 metrics, 2 reviewed
Signed supply chain: 1 managed development-key statement, CycloneDX 1.6, not revoked
Trust registry: 4 active development roots, 1 healthy source, 1 valid development proof,
0 production eligible
Signed production receipts: 0; local-authored evidence was not promoted to production
```

## Current Boundaries

- Bundled evidence remains primarily synthetic or locally authored. A real Ollama run is included
  as local runtime evidence, not production validation.
- Tool handlers are deterministic in-process fixtures with no production credentials or network
  side effects.
- RAG uses a deterministic local corpus and lexical retriever, not production ingestion, embeddings,
  vector storage, or online serving.
- Runtime Reliability uses in-process bounded workers and deterministic fixtures, not distributed
  load generation, live GPU monitoring, or production traffic replay.
- Agent recovery selects one predeclared branch or one bounded callback result and does not run an
  open-ended model loop. A production-shaped OpenAI-compatible transport is included, but no model
  quality claim follows from transport integration alone.
- Resume creates an append-only child run and automatically stales prior Gate evidence. Historical
  signed decisions remain immutable audit records.
- JWT verification supports HS256 and RS256 discovery/JWKS rotation. Browser PKCE now uses shared
  revocable sessions, Origin/CSRF enforcement, RP-initiated provider logout, verified-role
  administration, token minimization, and retention cleanup. Production TLS, back-channel logout,
  secret-rotation drills, and external identity lifecycle are not included.
- The PostgreSQL worker supports durable leases, heartbeats, dead letters, and reconciliation but
  is not a distributed workflow engine. The collector is a reference HTTP/outbox client, not Kafka.
- Agent memory writes remain task-local simulations; there is no durable memory service,
  multi-agent coordinator, or production agent.
- Production Readiness is an evidence and policy interpretation, not infrastructure deployment.
- Model identity now binds a server-observed digest and can verify configured publisher signatures,
  CycloneDX SBOM hashes, and append-only revocation. The bundled signer is a development key;
  external publisher identity, transparency logs, OCI registry verification, and online revocation
  distribution are not included.
- Remote JWKS synchronization includes durable interval policies and replica-safe PostgreSQL
  leases, but the bundled endpoint is development-only. The scheduler is at-least-once and does
  not provide calendar cron, multi-region consensus, or a general workflow service.
- Durable snapshots, paired-window burn rates, response actions, escalation, projected rotating-key
  TLS paging, strict receipts, readiness, and failure drills are included. The bundled receiver,
  generated CA, and secret volume are development fixtures rather than an external HA paging
  service, managed PKI, or secret manager.
- Tool/RAG preflight and Docker isolation examples are included, but per-run OS/Kubernetes sandbox
  orchestration is not.
- No production SSO service, Kubernetes, Kafka, Spark, or signed live model registry is included.

## Handoff Reading Order

1. `README.md`
2. `docs/reports/2026-08-04_model_atlas_sprint_5h_h_implementation_report.md`
3. `docs/staging_paging_qualification.md`
4. `docs/reports/2026-08-03_model_atlas_sprint_5h_g_implementation_report.md`
5. `docs/incident_response_and_burn_rate.md`
6. `docs/operational_slo_and_paging.md`
7. `docs/operational_observability.md`
8. `docs/reports/2026-07-27_model_atlas_sprint_5h_e_implementation_report.md`
9. `docs/browser_session_administration.md`
10. `docs/browser_oidc.md`
11. `docs/reports/2026-07-23_model_atlas_sprint_5h_d_implementation_report.md`
12. `docs/trust_source_scheduling.md`
13. `docs/trust_source_sync.md`
14. `docs/trust_registry_transparency.md`
15. `docs/supply_chain_evidence.md`
16. `docs/model_artifact_attestation.md`
17. `docs/model_validation.md`
18. `docs/workload_isolation.md`
19. `docs/agent_orchestration.md`
20. `docs/agent_control_plane.md`
21. `docs/agent_recovery_and_approval.md`
22. `docs/agent_operations.md`
23. `docs/runtime_reliability.md`
24. `docs/rag_evaluation.md`
25. `docs/tool_calling_evaluation.md`
26. `docs/golden_demo.md`
27. `docs/architecture.md`
28. `docs/data_contract.md`
29. `docs/deployment_gate.md`

## Recommended Next Work

Next work should deploy the completed 5H-H qualification boundary against an external secret
manager, managed PKI, and real staging paging provider, retaining verifier, rotation, certificate
renewal, rolling key removal, and failure-drill evidence. Then add staging publisher provenance, a
target 7B GPU run with reviewed production capture receipts, provider back-channel identity
lifecycle where required, and per-job OS or Kubernetes sandbox execution.
