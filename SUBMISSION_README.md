# Model Atlas Submission Package

## Current Submission (2026-09-13)

**Start with [MVP_REVIEW_GUIDE_KO.md](MVP_REVIEW_GUIDE_KO.md)** for installation, demo and technical review.
Then read [MVP_SCOPE_KO.md](MVP_SCOPE_KO.md) and
[the current verification report](docs/reports/2026-09-13_mvp_closeout_ko.md).

The current package uses `deploy/mvp-review.compose.yml`, a separate database, UI port 13000,
and API port 18010. Do not seed the original database. The fresh UI contains mock evidence,
not the original 384 actual runtime observations. Official results remain BLOCKED, with
110 critical failure observations and 0/30 targeted output reviews. External user review is pending.

`PACKAGE_INFO.json` links the actual current verification receipt. `MANIFEST.sha256` covers
all payload files. Model weights, private keys, actual environment files and databases are excluded.
This is a source/evidence package, not a production release or an offline runtime image.

## Historical Submission Notes (2026-08-04)

**Everything below records the earlier Sprint 5H-H checkpoint. Its test counts, setup commands,
service health and acceptance results are historical, not this submission's verification.**
Use the current guide above for new installation. Historical corpus source documents remain
unchanged to preserve approved evidence hashes.

## What This Package Is

This package contains the Model Atlas MVP source code, documentation, Docker runtime configuration,
tests, and evaluator-facing review documents.

Model Atlas is a local-first EvalOps/MLOps project for evaluating whether a specific local AI
deployment configuration is ready for release. It is not a model-weight bundle. No external model
weights are included. The project can evaluate local models exposed through an OpenAI-compatible
runtime such as LM Studio or Ollama.

## Start Here

Recommended review order:

1. `docs/reports/2026-08-04_model_atlas_sprint_5h_h_implementation_report.md`
2. `docs/staging_paging_qualification.md`
3. `docs/reports/2026-08-03_model_atlas_sprint_5h_g_implementation_report.md`
4. `docs/incident_response_and_burn_rate.md`
5. `docs/operational_slo_and_paging.md`
6. `docs/browser_session_administration.md`
7. `docs/trust_registry_transparency.md`
8. `docs/supply_chain_evidence.md`
9. `docs/model_artifact_attestation.md`
10. `docs/model_validation.md`
11. `docs/operational_observability.md`
12. `docs/workload_isolation.md`
13. `README.md`
14. `docs/agent_orchestration.md`
15. `docs/agent_control_plane.md`
16. `docs/agent_recovery_and_approval.md`
17. `docs/agent_operations.md`
18. `docs/runtime_reliability.md`
19. `docs/rag_evaluation.md`
20. `docs/tool_calling_evaluation.md`
21. `docs/golden_demo.md`
22. `docs/architecture.md`
23. `docs/data_contract.md`

## Main Value Proposition

Existing token/hardware-based local model recommenders answer:

- Which model might run on this hardware?
- Which artifact has acceptable VRAM, context length, throughput, or benchmark score?

Model Atlas adds an operational approval layer:

- Candidate Discovery ranks model artifacts but does not approve deployment.
- Deployment Gate evaluates a concrete deployment configuration against workload evidence and
  acceptance policy.
- Evidence Trust separates source provenance from score and judge-label provenance.
- Gate Preflight shows evidence, policy, baseline, and limitations before a decision is stored.
- Executable Tool Calling validates selection and arguments, runs bounded local tools, and records
  failures, retry recovery, outputs, and multi-step order as Gate evidence.
- RAG Evaluation runs versioned local retrieval before generation and evaluates retrieval recall,
  citation precision/recall, groundedness, and unsupported claims.
- Runtime Reliability persists repeated success, timeout, OOM, latency, variation, coverage, and
  context-stress evidence, then compares same-suite runtime runs.
- Agent Operations executes a single bounded plan across allowlisted memory, retrieval, and tool
  actions, then exposes step-level provenance, policy violations, retry recovery, and semantic
  replay as release evidence.
- Adaptive Agent Operations adds external human checkpoints, guarded actions, versioned
  observations, one-shot recovery branches, and fail-closed Gate evidence.
- Agent Control Plane adds verified role-scoped approvers, separation of duties, persistent
  checkpoint lifecycle, resume, metered live-replan callbacks, and verified production trace
  import.
