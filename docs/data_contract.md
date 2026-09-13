# Data Contract

The API and database enforce a practical Sprint 1 contract for benchmark metadata and local analytics.

## Validation Rules

1. Benchmark runs cannot reference inactive model artifacts.
2. Benchmark results cannot exist without a valid benchmark run.
3. Latency must never be negative.
4. Tokens per second must never be negative.
5. GPU VRAM usage must not significantly exceed the registered hardware VRAM.
6. If `json_valid` is true, `normalized_output` must be valid JSON.
7. If `tool_call_valid` is true, `normalized_output` must be a valid JSON object containing `tool_name`, `tool_call`, or `tool_calls`.
8. A benchmark run must include `runtime_name` and `runtime_config_json`.
9. A model artifact must reference an existing model.
10. Required timestamps must use UTC.
11. Recommendation scoring weights must be between 0 and 1, with at least one weight greater than 0.
12. Gate-related benchmark runs should reference both a deployment configuration and evaluation suite.
13. Gate-related benchmark results should reference an active evaluation case from the run suite.
14. Deployment configuration hashes are generated from canonicalized semantic configuration fields.
15. A local-only workload cannot be paired with an explicitly remote runtime configuration.
16. Benchmark execution adapters must persist raw outputs, normalized outputs, metrics, and runtime logs through existing benchmark lineage.
17. Only completed `APPROVED` gate evaluations can be promoted as active deployment baselines.
18. Explicit baseline gate evaluations must match the requested deployment configuration, evaluation suite, and acceptance policy.
19. Prompt regression reports read completed benchmark evidence and do not create or mutate decision records.
20. Auto-filled benchmark result scores must store scorer provenance in `metadata_json.scorer`.
21. Experiment lineage events must be idempotent by event type and primary entity ID.
22. Release readiness snapshots are derived views and must not mutate gate, baseline, benchmark, or judge-label records.
23. `APPROVE_RELEASE` decisions require readiness status `READY` or `READY_TO_PROMOTE`; other readiness states can only be signed as `REQUEST_CHANGES` or `REJECT_RELEASE`.

Pydantic handles API-boundary validation. Service functions handle cross-record validation. Database constraints protect non-negative metric and score ranges where appropriate.

## Synthetic Data Policy

All Sprint 1 seed benchmark data is synthetic demonstration data. Seeded benchmark runs, benchmark results, and inference metrics use:

```text
data_source = synthetic_demo
```

Seeded model metadata is plausible demonstration metadata, not a guarantee about any real artifact, model weights, benchmark dataset, or runtime behavior.

Deployment Gate has a stronger synthetic-data rule:

```text
synthetic_demo evidence may demonstrate the workflow,
but synthetic-only evidence can never produce APPROVED.
```

## API Data Expectations

- IDs are UUIDs.
- Timestamps are timezone-aware UTC values.
- Runtime configuration is JSON.
- Output schemas and metadata are JSON objects where supplied.
- List endpoints support bounded pagination with `limit` and `offset`.
- Benchmark runs can be filtered by model artifact, task, and hardware profile.
- Inference metrics can be filtered by benchmark run.

## Benchmark Record Requirements

Every benchmark run should identify:

- hardware profile;
- model artifact;
- benchmark task;
- prompt version;
- runtime name;
- runtime configuration;
- dataset version;
- seed where reproducibility requires it;
- status and failure reason where relevant.

Every result should identify:

- benchmark run;
- sample ID;
- quality or validation outcomes;
- raw and normalized outputs when available;
- metadata needed to interpret the sample.

Every inference metric should identify:

- benchmark run;
- sample ID;
- latency and throughput values;
- token counts;
- memory and utilization values when available.

## Recommendation Requirements

Recommendation reports are deterministic projections over existing catalog, hardware, benchmark, result, and metric records. They do not create benchmark data and do not infer missing measurements.

Hard filters exclude artifacts when:

- the artifact is inactive;
- registered VRAM requirements exceed the selected hardware VRAM;
- required context length is not met;
- required model capabilities are missing;
- commercial use is required but not allowed;
- no benchmark evidence exists for the selected scope.

Scores combine normalized quality, latency, throughput, and VRAM efficiency. The raw weighted score is then multiplied by evidence confidence:

```text
evidence_confidence = min(1, sqrt(benchmark_coverage_count / 3))
recommendation_score = raw_recommendation_score * evidence_confidence
```

The denominator `3` is the current target number of benchmark runs per candidate scope. Pareto flags compare eligible artifacts across quality, latency, throughput, and VRAM usage; Pareto membership is based on measured tradeoffs, not the confidence-adjusted score.

Recommendation scenarios persist a named `RecommendationRequest` as JSON. A scenario must include:

- a non-empty name;
- optional description;
- hardware and task filters where selected;
- hard filter flags;
- `top_k`;
- scoring weights.

Scenario replay uses the saved request as-is and generates a fresh report from the current stored benchmark evidence.

Scenario updates may change the name, description, or saved request JSON. Scenario deletion removes only the saved request record; it does not delete catalog, benchmark, result, metric, or report data.

Markdown and PDF exports are derived from the current generated report. They do not create a new database record and should be treated as shareable renderings of the API response at request time.

## Deployment Gate Requirements

Gate evaluations are deterministic decisions over stored evidence. They use absolute policy thresholds, not relative recommendation scores.

Valid verdicts are:

- `APPROVED`
- `CONDITIONAL`
- `BLOCKED`
- `INSUFFICIENT_EVIDENCE`

Missing required metric data produces a rule status of `insufficient`. If any required rule is insufficient, the final verdict is `INSUFFICIENT_EVIDENCE`.

Verdict priority:

1. Synthetic-only or missing mandatory evidence: `INSUFFICIENT_EVIDENCE`.
2. Blocker rule failure: `BLOCKED`.
3. Critical case failure: `BLOCKED`.
4. Warning rule failure: `CONDITIONAL`, or `BLOCKED` if the policy disallows conditional approval.
5. Otherwise: `APPROVED`.

Gate reports must preserve benchmark run IDs, configuration hash, suite hash, policy hash, metric values, rule outcomes, baseline reference, verdict, and decision hash.

Deployment baselines are scoped by deployment configuration, evaluation suite, and acceptance policy.
Only one active baseline should exist per scope. Promoting a new baseline supersedes the previous
active baseline and records the superseding baseline ID. When a gate request omits
`baseline_gate_evaluation_id`, the active baseline for the same scope is used automatically.

## Prompt Regression Report Requirements

