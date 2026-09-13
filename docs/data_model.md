# Data Model

The data model is centered on traceability from a logical model to an artifact, a task, a prompt, a run, sample-level outcomes, a Deployment Gate decision record, and signed release decisions.

## Entities

## HardwareProfile

Represents a local execution environment. The seed profile is the RTX 4080 Super workstation with Intel Core i9-13900K, 64 GB RAM, and 16 GB VRAM.

Key fields include CPU, RAM, GPU, VRAM, GPU count, OS, CUDA version, driver version, and notes.

## Model

Represents a logical model family entry, independent from a specific artifact. Capability fields describe text, vision, tool-calling, and structured-output support.

Key fields include provider, family, name, display name, parameter count, architecture, context length, license, commercial use, languages, source URL, and notes.

## ModelArtifact

Represents a runnable or downloadable artifact for a logical model. Multiple artifacts can exist for one model, such as fp16, bf16, GGUF, AWQ, or other quantized formats.

Key fields include format, quantization, precision, file size, VRAM requirements, context limit, runtime compatibility, checksum, active status, and notes.

## BenchmarkTask

Defines what is being measured. Sprint 1 seeds Korean document QA, structured JSON generation, tool calling, and latency smoke test tasks.

Key fields include category, task type, language, input format, expected output format, scoring method, dataset version, and active status.

## PromptVersion

Captures prompt text and output expectations used for a task. Prompt versions are linked to tasks and hashed for reproducibility.

Key fields include system prompt, user template, output schema, prompt hash, version label, active status, and notes.

## BenchmarkRun

Connects hardware, artifact, task, prompt version, runtime, runtime configuration, dataset version, seed, timing, status, and data source.

Runs are the parent record for sample-level results and metrics.

Sprint 5D adds append-only execution lineage through parent/root run IDs, a positive revision
number, revision reason, and evidence revision hash. Root revision 1 is the original run; resume
creates a child instead of mutating it.

## BenchmarkResult

Stores sample-level quality and correctness outcomes for a run.

Key fields include sample ID, quality score, exact match, JSON validity, tool-call validity, groundedness, faithfulness, human label, error type, raw output, normalized output, metadata, and data source.

Sprint 5D adds parent/root result IDs, revision number, and evidence revision hash. Gate aggregation
uses the latest result revision for each root.

## AgentApprovalCheckpoint

Stores persistent human-control state for one logical checkpoint in one Agent benchmark result.

Key fields include run, result, checkpoint ID, lifecycle status, requester identity, request and
policy snapshots, request hash, expiry, decision and approver identity, decision hash, revocation
and resume evidence, identity verification state, and optimistic-lock version.
Sprint 5D also records the transition child run/result produced by resume.

Allowed states are `pending`, `approved`, `denied`, `revoked`, `expired`, and `resumed`.
`(benchmark_result_id, checkpoint_id)` is unique.

## AgentExecutionJob

Stores durable control-plane work for checkpoint resume, reconciliation, and signed traffic
evidence import, plus local-model validation campaigns. Key fields include type, status, unique
dedupe key, payload and requester identity, optional run/result/checkpoint links, priority,
availability, lease owner/token/expiry, heartbeat state, attempt budget, timestamps, result JSON,
last error, dead-letter metadata, and requeue audit state.

Workers claim queued rows with a lease. Expired leases can return to the queue, while validation
failures become terminal failed records.

## AgentWorkerState

Stores one durable operational record per worker. It tracks online/stopped state, start and
last-seen timestamps, current job, processed/completed/failed counters, and runtime metadata.
Offline status is derived when the overview is read.

## AgentTrafficReceipt

Stores replay and signing provenance for one accepted traffic batch. It binds source system, batch
ID, nonce, signature version/hash, signing key ID, collector version, capture/sent/received times,
replay count, and queued job.

## InferenceMetric

Stores sample-level performance and hardware metrics for a run.

Key fields include TTFT, end-to-end latency, prompt tokens, completion tokens, tokens per second, GPU VRAM used, GPU and CPU utilization, peak memory, OOM flag, retry count, and data source.

## RecommendationScenario

Stores a named, replayable recommendation request.

Key fields include name, optional description, request JSON, created timestamp, and updated timestamp. The request JSON follows the `RecommendationRequest` API contract and includes filters, `top_k`, and scoring weights.

## WorkloadProfile

Defines the operational workload being approved. Key fields include slug, domain, primary language, local-only requirement, data classification, expected output modes, risk notes, and active status.