- Agent Orchestration preserves resume as append-only child evidence, executes work through durable
  leases, stales obsolete Gates, verifies JWT/proxy identity, and accepts signed traffic batches.
- Production Hardening adds OIDC/JWKS rotation, worker and dead-letter operations, a replay-safe
  traffic collector, stale release actions, and durable local-model validation reports.
- Artifact Identity and Operations binds server-observed SHA-256 manifests to immutable deployment
  configurations, records accountable reviewed labels, supports browser PKCE sessions, exports
  metrics and alerts, and fail-closes Tool/RAG execution against a versioned isolation policy.
- Supply-Chain Trust verifies publisher statements and production receipts, binds CycloneDX SBOM
  evidence, and requires managed lifecycle plus transparency evidence for production trust.
- Federated Trust Sources add HTTPS-by-default remote JWKS Preview/Apply, atomic key import,
  freshness-aware eligibility, source lineage, health metrics, and an operator console. Durable
  interval policies add replica-safe enqueue leases, execution leases, deterministic retry,
  per-attempt receipts, dead letters, and authenticated immediate runs.
- Shared Browser Identity adds opaque database sessions, CSRF/Origin enforcement, verified-role
  containment, RP-initiated provider logout, token minimization, retention cleanup, strict proxy
  boundaries, and shared OIDC caches.
- Operational Reliability persists replica-safe metric history, evaluates missing-interval-aware
  identity and worker SLOs, preserves incident transitions, and proves HMAC-signed paging delivery
  through durable retry/dead-letter/requeue evidence.
- Incident Response adds paired long/short burn rates, verified acknowledgement and assignment,
  hash-linked action history, automatic escalation, rotating-key identity, and CA-verified HTTPS
  paging without exposing secrets.
- Staging Paging Qualification adds runtime-projected secrets, no-restart rotation, strict
  delivery-to-provider receipt correlation, a seven-check readiness gate, and executable
  outage/dead-letter/requeue recovery evidence.
- Release Decisions store signer identity, RBAC policy state, frozen readiness snapshot,
  signature hash, decision hash, and snapshot drift.

## How To Run

From the project root:

```bash
make up
```

Then open:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:18000`
- OpenAPI: `http://localhost:18000/docs`

Seed data:

```bash
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

Optional development JWKS source:

```bash
make trust-source-up
```

Optional full local observability and paging path:

```bash
make observability-up
make operational-staging-verify
make paging-key-rotate KEY_ID=2026-08-04-rotated
make operational-failure-drill
```

## Verification Commands

Backend:

```bash
cd backend
..\.venv\Scripts\pytest.exe
..\.venv\Scripts\ruff.exe check .
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

Docker:

```bash
docker compose run --rm backend pytest
docker compose run --rm frontend npm run lint
```

Recent verified status:

- Backend pytest: 186 passed, 1 warning
- Backend and tools Ruff: passed
- Frontend typecheck/lint/build: passed
- Docker Compose build and migration `202608040001`: passed
- Backend, two Agent workers, HTTPS paging sink, and trust-source fixture healthy
- TLS and paging secret initializers exited 0
- Staging readiness passed 7 of 7 checks
- No-restart rotation selected `2026-08-04-rotated`
- Provider schema, delivery event, receipt ID, and acceptance-time correlation persisted
- Controlled sink outage reached dead letter; verified SRE requeue recovered the same job and a
  final capture reconciled transient incidents
- Final operational health `healthy`, open incidents 0, dead letters 0
- Twenty-six historical trust-source failures were requeued and three incidents resolved
- Historical deliveries remained readable with migrated `legacy` key identity
- Verified acknowledgement and assignment formed a valid two-event predecessor-hash chain
- Desktop and 390 x 844 mobile 5H-H QA: no document overflow, clipped controls, or console errors
- Two live workers produced 12 cycle jobs for 12 unique snapshot buckets with 12 unique dedupe
  keys at the verification checkpoint
- Prometheus target was up and all 10 alert rules loaded
- Signed paging delivery returned HTTP 202 with a matching payload hash
- Controlled receiver outage exhausted four attempts; Admin requeue after recovery completed and
  produced the expected event-id receipt
- Operations RBAC: Keycloak ML Ops Lead could audit while capture/test-page controls stayed
  disabled
