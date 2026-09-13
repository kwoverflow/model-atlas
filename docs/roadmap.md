# Roadmap

## Sprint 2

- Deterministic recommendation engine: MVP implemented.
- Hard eligibility filter: MVP implemented.
- Scoring engine: MVP implemented over quality, latency, throughput, and VRAM efficiency.
- Pareto frontier: MVP implemented for eligible artifacts.
- Recommendation report: MVP implemented through API and dashboard page.
- User-editable scoring weights: implemented through URL-backed dashboard controls and API query parameters.
- Persisted recommendation scenarios: implemented with named saved requests and replayable report endpoints.
- Coverage-confidence penalties: implemented through confidence-adjusted recommendation scores.
- Markdown report export: implemented for current reports and saved scenario reports.
- PDF report export: implemented for current reports and saved scenario reports.
- Scenario update/delete workflow: implemented for saved scenario curation.

Remaining Sprint 2 improvements:

- More explicit license and deployment-policy modeling.

## Sprint 3A

- Workload contracts: implemented.
- Evaluation suites and cases: implemented.
- Metric definitions: implemented.
- Acceptance policies and rules: implemented.
- Immutable deployment configurations: implemented.
- Deployment Gate evaluator: implemented over stored evidence.
- Baseline regression calculation: implemented for stored gate scorecards.
- Synthetic-only approval blocking: implemented.
- Gate report Markdown/PDF exports: implemented.
- Workloads, deployments, and gate report pages: implemented.

## Sprint 3B

- InferenceAdapter protocol: foundation implemented.
- Mock benchmark execution adapter: implemented.
- OpenAI-compatible local adapter: base URL/model override and endpoint discovery implemented.
- Runtime health check API: implemented.
- Benchmark execution API and logs: implemented.
- Real local runtime validation through Docker Ollama and `qwen2.5:0.5b`: implemented.
- Captured local 40-case suite seed: implemented.
- Deterministic scorer hooks for quality, groundedness, and faithfulness labels: implemented.
- Scorer registry for pluggable local result scoring: implemented.
- Production-captured evaluation case import workflow: implemented.
- Human/LLM judge label import and calibration workflow: implemented.
- Deployment baseline promotion with active-baseline auto-selection: implemented.
- Baseline approval-history and supersession page: implemented.
- Judge-label review and calibration dashboard: implemented.
- Judge-label dashboard import dry-run/apply workflow: implemented.
- Prompt version regression testing: implemented.
- Experiment lineage events and dashboard: implemented.
- Release readiness snapshot and Markdown export: implemented.
- Signed release decision records, Markdown export, snapshot JSON export, and snapshot diff: implemented.
- Release decision lineage events in experiment timeline: implemented.
- Signer identity capture, signature statements, signature hashes, trusted-header identity middleware, and role-based release approval policy: implemented.

## Sprint 4A

- Evidence Trust source/score separation: implemented.
- Gate Preflight and workflow Overview: implemented.
- Gate, readiness, production, and evidence status separation: implemented.
- Adapter/scorer extension descriptors and snapshot provenance: implemented.
- Workflow navigation and decision-first Gate UX: implemented.

## Sprint 4B

- Bounded local Tool Registry: implemented.
- Tool selection and argument validation: implemented.
- Actual handler execution and output validation: implemented.
- Retryable/permanent failure evidence and recovery: implemented.
- Multi-step tool sequence traces: implemented.
- Tool-specific scorer, Gate metrics, suite, and policy: implemented.
- Tool Registry and benchmark trace APIs/UI: implemented.

## Sprint 4C

- Versioned RAG corpus and retrieval configuration: implemented.
- Retrieval recall and ranking quality: implemented for deterministic lexical retrieval.
- Citation precision/recall and groundedness: implemented.
- Unsupported-claim rate: implemented.
- RAG-specific Gate policy rules and trace UI: implemented.

## Sprint 4D

- Repeated trials and per-case variance: implemented.
- P50/P95/P99 latency and TTFT: implemented.
- Bounded in-process concurrency: implemented.
- Context-length stress evidence: implemented.
- Timeout and OOM behavior: implemented.
- Runtime comparison and reliability-specific Gate rules: implemented.

## Sprint 5A

- Plan-first bounded Agent task execution: implemented.
- Operational-memory evidence and task-local simulated writes: implemented.
- Tool, retrieval, response, retry, and policy traces: implemented.
- Semantic replay with signatures and changed paths: implemented.
- Agent-level Gate metrics and policy pack: implemented.
- Release snapshot and lineage coverage through existing benchmark/Gate ownership: implemented.

## Sprint 5B

- Versioned observation envelopes: implemented.
- One-shot replanning and explicit recovery budgets: implemented.
- Human approval checkpoints and guarded actions: implemented.
- Approval and recovery semantic replay: implemented.
- Agent-specific Gate metrics and snapshot v7 provenance: implemented.