## EvaluationSuite

Defines a versioned set of evaluation cases for one workload. Key fields include workload, name, version label, suite hash, status, dataset source, and synthetic marker.

## EvaluationCase

Defines a reproducible test case with business criticality. Key fields include external case ID, category, input payload, expected output, reference context, expected tool schema, tags, criticality, weight, active status, and data source.

## MetricDefinition

Defines a metric that policy rules can reference. Initial metrics cover quality, JSON validity, tool-call validity, groundedness, faithfulness, critical failures, latency, throughput, VRAM, OOM rate, evidence counts, and baseline regressions.

## AcceptancePolicy And AcceptancePolicyRule

An acceptance policy is a versioned rule set for one workload. Rules reference metric definitions and define an operator, threshold, severity, minimum sample size, required flag, and failure message.

## DeploymentConfiguration

Represents an immutable deployable AI configuration. It binds workload, hardware, artifact, runtime, context length, generation settings, prompt bundle, schema versions, retrieval settings, concurrency target, status, and a canonical `configuration_hash`.

## GateEvaluation And GateRuleResult

A gate evaluation is a preserved decision record built from completed benchmark evidence. It stores
the deployment configuration, suite, policy, optional baseline, verdict, evidence snapshot,
evidence revision hash, scorecard, decision summary, decision hash, and evaluated timestamp. Sprint
5D may change its operational status to `stale` while preserving the original verdict/snapshot. It
also stores stale timestamp/reason and an optional superseding Gate link. Rule results store
per-rule metric values, sample sizes, pass/fail/insufficient status, severity, and details.

## DeploymentBaseline

A deployment baseline marks an approved gate evaluation as the active comparison point for one
deployment configuration, evaluation suite, and acceptance policy scope.

Key fields include deployment configuration, suite, policy, source gate evaluation, promotion time,
promoter, promotion reason, baseline hash, status, supersession timestamp, superseding baseline, and
notes.

## BenchmarkExecutionLog

Stores runtime events emitted while benchmark cases are executed through an inference adapter. Key fields include benchmark run, event type, level, message, payload JSON, occurrence time, and data source.

## ExperimentLineageEvent

Stores append-only traceability events that connect prompt versions, benchmark runs, gate
evaluations, deployment baselines, baseline supersession, and release decisions. Key fields include
event type, primary entity, event time, lineage key,
deployment/suite/policy/prompt/run/gate/baseline/release-decision links, status, summary,
metadata JSON, and data source.

## ReleaseDecision

Stores a signed release decision for a frozen readiness snapshot. Key fields include source gate
evaluation, deployment configuration, evaluation suite, acceptance policy, decision value,
readiness status, signer identity JSON, identity verification state, approval policy JSON,
signature statement, reason, notes, snapshot JSON, snapshot hash, signature hash, decision hash,
and decision timestamp.

Sprint 5E adds an optional `replaces_release_decision_id`. `ReleaseDecisionAction` stores
append-only stale detection, review, acknowledgement, revocation, and replacement events without
changing the signed decision snapshot.

## ModelArtifactAttestation

Stores an append-only server-observed model manifest for one `ModelArtifact`. Fields include
runtime provider/model/source, digest algorithm/value, normalized manifest JSON and hash,
verification method/status, attestation time, verified actor identity, notes, and stable
attestation hash. The artifact checksum and generated deployment runtime digest must agree with
this record for a verified Model Validation state.

## ModelSupplyChainAttestation And Action

`ModelSupplyChainAttestation` stores a publisher-signed in-toto-style statement verified against
configured trust policy. It binds one runtime attestation and model artifact to a SHA-256 subject,
runtime manifest and attestation hashes, canonical CycloneDX SBOM digest/content, publisher issuer,
key identity, signature algorithm, statement ID/time, verifier identity, original compact JWS, and
stable attestation hash.

`ModelSupplyChainAttestationAction` preserves append-only revocation. It stores the attestation,
action type, reason, optional ticket, verified revoker identity, action time, and stable action
hash. The effective state is derived without rewriting the signed attestation.

## ProductionEvidenceReceipt

Stores a collector-signed production capture binding for one completed benchmark run. Fields bind
the deployment configuration, runtime and supply-chain attestation chain, artifact digest, capture
window and environment, exact result/metric counts, issuer/key/signature metadata, verifier
identity, compact JWS, receipt time, and stable receipt hash. Only an active receipt allows a
`production_captured` label to contribute to production evidence thresholds.