Prompt regression reports group completed benchmark runs by prompt version and aggregate the same
stored result and inference metric evidence used by the gate. They may be filtered by deployment
configuration, evaluation suite, and acceptance policy. Baseline deltas are included only when all
three scope identifiers are supplied and an active deployment baseline exists for that exact scope.

Risk flags are advisory review signals. They highlight quality regression, latency regression,
critical-case failures, OOM risk, and low sample size, but they do not replace the Deployment Gate
verdict or mutate benchmark, baseline, or gate records.

## Experiment Lineage Requirements

Experiment lineage events are append-only traceability records. They connect:

- prompt version creation;
- benchmark run creation, completion, or failure;
- gate evaluation completion;
- baseline promotion;
- baseline supersession;
- release decision sign-off.

Each event stores a primary entity, event time, lineage key, optional deployment/suite/policy/prompt
scope, optional run/gate/baseline/release-decision links, summary, metadata, status, and data
source. The lineage API may materialize missing events from existing records, but this process is
idempotent and does not mutate benchmark results, gate decisions, baseline records, or release
decisions.

## Release Readiness Requirements

Release readiness snapshots are generated from existing gate evaluations. They summarize:

- Deployment Gate verdict and rule outcomes;
- active deployment baseline state;
- judge-label calibration coverage;
- prompt regression risk flags;
- experiment lineage events;
- next actions from the gate scorecard plus snapshot-level review actions.

Snapshot statuses are `READY`, `READY_TO_PROMOTE`, `NEEDS_REVIEW`, `BLOCKED`, or
`INSUFFICIENT_EVIDENCE`. The snapshot may be exported as Markdown, but it is not itself a signed
approval record and does not supersede the Deployment Gate verdict.

## Release Decision Requirements

Release decisions are signed records created from a generated readiness snapshot. Each record stores:

- gate evaluation ID;
- deployment configuration, evaluation suite, and acceptance policy scope;
- decision value: `APPROVE_RELEASE`, `REQUEST_CHANGES`, or `REJECT_RELEASE`;
- readiness status at sign-off time;
- signer identity, identity verification state, approval policy state, signature statement, and reason;
- frozen readiness snapshot JSON;
- snapshot hash;
- signature hash;
- decision hash;
- decision timestamp.

The frozen snapshot can be exported as `snapshot.json`. The snapshot diff endpoint compares that
stored JSON with a newly generated readiness snapshot for the same gate evaluation. It reports
path-level `added`, `removed`, and `changed` items, ignores volatile `generated_at`, and caps the
visible diff list at 200 items while preserving the full diff count.

`APPROVE_RELEASE` is accepted only when the generated snapshot status is `READY` or
`READY_TO_PROMOTE`, the signer identity is verified, and the signer has one of the approved release
roles. `REQUEST_CHANGES` is allowed for any status so incomplete or blocked releases can still leave
an auditable review record. `REJECT_RELEASE` also requires verified release-role authority.
Release decisions do not edit gate
evaluations, baselines, benchmark runs, prompt regression reports, judge-label rows, or lineage
events. Creating a release decision also records a `release_decision_signed` lineage event in the
same transaction so the operational timeline and sign-off history stay aligned.

Signer identity is normalized into `signer_identity_json`. Local UI submissions are stored as
`auth_source = self_attested` and `identity_verified = false`. If an upstream authentication proxy
or middleware supplies trusted headers, the API stores `auth_source = trusted_header` and
`identity_verified = true`.

`release-approval-rbac-v1` is evaluated before the record is persisted. `APPROVE_RELEASE` and
`REJECT_RELEASE` require verified identity and one of `Release Manager`, `ML Ops Lead`,
`Model Governance`, or `Admin`. `REQUEST_CHANGES` can be recorded by a local self-attested reviewer
so follow-up work is not blocked by auth rollout.

Trusted identity headers:

- `x-model-atlas-operator-id`
- `x-model-atlas-operator-name`
- `x-model-atlas-operator-role`
- `x-model-atlas-identity-provider`

The `signature_hash` binds the signer identity, decision, readiness status, frozen snapshot hash,
gate decision hash, signature statement, reason, notes, and decision timestamp. The `decision_hash`
then includes the approval policy result and signature hash so the final release decision record has
a stable audit fingerprint.

## Benchmark Execution Requirements

Benchmark execution is adapter-driven. Sprint 3B starts with:

- `mock`: deterministic local execution for tests and UI workflow validation.
- `openai_compatible`: local OpenAI-compatible HTTP runtime adapter.

`openai_compatible` accepts request-level adapter config:

```json
{
  "adapter_config_json": {
    "base_url": "http://host.docker.internal:1234",
    "model": "loaded-local-model-name"
  }
}
```

If `model` is omitted, the adapter uses the first model returned by `/v1/models`, then falls back to the configured model artifact name.

Execution creates:

- one suite-linked `BenchmarkRun`;
- one `BenchmarkResult` per active case executed;
- one `InferenceMetric` per executed case;
- runtime `BenchmarkExecutionLog` records.

If an adapter omits quality labels, benchmark execution applies the local deterministic scorer and
stores the scorer version, registry ID, scorer ID, method, and details in
`BenchmarkResult.metadata_json.scorer`.

## Production-Captured Import Requirements

Captured case imports accept JSONL, JSON, or CSV rows. Required fields:

- `external_case_id`
- `category`
- `input` or `input_payload_json`

Optional fields:

- `title`
- `expected_output` or `expected_output_json`
- `reference_context` or `reference_context_json`
- `expected_tool_schema` or `expected_tool_schema_json`
- `criticality`
- `weight`
- `tags`
- `judge_labels`

Imported suites are always non-synthetic. Rows using `data_source = synthetic_demo` are rejected.
When `judge_labels` are present on case rows, they are preserved under
`reference_context_json.judge_labels` for scorer calibration context.

Judge label imports match completed benchmark results by `sample_id` or `external_case_id`. Dry-run
mode reports match counts and score deltas. `--apply` updates `quality_score`,
`groundedness_score`, `faithfulness_score`, `human_label`, and
`metadata_json.judge_label`.

The judge-label review API reports, per benchmark result, whether the current score came from an
applied judge label, a case-level candidate judge label, the deterministic scorer, a raw label, or no
label. Rows with candidate labels that have not been applied, missing scores, or review-needed labels
are surfaced for calibration before gate evidence is treated as operationally mature.

The dashboard import API accepts JSONL, JSON, and CSV file content, runs the same validation as the
CLI importer, and applies labels only when `apply_labels = true`. Dry-run requests report matches,
missing samples, quality-label coverage, and average absolute quality delta without mutating stored
benchmark results.

