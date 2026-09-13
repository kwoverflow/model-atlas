# Extension Contracts

Sprint 4A defines small, versioned contracts so future evaluation packs can extend Model Atlas without replacing the Gate or Release pipeline. This is intentionally not a plugin marketplace or dynamic code-loading framework.

## Inference Adapter

Every adapter exposes an `AdapterDescriptor`:

```python
AdapterDescriptor(
    adapter_id="openai_compatible",
    adapter_version="openai-compatible-v7",
    display_name="OpenAI-compatible Local Runtime",
    capabilities=frozenset({"text_generation", "structured_output", "tool_call_json", "rag_grounded_generation", "runtime_reliability_trials", "bounded_agent_plan", "operational_memory", "observation_feedback", "bounded_recovery_plan", "human_approval_checkpoint", "usage_metrics"}),
    input_schema_version="evaluation-case-v1",
    output_schema_version="adapter-case-result-v1",
)
```

Required fields:

- `adapter_id`: stable logical identifier;
- `adapter_version`: behavior and implementation contract version;
- `display_name`: operator-facing name;
- `capabilities`: supported execution features;
- `input_schema_version`: accepted case contract;
- `output_schema_version`: emitted result contract.

Current adapters:

- deterministic mock;
- OpenAI-compatible local runtime.

Descriptors are copied into benchmark run runtime config and benchmark result metadata. Gate snapshots aggregate adapter versions.

## Result Scorer

Each scorer has a `ScorerDescriptor`:

```python
ScorerDescriptor(
    scorer_id="tool_call",
    scorer_version="tool-call-scorer-v2",
    method="executable_tool_trace",
    capabilities=frozenset({"tool_selection", "argument_schema", "actual_execution"}),
    input_schema_version="evaluation-case-v1",
    output_schema_version="score-outcome-v1",
)
```

The result metadata records both individual scorer and registry provenance. Legacy custom scorers without a descriptor receive an explicit legacy fallback descriptor so existing integrations remain executable.

## Tool Registry

Sprint 4B adds a bounded registry contract for executable evaluation fixtures. Each
`ToolDescriptor` contains:

- stable tool ID and behavior version;
- display name and description;
- argument and output schemas;
- capabilities;
- side-effect mode (`none` or `simulated`);
- default maximum attempts.

The current registry is static and in-process. It is not a dynamic loader. Adding a production tool
requires a separate security design for credentials, network allowlists, tenancy, data redaction,
timeouts, idempotency, and operator authorization.

## RAG Corpus and Retriever

Sprint 4C adds versioned descriptors for:

- corpus ID, version, hash, language, document count, and chunk count;
- chunk ID, document ID, title, text, and metadata;
- retriever ID/version, capabilities, and input/output schema versions;
- retrieval top-k and minimum-score configuration.

The current registry is static and the retriever is deterministic lexical overlap. Future embedding,
vector database, hybrid, or reranking implementations must publish new versions and preserve the
same result and Gate evidence boundary.

## Runtime Reliability Execution

Sprint 4D defines a concurrency-safe adapter boundary. Adapter configuration and evaluation case
inputs are structural protocols backed by frozen snapshots during execution. A future adapter must:

- treat configuration and case input as read-only;
- be safe for the declared bounded concurrency or document a lower bound;
- honor `_case_timeout_ms` at its external I/O boundary;
- return separate OOM and generic error evidence when available;
- publish latency, token, and memory telemetry provenance;
- preserve deterministic behavior when a seed is supported.

Adapters must not use the SQLAlchemy session or mutate stored cases. A new adapter behavior requires
a descriptor version change. Runtime comparison and Gate metrics consume the canonical trace and do
not depend on adapter-specific fields.

## Bounded Agent Runtime

Sprint 5A composes Tool, RAG, memory, and response actions behind one bounded trace contract. Future
Agent adapters must:

- return one valid plan object without hidden reasoning;
- consume only sanitized `agent_context` bounds and allowlists;
- avoid SQLAlchemy sessions and stored ground-truth contracts;
- declare `bounded_agent_plan` and any memory capability in the adapter descriptor;
- preserve action inputs/outputs needed for semantic replay;
- never authorize release or bypass Tool Registry validation.

Operational-memory registries require stable IDs, behavior versions, content hashes, data
classification, and explicit write mode. Durable memory implementations also require retention,
tenant isolation, deletion, consent, and authorization contracts; the current implementation allows
only read-only fixtures and task-local simulated writes.

Agent replay implementations must identify volatile fields, publish semantic signatures, check
dependency versions, and remain non-persisting unless a separate benchmark execution is requested.

Sprint 5B recovery plans must declare a trigger plan index, optional error allowlist, strategy, and
bounded recovery steps. Executors must preserve the failed triggering step, attach a versioned
observation, enforce the separate replan/recovery budget, and reject recovery from policy or
approval violations.

Approval decisions are executor-side inputs, not model context. Implementations must require actor
and reason, record decision provenance and a stable hash, and enforce `requires_approval` before a
guarded action. Authentication, expiry, and durable pause/resume require a later control-plane
contract and are not implied by the Sprint 5B evidence fields.

## Future Evidence Importer

The future contract should follow:

```python
class EvidenceImporter(Protocol):
    importer_id: str
    importer_version: str
    source_type: str

    def validate(self, payload: object) -> object: ...
    def dry_run(self, payload: object) -> object: ...
    def import_records(self, payload: object) -> object: ...
```