## JudgeLabelReviewDecision

Stores an append-only accountable review for one `BenchmarkResult`. It captures candidate hash,
prior labels, applied labels, decision type, applied state, reviewer identity, rationale,
criticality, review time, and stable review hash. The mutable result carries the currently applied
human-reviewed values; the decision preserves the before/after audit record.

## Relationships

- One `Model` has many `ModelArtifact` records.
- One `ModelArtifact` has many `ModelArtifactAttestation` records.
- One `ModelArtifact` has many `ModelSupplyChainAttestation` records.
- One `ModelArtifactAttestation` has many supply-chain attestations and production receipts.
- One `ModelSupplyChainAttestation` has many append-only actions and production receipts.
- One `HardwareProfile` has many `BenchmarkRun` records.
- One `BenchmarkTask` has many `PromptVersion` and `BenchmarkRun` records.
- One `PromptVersion` has many `BenchmarkRun` records.
- One `ModelArtifact` has many `BenchmarkRun` records.
- One `BenchmarkRun` has many `BenchmarkResult` and `InferenceMetric` records.
- One `BenchmarkRun` may have one idempotent signed production evidence receipt.
- One `BenchmarkResult` has many review decisions over its audit history and at most one applied
  decision through service-layer enforcement.
- One root `BenchmarkRun` can have an append-only chain of child run revisions.
- One root `BenchmarkResult` can have an append-only chain of child result revisions.
- One `BenchmarkResult` has many uniquely keyed `AgentApprovalCheckpoint` records.
- One `AgentApprovalCheckpoint` may link to one transition child run/result.
- One `AgentExecutionJob` may link to its run, result, and checkpoint ownership scope.
- One `AgentWorkerState` may point to its current `AgentExecutionJob`.
- One `AgentTrafficReceipt` points to the queued import job and is unique by source/batch and
  source/nonce.
- A `RecommendationScenario` stores a request snapshot and intentionally has no foreign-key dependency on selected hardware or tasks. This keeps scenarios readable even if future catalog records are edited.
- One `WorkloadProfile` has many evaluation suites, acceptance policies, and deployment configurations.
- One `EvaluationSuite` has many evaluation cases and gate evaluations.
- One `DeploymentConfiguration` has many benchmark runs and gate evaluations.
- One `GateEvaluation` has many gate rule results.
- One stale `GateEvaluation` may link to the newer Gate that supersedes it.
- One `GateEvaluation` can be promoted by many deployment baseline records over time.
- One deployment configuration, evaluation suite, and acceptance policy scope has at most one active
  deployment baseline through service-layer enforcement.
- One `BenchmarkRun` has many benchmark execution logs.
- `BenchmarkRun` may reference a deployment configuration and evaluation suite.
- `BenchmarkResult` may reference an evaluation case.
- `ExperimentLineageEvent` may reference prompt versions, benchmark runs, gate evaluations,
  deployment baselines, release decisions, and the deployment/suite/policy scope it belongs to.
- One `GateEvaluation` can have many signed release decision records over time.
- One `ReleaseDecision` can have many append-only operational actions and may be replaced by a
  newer decision.
- Each `ReleaseDecision` duplicates the deployment configuration, evaluation suite, and acceptance
  policy scope from the frozen snapshot for audit-friendly filtering.

## Benchmark Traceability

Each benchmark result can be traced through:

1. sample ID;
2. benchmark result;
3. benchmark run;
4. prompt version;
5. benchmark task;
6. model artifact;
7. logical model;
8. hardware profile;
9. runtime configuration.

This shape supports later recommendation logic without changing the core run/result/metric lineage.

Deployment Gate traceability adds:

1. deployment configuration hash;
2. evaluation suite hash;
3. policy hash;
4. source benchmark run IDs;
5. metric scorecard;
6. rule outcomes;
7. optional baseline reference;
8. active baseline promotion record;
9. final verdict and decision hash.

Experiment lineage adds a filterable operational timeline across:

1. prompt version creation;
2. benchmark run creation, completion, or failure;
3. gate evaluation completion;
4. baseline promotion;
5. baseline supersession;
6. release decision sign-off.

Signed release decisions add:

1. frozen readiness snapshot JSON;
2. snapshot hash;
3. signer identity and verification state;
4. approval policy state;
5. signature statement and signature hash;
6. operator decision and reason;
7. decision hash;
8. Markdown export for handoff or audit review.