The execution API does not itself approve deployment. It only creates evidence. Deployment approval still requires a Gate Evaluation.

## Sprint 4A Evidence Trust Contract

### Canonical source values

New evidence should use one of:

```text
synthetic_demo
local_authored
production_captured
external_benchmark
unknown
```

Read-time normalization is centralized:

```text
captured_local -> local_authored
missing or unsupported value -> unknown
```

`captured_local` remains readable for existing records, but new UI benchmark execution defaults to `local_authored`. `human_reviewed` is never a source tier; it is score provenance.

### Score provenance priority

`BenchmarkResult.metadata_json` is interpreted in this order:

1. Explicit human-review provenance -> `human_reviewed`.
2. `metadata_json.judge_label.applied = true` -> `applied_judge_label`.
3. Case-level `reference_context_json.judge_labels` -> `candidate_judge_label`.
4. Scorer ID or version -> `heuristic`.
5. Otherwise -> `unknown`.

Stronger markers win when several are present. A populated `human_label` string alone does not prove human review.

### Adapter provenance

Benchmark run runtime config and result metadata can include:

```json
{
  "adapter_descriptor": {
    "adapter_id": "openai_compatible",
    "adapter_version": "openai-compatible-v6",
    "display_name": "OpenAI-compatible Local Runtime",
    "capabilities": ["citation_json", "multi_step_tool_calling", "rag_grounded_generation", "runtime_reliability_trials", "structured_output", "text_generation", "tool_call_json", "usage_metrics"],
    "input_schema_version": "evaluation-case-v1",
    "output_schema_version": "adapter-case-result-v1"
  }
}
```

### Scorer provenance

`metadata_json.scorer` contains the individual scorer and registry versions:

```json
{
  "scorer_id": "json_schema",
  "scorer_version": "json-schema-scorer-v1",
  "registry_id": "default_heuristic_registry",
  "registry_version": "heuristic-scorer-v5",
  "method": "json_schema_coverage",
  "capabilities": ["json_schema", "structured_output"],
  "input_schema_version": "evaluation-case-v1",
  "output_schema_version": "score-outcome-v1"
}
```

### Snapshot schema policy

- Gate evidence snapshots created by Sprint 5B use `gate-evidence-snapshot-v7`.
- Sprint 5A `gate-evidence-snapshot-v6` records remain readable.
- Sprint 4D `gate-evidence-snapshot-v5` records remain readable.
- Sprint 4C `gate-evidence-snapshot-v4` records remain readable.
- Sprint 4B `gate-evidence-snapshot-v3` records remain readable.
- Sprint 4A `gate-evidence-snapshot-v2` records remain readable.
- Release readiness snapshots use `release-readiness-snapshot-v2`.
- Existing fields are not removed.
- New fields are additive.
- Missing trust fields in legacy snapshots must produce an explicit legacy or unknown state, not an exception.
- Canonical hashes continue to use sorted, compact JSON with stable string conversion.

## Sprint 4B Executable Tool Contract

Tool cases continue to use `EvaluationCase.expected_tool_schema_json`. A single-step contract uses:

```json
{
  "tool_name": "lookup_policy",
  "arguments": {
    "type": "object",
    "required": ["query"],
    "properties": {"query": {"type": "string"}},
    "additionalProperties": false
  },
  "example_arguments": {"query": "Check release policy"},
  "max_attempts": 2
}
```

A multi-step contract uses `expected_sequence`, where each item has its own `tool_name`, argument
schema, optional fixture arguments, and optional attempt limit. Legacy `required_arguments` remains
readable and is normalized to an object schema.

`BenchmarkResult.metadata_json.tool_execution` stores `tool-execution-trace-v1` with:

- parser and call validity;
- expected and actual tool sequences;
- selection, argument, execution, and retry-recovery rates;
- one step per call;
- bounded attempt records;
- output validation, output payload, and failure classification;
- registry and trace schema versions.

`metadata_json.tool_registry` stores the effective registry descriptor. Benchmark run runtime config
also records the registry descriptor when the selected suite contains tool cases.

Gate evidence snapshot v3 aggregates:

```json
{
  "tool_registry_versions": ["local-tool-registry-v1"],
  "tool_execution_versions": ["tool-execution-trace-v1"]
}
```

No new database table is required. Trace records are immutable evidence inside the existing result
metadata and execution-log ownership boundary.

## Sprint 4C RAG Contract

The immutable deployment configuration activates retrieval through:

```json
{
  "retrieval_config_json": {
    "corpus_id": "model-atlas-ops-handbook",
    "corpus_version": "ops-handbook-v1",
    "corpus_hash": "...",
    "retriever_id": "lexical_overlap",
    "retriever_version": "lexical-overlap-v1",
    "top_k": 3,
    "min_score": 0.05
  }
}
```

RAG case ground truth uses `reference_context_json.rag` with corpus ID/version, query, and
`relevant_chunk_ids`. Legacy `rag-evidence-contract-v1` treats that list as one required group.
`rag-evidence-contract-v2` may add equivalent evidence choices:

```json
{
  "evidence_contract_version": "rag-evidence-contract-v2",
  "relevant_chunk_ids": ["primary-a", "primary-b"],
  "acceptable_evidence_groups": [
    ["primary-a", "primary-b"],
    ["alternative-c"]
  ]
}
```

Every chunk within a group is required, while any one complete group satisfies the contract. The
first group must exactly equal `relevant_chunk_ids`, groups and IDs must be unique, and every ID must
resolve in the locked corpus. Retrieval recall, evidence-selection recall, and citation recall use
the best-covered group. Citation precision accepts only IDs in the union of declared groups. The
adapter-facing copy removes every expected group and contains only retrieved chunks.

RAG semantic ground truth uses `EvaluationCase.expected_output_json`. Legacy
`rag-semantic-contract-v1` treats `required_facts` as one required group.
`rag-semantic-contract-v2` may declare reviewed alternatives while preserving the legacy list as
the primary group:

```json
{
  "semantic_contract_version": "rag-semantic-contract-v2",
  "required_facts": ["primary fact"],
  "acceptable_required_fact_groups": [
    ["primary fact"],
    ["reviewed alternative fact"]
  ]
}
```

Every fact within a group is required, while any one complete group satisfies the contract. The
first group must exactly equal `required_facts`; groups and facts must be non-empty and unique.
Required-fact coverage reports the best-covered group and records the satisfied group index.

`BenchmarkResult.metadata_json.rag_evaluation` stores `rag-evaluation-trace-v5`, including:

- nested `rag-retrieval-trace-v3`;
- evidence-contract version, acceptable groups, matched group indexes, and contract satisfaction;
- retrieved rank, score, chunk text, and corpus/retriever provenance;
- deterministic sentence-selector ID/version, selected source rank, selected claim, confidence,
  abstention recommendation, and selection recall;
- output validity, answer, citations, and claims;
- citation precision/recall;
- claim support scores and groundedness;
- unsupported claim count/rate;
- `must_refuse`, refusal detection, and refusal-requirement status;
- semantic-contract version, acceptable required-fact groups, per-group results, best-group fact
  matches, required-fact coverage, and satisfied group index;
- forbidden claims, per-claim match details, and violation count;
- bounded-answer contract version, strategy, application state, and exact-match state;
- aggregate semantic-contract status.

RAG semantic ground truth is supplied to the evaluator only after generation. The adapter request
contains the public query, retrieved chunks, and retrieved citation candidates, but never expected
relevant chunk IDs, required facts, or forbidden claims. OpenAI-compatible RAG requests use a strict
three-field JSON schema when supported by the runtime. For `rag_version_or_scope` and
`insufficient_evidence_refusal`, `lexical-sentence-selector-v1` chooses one sentence from the
retrieved top-k set using only public query and chunk data. The selected citation and exact source
claim become schema enums. Scope and refusal cases additionally receive a bounded answer enum from
`rag-bounded-answer-contract-v1`, derived only from the public query and selected source claim.
Scope answers state only the selected evidence boundary and forbid extrapolation to performance,
approval, identity, or operational status. Refusal answers preserve the bounded refusal form. The
compiler never receives required facts, forbidden claims, or evaluator-only ground truth.
`rag-evaluation-scorer-v5` records the same semantic- and answer-contract decisions in score
details. `openai-compatible-v17` consumes the prepared public contract. Historical traces remain
readable through additive schema defaults.

`metadata_json.rag_corpus` and `metadata_json.retriever_descriptor` preserve the effective
implementation contracts. Benchmark run runtime configuration also stores the evidence-selector,
RAG evidence-contract, semantic-contract, and bounded-answer descriptors when RAG cases are present.
Gate evidence snapshot v4 aggregates corpus, retriever, and RAG trace versions. Existing database
columns and canonical hash rules remain unchanged.

## Sprint 4D Runtime Reliability Contract

Benchmark execution reliability controls are additive:

```json
{
  "reliability_mode": true,
  "trials_per_case": 5,
  "concurrency": 4,
  "case_timeout_ms": 2000
}
```

- `trials_per_case`: integer from 1 through 20;
- `concurrency`: integer from 1 through 16;
- `case_timeout_ms`: integer from 100 through 300,000;
- repeated/concurrent options require `reliability_mode=true`;
- a run may contain at most 5,000 planned trials.

Each repeated result and inference metric uses `<external_case_id>::trial-XX`. The suffix is
preserved when the external ID must be trimmed to the existing 120-character sample-ID limit.

`BenchmarkResult.metadata_json.runtime_reliability` stores
`runtime-reliability-trace-v1`:

```json
{
  "schema_version": "runtime-reliability-trace-v1",
  "benchmark_run_id": "...",
  "external_case_id": "runtime-rel-001",
  "trial_index": 2,
  "total_trials": 5,
  "concurrency": 4,
  "case_timeout_ms": 2000,
  "status": "success",
  "successful": true,
  "within_timeout": true,
  "ttft_ms": 108,
  "end_to_end_latency_ms": 650,
  "tokens_per_second": 196.9,
  "oom_occurred": false,
  "context_tokens": 1024,
  "context_window_tokens": 32768,
  "context_utilization_ratio": 0.0313,
  "context_stress": false
}
```

Status values are `success`, `timeout`, `oom`, or `error`. OOM has precedence over timeout, and
timeout has precedence over a generic error. Adapter errors captured in reliability mode must store
an error type and message.

`runtime-reliability-summary-v1` includes:

- observed and expected trial counts;
- success, timeout, OOM, and generic error counts/rates;
- P50/P95/P99 end-to-end latency and P50/P95 TTFT;
- mean throughput;
- mean per-run/per-case latency coefficient of variation;
- trial coverage and per-case coverage bounds;
- context-stress trial count and success rate;
- trace versions.

Gate evidence snapshot v5 adds:

```json
{
  "runtime_reliability_versions": ["runtime-reliability-trace-v1"]
}
```

The metric aggregation value `p99` is valid after Alembic revision `202607110001`. Existing
benchmark and evidence tables are unchanged.

## Sprint 5A Bounded Agent Contract

Agent ground truth is stored in `EvaluationCase.reference_context_json.agent`:

```json
{
  "agent": {
    "max_steps": 4,
    "allowed_actions": ["memory_read", "retrieve", "tool", "respond"],
    "allowed_memory_ids": ["memory-release-guardrails"],
    "allowed_tools": ["lookup_policy"],
    "allow_memory_write": false,
    "expected_steps": [
      {"action": "memory_read"},
      {"action": "retrieve", "relevant_chunk_ids": ["ops-release-001"]},
      {"action": "tool", "tool_name": "lookup_policy", "arguments": {}},
      {"action": "respond", "required_terms": ["approved deployment gate"]}
    ]
  }
}
```

Real adapter input does not receive `expected_steps`, relevant chunk IDs, or required response
terms. It receives `agent_context` with only:

- `agent-context-v1` schema version;
- effective step and per-action limits;
- allowed action, memory, and tool IDs;
- task-local memory-write permission;
- memory, tool, corpus, and retriever versions/configuration.

The adapter returns one JSON object with a `steps` array. Step action values are `memory_read`,
`retrieve`, `tool`, `memory_write`, and `respond`.

`BenchmarkResult.metadata_json.agent_execution` stores `agent-execution-trace-v1`. Required trace
fields include:

- parse, plan, sequence, task, and final-response state;
- expected/actual action sequence and effective step limit;
- step, tool, retrieval, memory, retry, recovery, and violation counts;
- operational-memory, tool, corpus, retriever, context, and trace versions;
- one structured record per executed step;
- memory provenance counts and task-local write state.

`BenchmarkResult.metadata_json.operational_memory_registry` stores the effective registry descriptor
with memory IDs, versions, classifications, tags, and content hashes. Memory write outputs must use:

```json
{
  "scope": "task_local_simulated",
  "persisted": false
}
```

`agent-execution-summary-v1` aggregates case and step outcomes. Non-Agent runs receive an additive
empty summary.

Semantic replay responses contain original and replay trace objects, version compatibility,
timing-normalized SHA-256 signatures, deterministic match, and changed JSON paths. Replay does not
create a Benchmark Result, metric, log, Gate, or release record.