- Two concurrent Agent workers observed one OIDC cleanup bucket and produced exactly one durable
  job; it completed on attempt 1 and purged provider token material from 3 inactive sessions
- Session cleanup backlog after completion: retention due 0, inactive provider tokens 0
- Browser-session RBAC: ML Ops audit passed, ML Ops cleanup returned 403, Admin cleanup passed
- Browser-session state after final login: active 1, expired 1, revoked 2, audit events 7
- Two concurrent Agent workers scanned one due trust-source policy and produced exactly one durable
  job and scheduled receipt; completion cleared the lease and advanced the next run
- Scheduled sync metrics after completion: enabled 1, due 0, retrying 0, failed 0
- Runtime/IdP/observability and isolation Compose configuration: passed
- Prometheus metrics endpoint: HTTP 200
- Live remote JWKS Preview/Apply: passed; 1 source healthy, 1 root imported, 0 rejected
- Live Keycloak PKCE login, role mapping, CSRF-protected POST logout, DB revocation, provider
  logout, and frontend return: passed
- Desktop 1440 x 900 and mobile 390 x 844 browser QA: passed; final console clean
- Attested Ollama `qwen2.5:0.5b` validation campaign: completed, 5 results, 5 metrics,
  verified digest, and 2 human-reviewed cases
- Signed supply-chain statement: verified with a development RS256 key and matching CycloneDX 1.6
  SBOM; reconciled to a managed development root with no revocation
- Trust registry and transparency: four active development roots, one healthy source, and one valid signed Merkle
  proof; zero production-eligible roots, proofs, attestations, or receipts
- Signed production receipts: 0; local-authored evidence remains outside production thresholds
- Snapshot JSON export and snapshot diff: passed

## Package Notes

Included:

- Backend FastAPI source, Alembic migrations, tests, and Dockerfile.
- Frontend Next.js source, TypeScript types, components, and Dockerfile.
- Docker Compose configuration.
- Seed data examples and import scripts.
- Architecture, data contract, deployment gate, roadmap, technical report, and evaluator review
  documentation.

Excluded from the zip:

- `.venv/`
- `node_modules/`
- `.next/`
- cache directories
- runtime database volumes
- generated local temporary files
- Ollama model weights and Docker volumes

## MVP Boundary

The current MVP demonstrates a local AI deployment approval workflow, not a full production
platform. Tool execution, RAG retrieval, Runtime Reliability profiles, and Agent Operations use
deterministic local fixtures. The Agent runtime executes one bounded plan, may select one
predeclared branch or one metered callback result, and uses task-local simulated memory writes; it
is not an unrestricted autonomous system. Resume creates append-only child evidence through a
durable PostgreSQL worker and automatically stales prior Gates. Identity supports HS256 and RS256
JWTs with OIDC discovery/JWKS rotation, trusted proxies, browser Authorization Code + PKCE, and a
Keycloak development profile. Browser sessions are now shared and revocable with RP-initiated
provider logout, verified-role administration, token minimization, and retention cleanup.
Production TLS, back-channel logout, secret-rotation drills, and external identity lifecycle
remain out of scope. Local Model Validation binds a server-observed runtime digest and
can verify managed publisher signatures, CycloneDX SBOM hashes, append-only key/attestation
lifecycle, signed transparency inclusion, remote JWKS source freshness, and production capture
receipts. The included signer and
proof are development-only; external publisher identity, independent registry transparency,
online revocation distribution, calendar scheduling, and actual production receipts remain out of
scope. Interval-based source synchronization is implemented with PostgreSQL-backed at-least-once
leases and deterministic retry, but it is not a multi-region consensus or general workflow
service. Durable control-plane snapshots, paired-window burn rates, response actions, automatic
escalation, projected rotating-key TLS paging receipts, strict receipt correlation, staging
readiness, and failure drills are implemented. The bundled receiver, generated CA, and secret
volume remain development fixtures rather than an external HA on-call service, managed PKI, or
secret manager. Tool/RAG
policy preflight and Docker isolation examples are included, but the primary
worker does not yet create one OS sandbox per run. The project intentionally excludes live cloud
deployment, hosted model
weights, production-connected tools, production RAG ingestion/vector serving, distributed load
generation, live GPU monitoring, Kafka/Spark, a general workflow engine, durable Agent memory,
multi-agent coordination, actual external secret-manager/paging-provider integration, and general
post-deployment telemetry.