## Sprint 5H-A Trust Registry

`EvidenceTrustRoot` stores one public signing key for one purpose/issuer/key-ID tuple, its trust
tier, validity interval, source metadata, registrar identity, optional predecessor, and stable
registration hash.

`EvidenceTrustRootAction` stores append-only `rotated`, `retired`, or `revoked` lifecycle events.
Status is derived from actions and validity; no mutable status column can erase history.

`SupplyChainTransparencyProof` binds a supply-chain attestation to a managed log key, signed
checkpoint, canonical entry, log position, tree size, inclusion path, reconstructed root, verifier
identity, and stable proof hash.

`ModelSupplyChainAttestation.publisher_trust_root_id` and
`ProductionEvidenceReceipt.collector_trust_root_id` are nullable additive references. Legacy rows
remain readable and are development-scoped until an exact issuer/key/fingerprint match is
registered.

## Sprint 5H-B Trust Sources

`EvidenceTrustSource` stores one immutable JWKS source configuration: name, purpose, issuer, trust
tier, endpoint, allowed algorithms, development HTTP flag, freshness window, enabled state,
registrar identity, configuration hash, and notes.

`EvidenceTrustSourceSync` stores one append-only Preview or Apply attempt. It captures status,
HTTP/fetch/completion metadata, payload hash, observed/candidate/imported/unchanged/rejected key
counts, bounded key metadata, error details, actor identity, and sync hash.

`EvidenceTrustRoot.trust_source_id` and `trust_source_sync_id` preserve immutable import lineage.
Read models derive source status and whether each key is present in the latest successful Apply
snapshot. Remote rotation does not delete or rewrite a prior root.

Relationships:

- one trust source has many append-only sync attempts;
- one successful Apply may import many trust roots;
- one source may own many historical roots, while only keys in its latest Apply are current;
- manually registered roots have null source lineage and retain Sprint 5H-A behavior.

## Sprint 5H-C Browser Identity State

`OIDCBrowserSession` stores a hashed opaque cookie, hashed CSRF token, stable audit hash,
normalized operator identity, provider issuer and optional `sid`, AES-GCM encrypted provider ID
token, authentication/expiry/last-seen times, and optional revocation/logout metadata. Raw browser
secrets are never stored.

`OIDCCacheEntry` stores one discovery or JWKS document per type/source URL. It includes canonical
content hash, provider fetch and original expiry times, refresh count, and the backend instance
that last wrote the row.

Relationships are intentionally soft:

- a browser session does not reference domain evidence or release records; those records preserve
  their own normalized signer snapshots;
- cache entries are transport state and do not replace managed evidence trust roots;
- multiple API replicas resolve the same session/cache rows through PostgreSQL;
- revocation is retained for audit, while expired/revoked rows are never accepted for identity.

## Sprint 5H-D Trust Source Schedules

`EvidenceTrustSourceSchedule` stores one mutable operating policy per immutable trust source. It
contains interval and schedule jitter, retry bounds, next run, run sequence, last job/sync pointers,
consecutive failures, a short-lived lease fingerprint, policy hash, and the latest verified
configurator identity.

`EvidenceTrustSourceSync` adds execution provenance without changing append-only behavior:

- `trigger` distinguishes manual and scheduled work;
- `schedule_id` and `job_id` link policy and durable delivery;
- `attempt_number` distinguishes retry receipts;
- `scheduled_for` preserves the due-window anchor.

Relationships:

- one trust source has zero or one schedule and many immutable sync receipts;
- one scheduled run sequence creates one durable job;
- one durable job can create multiple failed receipts across retries and one terminal result;
- manually initiated receipts keep null schedule/job lineage;
- `last_sync_id` is an indexed operational pointer, while the receipt's schedule/job fields are the
  authoritative lineage.

## Sprint 5H-E Browser Session Lifecycle

`OIDCBrowserSession` adds:

- `provider_session_hash`: SHA-256 correlation value for provider `sid` scope;
- `client_fingerprint`: keyed HMAC-SHA256 over the bounded local client descriptor;
- `provider_token_purged_at`: evidence that retained provider logout material was removed.

The raw provider `sid` and encrypted provider ID token remain usable only while the session needs
RP-initiated logout. Revocation and inactive-session cleanup clear both raw values while retaining
their non-reversible correlation state.