Gate evidence snapshot v6 adds:

```json
{
  "agent_runtime_versions": ["bounded-agent-runtime-v1"],
  "agent_execution_versions": ["agent-execution-trace-v1"],
  "operational_memory_registry_versions": ["operational-memory-registry-v1"]
}
```

Sprint 5A uses existing JSON evidence columns and requires no database migration.

## Sprint 5B Adaptive Agent Contract

`BenchmarkExecutionCreate.agent_approval_decisions` is an additive map keyed by checkpoint ID. A
decision contains `decision` (`approved` or `denied`), `decided_by`, and `reason`. Missing entries
are pending. The request accepts at most 20 entries and stores validated decisions in
`BenchmarkRun.runtime_config_json.agent_approval_decisions`; they are excluded from adapter input.

Agent context v2 adds:

- `execution_step_limit`, `replan_limit`, and `recovery_step_limit`;
- `approval_checkpoint_limit` and `allowed_checkpoint_ids`;
- observation, recovery-policy, and approval-policy versions;
- `approval_decision_mode=external_request_only`.

The plan may add `approval_checkpoint`, `requires_approval`, and `recovery_plans`. A recovery branch
contains `trigger_step_index`, optional `on_error_types`, strategy, and a bounded `steps` array.
Ground-truth `expected_recovery_plans` remain in the stored case and are not sent to a real adapter.

`agent-execution-trace-v2` adds:

- runtime, observation, recovery-policy, and approval-policy versions;
- total execution and replan limits;
- observation, replan, and recovery counts;
- approval approved, denied, pending, and provenance counts;
- unrecovered failure count and halt reason;
- step phase, parent index, observation, approval provenance, and `recovered_by_replan`;
- structured replan events with trigger observation and recovery sequence evidence.

`agent-execution-summary-v2` adds replan, recovery, approval, pending, observation coverage,
unrecovered failure, and halted-case aggregates. Trace v1 remains readable through additive schema
defaults.

Gate evidence snapshot v7 adds:

```json
{
  "agent_runtime_versions": ["bounded-agent-runtime-v2"],
  "agent_execution_versions": ["agent-execution-trace-v2"],
  "agent_observation_versions": ["agent-observation-v1"],
  "agent_recovery_policy_versions": ["bounded-recovery-policy-v1"],
  "agent_approval_policy_versions": ["human-checkpoint-policy-v1"],
  "operational_memory_registry_versions": ["operational-memory-registry-v1"]
}
```

Sprint 5B also uses existing benchmark run/result JSON columns and requires no database migration.

## Sprint 5C Agent Control Plane Contract

Alembic revision `202607130001` adds `agent_approval_checkpoints`. Its lifecycle status is one of:

```text
pending | approved | denied | revoked | expired | resumed
```

The record binds `benchmark_run_id`, `benchmark_result_id`, and logical `checkpoint_id` to:

- requester identity and frozen request snapshot;
- frozen `agent-control-approval-rbac-v1` policy;
- request hash and expiry;
- decision, approver identity, reason, timestamp, verification state, and hash;
- revocation identity, reason, timestamp, and hash;
- resume identity, timestamp, and hash;
- positive optimistic-lock `version`.

`(benchmark_result_id, checkpoint_id)` is unique. Mutations require `expected_version`. The secure
default policy requires a verified trusted-header identity, an allowlisted role, separation of
duties, and a 3,600-second expiry. Workload Agent contracts may narrow defaults globally through
`approval_policy` or per checkpoint through `approval_policies`.

`BenchmarkResult.metadata_json.agent_control_plane` uses `agent-control-plane-link-v1` and stores
record IDs, request hashes, `result_revision`, last transition, transition time, and operator
identity. Resume reuses the stored normalized plan, updates the existing result and metric, and
increments the revision. It never reruns the original adapter.

Optional live replan fields are additive to Agent trace and summary v2:

- callback and model-call count;
- prompt and completion tokens;
- model-call latency and estimated cost;
- provider, provider version, model, callback duration, and semantic response hash on the replan
  event.

The callback requires `allow_replanning=true`, `allow_live_replanning=true`, no matching
predeclared branch, and unused one-replan and one-live-call budgets. Recovery actions still pass all
normal executor contracts.

`production-agent-evidence-import-v1` accepts a target production-captured run, case, sample ID,
stored plan output, trace, metrics, and provenance envelope. The source trace hash is calculated
from the normalized Pydantic trace contract. Import requires verified RBAC identity and rejects:

- unsupported trace versions or mismatched case identity;
- inconsistent step count or exceeded replan limits;
- pending checkpoints;
- approved checkpoints without verified persisted provenance;
- mock or fixture live-replan provider provenance;
- invalid plan JSON;
- duplicate sample or source event IDs;
- trace-hash mismatch.

Accepted imports create one `BenchmarkResult`, one `InferenceMetric`, and one
`BenchmarkExecutionLog`, all labeled `production_captured`, with importer identity, source trace
hash, and envelope evidence hash.

## Sprint 5D Agent Orchestration Contract

Alembic revision `202607130002` adds append-only revision lineage.

`BenchmarkRun` adds:

- `parent_benchmark_run_id`, `root_benchmark_run_id`, and positive `revision_number`;
- `revision_reason`;
- `evidence_revision_hash`.

`BenchmarkResult` adds equivalent parent/root/result revision links and an evidence revision hash.
The original checkpoint result remains unchanged. Resume creates a child run/result/metric and
stores the child IDs on `AgentApprovalCheckpoint.transition_benchmark_run_id` and
`transition_benchmark_result_id`. `agent-control-plane-link-v2`, `agent-resume-event-v2`, and
`agent-evidence-revision-v1` describe this transition.

`agent_execution_jobs` uses `agent-durable-job-v1` and stores:

- type: `resume_checkpoint`, `checkpoint_reconciliation`, or `traffic_evidence_import`;
- status: `queued`, `leased`, `running`, `completed`, `failed`, or `cancelled`;
- unique dedupe key and normalized payload;
- requested identity snapshot and optional run/result/checkpoint links;
- priority, availability, attempts, and bounded attempt limit;
- lease owner/token/expiry plus creation/start/completion timestamps;
- result JSON or bounded last error.

Gate evidence snapshot v8 adds a latest-root-revision manifest and
`evidence_revision_hash`. `GateEvaluation` adds `stale_at`, `stale_reason`, and
`superseded_by_gate_evaluation_id`; status now also accepts `stale`. Stale evaluations cannot be
promoted and block Release Readiness until a new evaluation supersedes them.