Planned import targets include local JSONL cases, production log exports, Promptfoo output, Langfuse exports, and benchmark CSV files.

Importers must:

- use canonical source values;
- preserve external IDs and provenance;
- support dry-run validation before mutation;
- never create a release decision directly.

## Future Metric Calculator

```python
class MetricCalculator(Protocol):
    metric_id: str
    metric_version: str
    required_fields: set[str]

    def calculate(self, evidence: object) -> object: ...
```

Calculators return versioned metric values and sample sizes. They do not apply acceptance policy or choose a verdict.

## Future Policy Rule Evaluator

The current evaluator supports absolute thresholds. Extension points may add:

- `absolute_threshold`;
- `regression_threshold`;
- `sample_coverage`;
- `critical_case_failure`;
- `evidence_trust`;
- `timeout_or_oom`.

Every rule evaluator must return a deterministic status, severity, details, and version. It may not bypass required-rule insufficiency or critical-case blocking semantics.

## Future Report Renderer

Report renderers may target:

- Markdown;
- PDF;
- JSON.

Renderers consume an immutable stored snapshot. They do not recompute metrics, evidence trust, or verdicts.

## Versioning Rules

1. Descriptor IDs remain stable across compatible versions.
2. Behavior changes require a version change.
3. Input and output schema versions are explicit.
4. Snapshot fields are additive where practical.
5. Legacy records remain readable with an explicit fallback state.
6. Gate and release hashes include the effective provenance fields.
7. Extensions cannot authorize release outside the existing signer and policy path.

## Paging Provider Adapter

An external paging adapter receives the existing HMAC-authenticated event over allowlisted HTTPS.
When strict correlation is enabled, it must return:

```json
{
  "schema_version": "model-atlas-paging-provider-receipt-v1",
  "accepted": true,
  "provider": "configured-provider-id",
  "provider_event_id": "<delivery UUID>",
  "receipt_id": "<provider-owned ID>",
  "accepted_at": "<timezone-aware timestamp>"
}
```

The adapter owns translation to the provider API but cannot replace the Model Atlas event ID,
claim success without provider acceptance, expose signing material, mutate the incident, or grant
release authorization. Provider-specific metadata may be retained externally; only bounded
correlation fields enter the operational delivery record.

## Planned Evaluation Packs

1. Tool Calling: implemented in Sprint 4B with execution correctness, argument validation, failures, recovery, and multi-step sequences.
2. RAG: implemented in Sprint 4C with corpus version, retrieval configuration, citation precision, groundedness, and unsupported claims.
3. Runtime Reliability: implemented in Sprint 4D with repeated trials, bounded concurrency, latency
   percentiles, context stress, timeout/OOM capture, comparison, and Gate rules.
4. Agent Operations: implemented in Sprint 5A with bounded plan execution, versioned memory,
   Tool/RAG composition, semantic replay, and Agent Gate evidence.
5. Adaptive Agent Operations: implemented in Sprint 5B with versioned observations, one-shot
   recovery branches, human checkpoint evidence, guarded actions, and Gate rules.
6. Agent Control Plane: implemented in Sprint 5C with authenticated policy approvers, persistent
   checkpoint transitions, resumable result revisions, expiry/revocation, one-call live-replan
   provider evidence, and production trace import validation.
7. Agent Orchestration: implemented in Sprint 5D with append-only revisions, durable asynchronous
   workers, Gate staleness, strict JWT/trusted-proxy verification, scheduled reconciliation,
   OpenAI-compatible replanning, and signed traffic evidence ingestion.
8. Production Hardening: implemented in Sprint 5E with OIDC discovery/JWKS rotation, worker
   observability/dead-letter operations, a reference collector, stale-release actions, and durable
   local-model validation reports.
9. Model Identity And Monitoring: implemented in Sprint 5F with artifact digest attestation,
   reviewed-label decisions, browser OIDC integration, exported operational metrics, and Tool/RAG
   isolation preflight.
10. Supply Chain And Managed Trust: implemented across Sprint 5G, 5H-A, and 5H-B with signed SBOM
   provenance, purpose-scoped public keys, append-only lifecycle, signed transparency inclusion,
   remote JWKS source lineage, and production eligibility.
11. Shared Browser Identity: implemented across Sprint 5H-C and 5H-E with opaque PostgreSQL
   sessions, CSRF/Origin enforcement, RP-initiated logout, proxy-boundary rejection, shared OIDC
   documents, verified-role containment, provider-token minimization, hash-linked lifecycle
   evidence, and retention cleanup.
12. Managed Trust Operations: implemented in Sprint 5H-D with replica-safe interval policies,
   durable Apply jobs, deterministic retry/dead-letter behavior, and per-attempt receipts.
13. Operational Reliability Evidence: implemented across Sprint 5H-F through 5H-H with
   replica-safe snapshots, missing-interval-aware paired-window SLOs, burn rates, incident response
   actions, automatic escalation, projected rotating-key CA-verified paging, strict provider
   receipts, a staging readiness gate, and controlled outage/recovery verification. Deployment
   against an external secret manager, managed PKI, and real paging provider remains target-
   environment work; target GPU evidence and per-job Kubernetes sandboxing also remain future
   work.

Each pack should add evidence and policy rules through these contracts while reusing the current Preflight, Gate, Release Readiness, frozen decision, and lineage layers.