`OIDCBrowserSessionEvent` is an independent lifecycle ledger. It stores the stable session and
subject fingerprints, event type, reason, actor identity snapshot, verification state, bounded
metadata, prior event hash, canonical event hash, and occurrence time. Supported event types are
`issued`, `migrated`, `revoked`, `provider_token_purged`, and `retention_deleted`.

Relationships and retention behavior:

- one browser session can produce many ordered lifecycle events;
- the event `session_id` is intentionally not a foreign key, allowing events to survive session
  retention deletion;
- event hashes are unique and each new event points to the prior event hash for that session;
- cleanup jobs delete only inactive session rows beyond policy and never delete lifecycle events;
- one durable `oidc_session_cleanup` job records the bounded cleanup result in its existing job
  result payload;
- session identity state remains separate from evidence, Gate, trust-root, and release records.

## Sprint 5H-F Operational Reliability

`OperationalMetricSnapshot` stores one interval bucket, generation and expiry timestamps, derived
health, source schema version, metric/alert counts, canonical content hash, and collector identity.
The interval bucket and content hash are both unique.

`OperationalMetricPoint` stores one normalized metric value per snapshot, metric name, and
canonical labels hash. Labels remain structured JSON, and every row retains the metric help text
and recorded timestamp.

`OperationalSLOEvaluation` stores one identity or worker objective per snapshot. It includes
status, target and observed ratios, remaining error budget, window, expected and good sample
counts, detailed actual/missing counts, an evaluation hash, and the source snapshot relation.

`OperationalAlertIncident` stores a derived-alert, SLO, or test lifecycle. One nullable unique
`active_key` permits only one open incident for a signal. Resolution clears that key, records the
resolution timestamp, and preserves occurrence and transition versions.

`OperationalAlertDelivery` is the paging outbox and receipt. It binds an incident transition to a
canonical payload hash, destination hash, optional durable job, status, lifetime attempt count,
bounded response/error evidence, and delivery time.

Relationships and retention:

- one snapshot has many metric points and SLO evaluations;
- deleting an expired snapshot cascades to its normalized points and evaluations;
- one incident has many transition deliveries;
- delivery records retain the incident, job, payload, and response lineage;
- one `operational_observability_cycle` job creates at most one snapshot bucket;
- one `operational_alert_delivery` job owns one delivery row through a unique job reference;
- snapshot retention does not delete incident or paging history.

## Sprint 5H-G Incident Response And Burn Rate

`OperationalSLOEvaluation` adds the short-window duration and observed ratio, long and short burn
rates, and a `none|warning|critical` multi-window alert level. Existing long-window status and
error-budget fields remain intact. Short-window expected, actual, good, and missing counts are
retained in structured details.

`OperationalAlertIncident` adds the current acknowledgement time and verified actor snapshot,
bounded assignee, and escalation level from 0 through 3. These fields are mutable response state;
incident open/resolved constraints and historical recurrence remain unchanged.

`OperationalAlertIncidentAction` is the append-only response ledger. It stores action type,
reason, optional assignee, actor identity snapshot, verification state, occurrence time, previous
action hash, and unique canonical action hash. Actions are `acknowledged`, `assigned`, `note`, or
controller-generated `escalated`.

`OperationalAlertDelivery` adds the non-secret signing key ID and allows the `escalated`
transition. Existing rows migrate to `legacy`. One delivery continues to be unique for an incident,
transition type, and transition version.

Relationships and ownership:

- one incident has many ordered response actions and many transition deliveries;
- response action deletion follows incident deletion, while normal incident history is retained;
- acknowledgement suppresses future automatic escalation but does not resolve an incident;
- assignment updates current owner and appends independent immutable evidence;
- a delivery's signing key ID is fixed at outbox creation and its secret never enters the database.

## Sprint 5H-H Provider Receipt Correlation

`OperationalAlertDelivery` adds nullable `provider_name`, `provider_event_id`,
`provider_receipt_id`, and `provider_accepted_at` fields. They remain null for legacy rows and for
deliveries where strict provider receipts are disabled or not yet accepted.

The provider event ID must equal the delivery UUID before the row can transition to delivered in
strict mode. The provider receipt ID is an external correlation identifier, not a secret or a
release signature. Acceptance time is normalized to UTC and bounded by the configured freshness
policy.

The staging readiness object is a derived API read model rather than a database table. It combines
current deployment configuration with the latest persisted correlated receipt. Readiness does not
mutate delivery, incident, model evidence, Gate, or release records.