Verified bearer identity uses a strict HS256 JWT contract with required `exp`, optional configured
issuer/audience, `nbf`/`iat` validation, fixed algorithm, static `kid` key selection, and configured
name/role claims. Trusted operator headers are valid only when the direct client matches
`TRUSTED_PROXY_NETWORKS`; invalid bearer tokens never fall back to headers.

`production-agent-traffic-batch-v1` contains source system, batch ID, collector version, capture
time, and one or more production evidence events. `hmac-sha256-v1` signs the canonical normalized
JSON. The queued job stores a signature hash, not the secret. Worker import is atomic across all
events in the batch.

OpenAI-compatible live replan mode adds runtime configuration keys for base URL, model, timeout,
max tokens, API-key environment name, and optional input/output token prices. Secrets are excluded
from persisted runtime configuration. Semantic replay reconstructs the recorded live recovery and
does not repeat an external model call.

## Sprint 5E Operational And Validation Contract

Alembic revisions:

```text
202607170001 worker operations
202607170002 traffic collector receipts
202607170003 release operations
202607170004 model validation job type
```

`agent_execution_jobs` now also accepts `model_validation_campaign`. Worker-operation fields add:

- `last_heartbeat_at` and `heartbeat_count`;
- `dead_lettered_at` and bounded `dead_letter_reason`;
- `requeue_count`, `last_requeued_at`, and requeue identity snapshot.

`agent_worker_states` stores worker ID, online/stopped state, start and last-seen timestamps,
current job, processed/completed/failed counters, and metadata. Offline status is computed at read
time from the configured last-seen threshold.

`agent_traffic_receipts` binds source, batch, nonce, signature version/hash, key ID, collector
version, capture/sent/received timestamps, replay count, and durable job ID. Source/batch and
source/nonce pairs are unique.

Traffic signature `hmac-sha256-v2` covers:

```json
{
  "source_system": "production-agent-runner",
  "key_id": "2026-07",
  "nonce": "collector-generated-id",
  "sent_at": "2026-07-17T00:00:00Z",
  "batch": {}
}
```

`ReleaseDecision` adds an optional replacement decision ID. `release_decision_actions` stores
append-only action type, dedupe key, actor identity, reason, source Gate, replacement decision,
metadata, and occurrence time. Action types are:

```text
stale_detected | review_requested | acknowledged | revoked | replaced
```

`ModelValidationCampaignCreate` extends benchmark execution with a campaign key and canonical
source values. Raw credential-like fields are rejected recursively. Only
`api_key_env=OPENAI_COMPATIBLE_API_KEY` is accepted as a persisted credential reference.

`model-validation-report-v1` contains:

- scope and optional focus run;
- configured artifact and observed runtime models;
- model identity match (`true`, `false`, or unknown);
- actual-runtime and release-authorized flags;
- evidence revision and report hashes;
- source cohorts and comparisons;
- judge calibration;
- canonical Evidence Trust;
- recommendations and limitations.

The report is a read model, not a new evidence table. Durable jobs may store a frozen copy in
`result_json`; GET report endpoints recompute from current latest-revision evidence.

OIDC JWT configuration accepts an algorithm allowlist, static HS256 keys, discovery URL or direct
JWKS URI, cache TTLs, HTTP timeout, and an insecure-HTTP development flag. Supported algorithms are
strictly `HS256` and `RS256`.

## Sprint 5F Artifact, Review, Identity, Metrics, And Isolation Contract

Alembic revisions:

```text
202607200001 model artifact attestations
202607200002 judge label review decisions
202607200003 traffic receipt timestamp alignment
```

`ModelArtifactAttestation` binds one artifact to a normalized runtime manifest, exact SHA-256
digest, source URI, runtime model name, verification method, status, attestation time, verified
actor identity, notes, manifest hash, and stable attestation hash. Repeated identical observation is
idempotent. A generated deployment configuration stores:

```json
{
  "model": "qwen2.5:0.5b",
  "model_digest": "sha256:a8b0c515...",
  "artifact_attestation_hash": "0b991aac..."
}
```

`model-validation-report-v2` adds observed digests, configured digest, attestation ID/status, and
digest-aware model matching. Attestation status is:

```text
missing | verified | digest_mismatch | model_mismatch
```

`JudgeLabelReviewDecision` is append-only and stores decision type, candidate-label hash,
prior/applied score snapshots, applied flag, reviewer identity, identity verification, rationale,
case criticality, review time, and review hash. Decision type is:

```text
approved_candidate | overridden | rejected
```

Applied review metadata explicitly changes score provenance to `human_reviewed`. Verified reviewer
RBAC and separation of duties are service invariants. A request that exactly repeats an existing
review is idempotent; a second conflicting applied decision is rejected.

Browser OIDC uses `browser-oidc-pkce-v1`. The ten-minute signed transaction contains state, nonce,
PKCE verifier, and a validated local return path. The app session contains normalized operator
identity, issuer/audience, issue/expiry times, and a unique token ID. Both cookies are HttpOnly and
SameSite Lax; Secure is required by default.

`model-atlas-operational-metrics-v1` returns gauge samples and derived alerts. Prometheus text is
rendered from the same object. Alert records contain key, severity, metric, value, threshold,
summary, and route.

`workload-isolation-registry-v1` fixes workload kinds, network host allowlist, credential
environment allowlist, filesystem roots, tools, subprocess permission, timeout, and output bounds.
`workload-isolation-preflight-v1` returns the selected policy, normalized request, violations, and
an allowed flag. A denied execution raises before Tool/RAG adapter or handler work begins.

## Sprint 5G Signed Supply-Chain And Production Evidence Contract

Alembic revision:

```text
202607200004 supply-chain attestations, revocation actions, and production receipts
```

`ModelSupplyChainAttestation` stores the verified compact-JWS claims and evidence binding. The
effective record includes runtime attestation, artifact, statement and predicate types, statement
ID, publisher issuer, key ID/fingerprint, algorithm, issued time, subject digest, runtime hashes,
CycloneDX specification/version, canonical SBOM JSON/hash, original compact JWS, verifier identity,
verification time, and stable attestation hash. API reads omit the compact JWS.

The statement contract requires:

```text
_type = https://in-toto.io/Statement/v1
predicateType = https://model-atlas.dev/attestations/model-supply-chain/v1
subject[0].digest.sha256 = stored runtime artifact digest
predicate.artifact_attestation_hash = stored runtime attestation hash
predicate.runtime_manifest_hash = stored normalized manifest hash
predicate.sbom_sha256 = canonical CycloneDX JSON SHA-256
```