## Sprint 5C

- Authenticated policy-scoped checkpoint approvers: implemented.
- Persisted pause/resume Agent execution state: implemented.
- Approval expiry, revocation, and separation-of-duties rules: implemented.
- Optional bounded live replan callback with model-call cost and latency evidence: implemented as
  a provider boundary with deterministic fixture coverage.
- Production-captured Agent evidence import contract: implemented.

## Sprint 5D

- Append-only child-run revisions for resumed execution evidence: implemented.
- Asynchronous execution workers and durable job leasing: implemented.
- Gate staleness and required re-evaluation after evidence revisions: implemented.
- Verified JWT integration and trusted-proxy header hardening: implemented with static HS256 keys.
- Scheduled checkpoint expiry and Gate reconciliation: implemented in the Agent worker.
- Production-shaped live-replan provider and signed traffic evidence ingestion: implemented.

## Sprint 5E

- OIDC discovery, JWKS rotation, and asymmetric JWT verification: implemented.
- Worker heartbeat telemetry, dead-letter operations, and requeue: implemented.
- Reference production traffic collector and signing-key rotation: implemented.
- Stale release-decision review, revocation, and replacement workflow: implemented.
- Durable local-model validation campaigns and reports: implemented.
- Real Ollama runtime smoke evidence: implemented with explicit model-mismatch and review limits.

## Sprint 5F

- Model artifact digest/manifest attestation: implemented.
- Target-artifact execution or a deployment configuration matching the observed model:
  implemented with a digest-pinned `qwen2.5:0.5b` configuration.
- Reviewed judge decisions for critical and representative cases: implemented.
- Browser OIDC login/session integration and deployable IdP examples: implemented.
- Exported worker, collector, and release-operation metrics with alert routing: implemented.
- Production-shaped Tool/RAG isolation and credential/network policy examples: implemented.

## Sprint 5G

- Fail-closed configured-JWKS verification for signed evidence: implemented.
- Signed in-toto-style model provenance and CycloneDX SBOM binding: implemented.
- Append-only supply-chain revocation with verifier/revoker separation: implemented.
- Signed production capture receipts and unverified-label trust downgrade: implemented.
- Model Validation v3, Supply Chain UI, and operational trust metrics: implemented.
- Target 7B execution on representative GPU hardware and broader production-captured coverage:
  pending external hardware and capture source.

## Sprint 5H

- Purpose-scoped public-key trust registry, append-only key lifecycle, signed checkpoints, and
  Merkle transparency evidence: implemented in Sprint 5H-A.
- Allowlisted remote JWKS sources, Preview/Apply receipts, atomic key import, source lineage,
  freshness-aware eligibility, metrics, and operator UX: implemented in Sprint 5H-B.
- External publisher, internal production CA, OCI registry, or independent transparency-service
  integration using production credentials: pending external trust infrastructure.
- Shared browser sessions, RP-initiated provider logout, CSRF/proxy review, and horizontally shared
  discovery/JWKS cache: implemented in Sprint 5H-C.
- Scheduled trust-source synchronization with PostgreSQL enqueue leases, durable execution leases,
  deterministic jitter, retry/dead-letter policy, receipts, metrics, and operator UX: implemented
  in Sprint 5H-D.
- Verified-role browser session audit/containment, provider-token minimization, hash-linked
  lifecycle events, and replica-deduplicated retention cleanup: implemented in Sprint 5H-E.
- Durable operational snapshot retention, explicit identity/worker SLOs, incident transitions,
  owned signed paging, retry/dead-letter recovery, and delivery testing: implemented in Sprint
  5H-F.
- Paired-window SLO burn rates, verified acknowledgement/assignment/note actions, hash-linked
  response history, automatic escalation, rotating HMAC key identity, and private-CA-verified
  HTTPS paging: implemented in Sprint 5H-G.
- Runtime secret projection, no-restart rolling key rotation, strict provider-receipt correlation,
  seven-check staging readiness, and executable outage/recovery qualification: implemented in
  Sprint 5H-H.
- Deployment against an external secret manager, managed PKI with renewal, and a real staging
  paging provider: pending target-environment credentials and infrastructure.
- Per-job OS/Kubernetes sandbox orchestration with egress and resource enforcement.
- Durable streaming traffic evidence where operational scale requires it.

## Later

- Distributed workflow execution and streaming traffic evidence.
- Live GPU/runtime telemetry and external alerting integrations.

## Notes

Sprint 1 deliberately focuses on data shape, validation, seed records, local API contracts, and dashboard visibility. Recommendation and execution logic should build on the Sprint 1 traceability model rather than bypassing it.