`ModelSupplyChainAttestationAction` is append-only. Sprint 5G supports one `revoked` action per
attestation with reason, optional ticket, verified actor, timestamp, and stable action hash. The
revoker cannot be the original Model Atlas verifier.

`ProductionEvidenceReceipt` binds a configured collector signature to one completed
`production_captured` benchmark run. It stores statement ID, issuer/key/signature metadata, capture
window and environment, exact result and metric counts, artifact digest, runtime and supply-chain
attestation IDs/hashes, verifier identity, receipt time, and stable receipt hash. Repeated identical
input is idempotent; statement-ID reuse with changed content is rejected.

Evidence Trust treats production labels as follows:

```text
production_captured + active valid receipt -> production_captured
production_captured + no active receipt    -> production_captured_unverified
```

A supply-chain revocation makes linked receipts ineffective for current trust calculations while
preserving all source records. Model Validation advances additively to
`model-validation-report-v3`, exposing supply-chain status/ID, production capture status, and
verified production run/result counts.

## Sprint 5H-A Managed Trust And Transparency Contract

Alembic revision `202607200005` adds trust roots, lifecycle actions, transparency proofs, and
nullable evidence-to-root bindings. Existing evidence payloads remain readable.

Managed JWS lookup is exact on purpose, issuer, key ID, and algorithm. A known issuer/key pair
registered for a different purpose fails closed and cannot use static-JWKS fallback. Private or
symmetric key material is rejected.

Transparency entry:

```text
schema_version = model-atlas-transparency-entry-v1
supply_chain_attestation_id = stored attestation ID
attestation_hash = stored attestation hash
statement_id = stored in-toto JWS jti
subject_digest = stored model SHA-256 digest
```

Checkpoint:

```text
schema_version = model-atlas-transparency-checkpoint-v1
iss / kid / alg = active transparency-log trust root
tree_size > 0
0 <= log_index < tree_size
leaf_hash = SHA256(0x00 || canonical entry JSON)
root_hash = reconstructed RFC 6962-style inclusion root
```

Model Validation advances additively to `model-validation-report-v4`. Supply Chain overview v2 and
receipt/attestation responses add managed-root, tier, transparency, and production-eligibility
fields. Development signatures and proofs remain valid audit evidence but are excluded from
production thresholds.

## Sprint 5H-B Remote Trust Source Contract

Alembic revision `202607210001` adds `evidence_trust_sources`,
`evidence_trust_source_syncs`, and nullable source/sync lineage on trust roots.

Source configuration requires:

```text
source_kind = jwks
purpose = model_publisher | production_collector | transparency_log
trust_tier = development | internal_ca | external
allowed_algorithms = non-empty subset of RS256 | ES256 | EdDSA
60 <= freshness_seconds <= 604800
```

The URL contract rejects credentials, query, fragment, redirect, disallowed host, and non-HTTPS
transport. HTTP requires `development` tier plus both source and server overrides.

Sync mode is `preview | apply`; status is `succeeded | failed`. Every attempt produces an
append-only receipt, including fetch and validation failures. Preview has `imported_count=0` and
does not change trust roots. Apply validates the complete snapshot before importing any key.

Trust-source status is:

```text
unsynced | healthy | degraded | stale | failed | disabled
```

For a source-backed production root:

```text
active root and production trust tier
AND enabled source
AND fresh latest successful Apply
AND root fingerprint present in that Apply snapshot
```

A newer failed attempt yields `degraded` only while the prior Apply is fresh. Stale, failed,
unsynced, and disabled sources fail closed. Trust Registry overview v2 adds source counts without
removing v1 root/proof fields.

## Sprint 5H-C Browser Session Contract

Alembic revision `202607220001` adds opaque browser sessions and shared OIDC documents without
changing evidence or release schemas.

Cookie-authenticated unsafe requests must satisfy:

```text
session hash resolves to active row
AND Origin is in configured browser origins
AND CSRF header == CSRF cookie
AND SHA256(CSRF header) == stored CSRF hash
```

`POST /api/v1/operator-identity/logout` revokes the session before returning
`redirect_url`, `provider_logout`, and `session_revoked`. The browser status response adds
`logout_method=POST`, CSRF names, `session_store=database`, and optional session expiry.

Discovery/JWKS cache rows are reusable only before their stored `expires_at`. A process loading a
shared row inherits that original expiry and cannot renew it without a provider fetch.

## Sprint 5H-D Trust Source Schedule Contract

Alembic revision `202607230001` adds `evidence_trust_source_schedules`, widens the Agent job type
constraint with `trust_source_sync`, and adds scheduled execution lineage to source sync receipts.

Policy bounds are:

```text
60 <= interval_seconds <= 604800
0 <= jitter_seconds < interval_seconds
1 <= max_attempts <= 10
1 <= retry_base_seconds <= retry_max_seconds <= 3600
0 <= retry_jitter_seconds <= retry_max_seconds
```

A due enqueue is valid only when:

```text
schedule.enabled
AND source.enabled
AND next_run_at <= database time
AND schedule lease is absent or expired
AND PostgreSQL locks the row with FOR UPDATE SKIP LOCKED
```

The enqueue transaction increments `run_sequence`, creates the schedule lease fingerprint, inserts
one durable job with dedupe key `trust-source-sync:{schedule_id}:run:{run_sequence}`, and records
`last_job_id`. The worker then requires its independent durable-job lease.

Scheduled receipt fields satisfy:

```text
trigger = scheduled
schedule_id IS NOT NULL
job_id IS NOT NULL
attempt_number > 0
scheduled_for IS NOT NULL
```

Manual receipts use `trigger=manual`, attempt 1, and null scheduled lineage. Existing rows receive
these values through migration defaults. Trust Registry overview v3 adds schedule total, enabled,
due, retrying, and failed counts without removing v2 fields.

## Sprint 5H-E Browser Session Lifecycle Contract

Alembic revision `202607270001` adds session correlation/purge fields, creates
`oidc_browser_session_events`, and widens the Agent job type constraint with
`oidc_session_cleanup`.

Permission policy:

```text
audit       = verified AND role in Admin | SRE Lead | ML Ops Lead
administer  = verified AND role in Admin | SRE Lead
job execute = verified System Worker OR administrator
```

Session status is derived:

```text
revoked_at IS NOT NULL                     -> revoked
revoked_at IS NULL AND expires_at <= now  -> expired
otherwise                                  -> active
```

An administrative revoke requires an 8-to-160-character reason. A single-session action rejects
the current browser session. Subject and provider-session actions skip and report the current
session while revoking other active matches.

Provider token policy:

```text
active session              -> encrypted ID token may be retained for RP logout
revoked or expired session  -> encrypted ID token and raw provider sid must be purged
provider sid hash           -> retained for bounded correlation
```

Retention eligibility:

```text
revoked_at <= now - retention_days
OR (revoked_at IS NULL AND expires_at <= now - retention_days)
```

One cleanup pass locks at most the configured batch size with `FOR UPDATE SKIP LOCKED`, appends a
`retention_deleted` event before each row deletion, and separately purges token material from
recent inactive rows. Independent lifecycle events survive session deletion.

Every lifecycle event hashes a canonical payload including its `previous_event_hash`. This chain
is application-level tamper evidence; no external anchoring or database immutability is implied.

The overview advances additively to `oidc-session-administration-v1` with active, expired,
revoked, retention-due, inactive-token, audit-event, last-cleanup, policy, and permission state.

## Sprint 5H-F Operational Reliability Contract

Alembic revision `202607270002` creates operational snapshots, normalized points, SLO evaluations,
incidents, and paging deliveries. It widens the Agent job type constraint with
`operational_observability_cycle` and `operational_alert_delivery`.

Interval identity is:

```text
bucket_started_at =
  floor(observed_unix_seconds / snapshot_interval_seconds)
  * snapshot_interval_seconds

job dedupe key =
  operational-observability:interval-<bucket sequence>
```

Both the job dedupe key and snapshot bucket are unique. A repeated capture in the same bucket
returns the existing snapshot and does not create new SLO, incident, or delivery rows.

SLO status is:

```text
expected =
  max(actual snapshots, scheduled intervals since first retained baseline)

observed = good / expected

expected < minimum samples  -> insufficient
observed >= target          -> met
otherwise                   -> breached
```

The identity good condition is `retention_due == 0 AND inactive_provider_token == 0`. The worker
good condition is `worker_online >= 1 AND expired_lease_count == 0`.

Incident lifecycle constraints are:

```text
open     -> active_key IS NOT NULL AND resolved_at IS NULL
resolved -> active_key IS NULL AND resolved_at IS NOT NULL
```

Only one open incident may use an alert key. Test incidents are created resolved. Open and resolved
transitions increment a transition version and may create one unique delivery payload.

Paging request authentication is:

```text
canonical payload = JSON(sort_keys=true, separators=(",", ":"))
signature input   = unix_timestamp + "." + canonical payload bytes
signature         = HMAC-SHA256(secret, signature input)
event id          = delivery UUID
idempotency key   = delivery UUID
```

Configuration and permanent HTTP 4xx failures are recorded as `failed`. Transport errors, HTTP
5xx, 408, and 429 remain `queued` until the durable job exhausts its attempts. A delivered row is
replay-safe and performs no second HTTP request. `attempt_count` is a lifetime count and continues
across operator requeue.

Permission policy:

```text
audit =
  verified AND role in Admin | SRE Lead | ML Ops Lead | Release Manager

administer =
  verified AND role in Admin | SRE Lead
```

The additive overview schema is `model-atlas-operational-reliability-v1`. It returns policy and
permission state, snapshot and delivery totals, latest SLO evaluations, bounded snapshot/incident/
delivery collections, and the latest snapshot without removing existing metrics or alerts APIs.

## Sprint 5H-G Multi-Window And Response Contract

Alembic revision `202608030001` extends SLO evaluations and incidents, creates
`operational_alert_incident_actions`, adds delivery key identity, and expands the delivery
transition constraint with `escalated`.

Burn rate is calculated independently for the configured long and short windows:

```text
burn = (1 - observed ratio) / (1 - target ratio)

critical = long burn >= critical threshold AND short burn >= critical threshold
warning  = long burn >= warning threshold  AND short burn >= warning threshold
none     = otherwise, including insufficient samples
```

An SLO breach still has incident evidence when paired burn is `none`; it uses warning severity.
Critical incident severity requires critical paired burn or a critical derived alert.

Incident action mutation requires a verified Admin or SRE Lead. Acknowledgement and assignment
require an open incident; notes may be attached after resolution. Each action's canonical hash
includes its predecessor hash. Automatic escalation applies only to open, critical,
unacknowledged incidents and caps the level at 3.

Paging authentication adds a required sender key identity:

```text
X-Model-Atlas-Key-Id = delivery.signing_key_id
X-Model-Atlas-Signature = sha256=<HMAC>
```

The key ID is selected and persisted at outbox creation. A multi-key keyring requires an explicit
active key. The receiver may accept v1 and v2 payloads during rollout, but new payloads use
`model-atlas-paging-event-v2`. HTTPS uses the system trust store or the configured CA bundle.

The additive overview schema advances to `model-atlas-operational-reliability-v2`. It includes
multi-window values, burn policy, incident response state and action history, active key identity,
TLS state, and delivery key identity. No secret value is exposed.

## Sprint 5H-H Staging Paging Qualification Contract

Alembic revision `202608040001` adds nullable provider-correlation fields to
`operational_alert_deliveries`:

```text
provider_name
provider_event_id
provider_receipt_id
provider_accepted_at
```

Existing rows and routes remain readable. A successful strict delivery requires a bounded JSON
response with this contract:

```json
{
  "schema_version": "model-atlas-paging-provider-receipt-v1",
  "accepted": true,
  "provider": "configured-provider-id",
  "provider_event_id": "<delivery UUID>",
  "receipt_id": "<provider receipt ID>",
  "accepted_at": "<timezone-aware ISO 8601 or Unix seconds>"
}
```

`provider` must equal `OPERATIONAL_PAGING_PROVIDER`; `provider_event_id` must equal the durable
delivery ID; `receipt_id` and the other identifiers must be printable, nonempty, and at most 200
characters. `accepted_at` cannot exceed the configured age and cannot be more than 300 seconds in
the future. If strict receipts are enabled, an invalid 2xx response is a retryable delivery failure.

The key projection contract is a bounded UTF-8 JSON string map plus a separate active key ID file.
The projected keyring has precedence over environment keyrings and the legacy secret. Keyring and
active-key files are read at delivery time so rotation does not require a sender restart. Each
delivery continues to use its persisted `signing_key_id`; the corresponding retiring key must stay
projected until queued work has completed.

The additive overview schema advances to `model-atlas-operational-reliability-v3`. Its policy adds
secret source, key count, provider ID, and strict-receipt state. Its `staging_readiness` object
contains seven named checks, passed and failed counts, aggregate readiness, and the latest
qualifying receipt delivery ID. A recent correlated receipt is deployment evidence, not model
release authorization.
