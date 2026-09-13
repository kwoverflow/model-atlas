# Deployment Gate

Model Atlas Deployment Gate is the authoritative decision layer for local AI deployment readiness.

Candidate Discovery answers:

```text
Which model artifacts are promising enough to evaluate?
```

Deployment Gate answers:

```text
Can this exact configuration be deployed for this workload under this policy?
```

## Verdicts

Only four verdicts are valid:

- `APPROVED`: all blocker rules pass, warning rules pass, required real evidence exists, no critical case fails, no OOM occurs, and baseline regression is within policy.
- `CONDITIONAL`: blocker rules pass, but warning rules or known non-blocking risks require review.
- `BLOCKED`: a blocker rule fails, a critical case fails, OOM occurs, or a zero-tolerance policy is violated.
- `INSUFFICIENT_EVIDENCE`: mandatory evidence is missing, required metrics are unavailable, active cases are missing, critical coverage is too low, or evidence is synthetic-only.

## Evidence Requirements

Gate evidence is collected from completed benchmark runs attached to both:

- a `deployment_configuration_id`;
- an `evaluation_suite_id`.

Gate-related benchmark results should reference active evaluation cases from the same suite. Inference metrics are matched by run ID and sample ID.

## Policy Rules

Acceptance policy rules reference metric definitions and apply absolute thresholds:

```text
json_validity_rate >= 0.99
tool_call_validity_rate >= 0.95
critical_case_failure_rate == 0
p95_end_to_end_latency_ms <= 5000
oom_rate == 0
real_case_count >= 30
critical_case_count >= 10
```

Rule statuses are:

- `pass`
- `fail`
- `insufficient`

Missing required metric data is `insufficient`, not zero.

## Scoring Hooks

Benchmark execution applies local deterministic scoring when an adapter result does not already
include quality labels. Scorers are selected through `ResultScorerRegistry`, so new scoring methods
can be added without changing benchmark execution orchestration:

- JSON cases: valid JSON object plus required-key and property-type coverage.
- Tool cases: expected `tool_name` match plus required argument coverage.
- Grounded-answer cases: reference fact coverage, context overlap, and concise-answer checks.
- Text fallback cases: non-empty output check.

These scores populate `mean_quality_score`, `groundedness_score`, `faithfulness_score`, and
critical-case failure detection. Result metadata stores scorer version, registry ID, scorer ID,
method, and details. These scores are reproducible local evidence, not a replacement for
production-captured labels or later human/LLM judge calibration.

Human or LLM judge labels can be imported after a benchmark run. Dry-run mode compares labels
against existing scores; apply mode updates result scores and stores provenance in
`metadata_json.judge_label`.

## Synthetic Evidence

Seed data uses `data_source = synthetic_demo`.

Synthetic evidence may demonstrate the UI, API, rule behavior, and report generation. It cannot prove deployment readiness. Synthetic-only evidence always resolves to `INSUFFICIENT_EVIDENCE`, even when some individual rules pass.

## Baseline Regression

When a baseline gate evaluation is supplied or an active baseline exists for the same scope, the
evaluator calculates:

- `quality_regression_vs_baseline`
- `latency_regression_vs_baseline`

Baseline metric values are read from the stored baseline scorecard. Explicit baselines must match
the same deployment configuration, evaluation suite, and acceptance policy as the new gate.

## Prompt Version Regression

Prompt version regression is a review layer over stored benchmark evidence. It groups completed
benchmark runs by prompt version, aggregates quality, reliability, latency, throughput, and OOM
metrics, and compares those aggregates with the active baseline scorecard when the report is scoped
to one deployment configuration, suite, and policy.

Regression flags are intentionally advisory. They help operators decide which prompt version needs
review or rerun, while the Deployment Gate remains the authoritative approval decision.

## Experiment Lineage

Gate evaluation, baseline promotion, and release decision signing automatically create experiment
lineage events. These events link prompt versions, benchmark runs, gate verdicts, active baselines,
supersession history, and release sign-offs into one operational timeline. Lineage improves
auditability and release review, but it does not change the gate verdict or baseline rules.

## Release Readiness

Release readiness snapshots compose the gate verdict, baseline state, judge calibration coverage,
prompt regression risks, and lineage events into one review artifact. A snapshot can mark an
approved gate as ready, ready to promote, or needing review, but it does not replace the gate
verdict. Operators can sign a reviewed snapshot as a separate release decision record.

## Signed Release Decisions

Release decisions freeze the readiness snapshot reviewed by an operator. A record stores the gate
scope, readiness status, decision value, signer identity, identity verification state, approval
policy state, signature statement, reason, snapshot JSON, snapshot hash, signature hash, decision hash, and decision
timestamp.

Valid release decisions are:

- `APPROVE_RELEASE`
- `REQUEST_CHANGES`
- `REJECT_RELEASE`

`APPROVE_RELEASE` requires readiness status `READY` or `READY_TO_PROMOTE`, verified operator
identity, and one of the approved release roles: `Release Manager`, `ML Ops Lead`,
`Model Governance`, or `Admin`. `REJECT_RELEASE` uses the same verified release-role requirement.
`REQUEST_CHANGES` can still be recorded by a local self-attested reviewer so blocked releases leave
an audit trail during auth rollout. Signing a release decision does not mutate the gate verdict,
benchmark evidence, prompt regression report, or active baseline. It records a
`release_decision_signed` lineage event in the same transaction.

The release decision detail API can export the frozen snapshot JSON and compare it with the current
readiness snapshot for the same gate. The diff is path-based and ignores volatile `generated_at`
values so audit review can focus on material drift.

Local UI signing is self-attested. If a trusted reverse proxy or authentication middleware supplies
`x-model-atlas-operator-*` headers, the same API records the signer as a verified trusted-header
identity without changing the release decision workflow.

## Baseline Promotion

Only completed `APPROVED` gate evaluations can be promoted as deployment baselines. A promoted
baseline stores:

- deployment configuration ID;
- evaluation suite ID;
- acceptance policy ID;
- source gate evaluation ID;
- promotion metadata;
- stable baseline hash;
- active, superseded, or archived status.

Only one active baseline is kept per deployment configuration, suite, and policy scope. Promoting a
new baseline in that scope marks the previous active baseline as `superseded`. When a new gate
evaluation omits `baseline_gate_evaluation_id`, the evaluator automatically uses the active baseline
for the same scope.

## Decision Record

Each gate evaluation stores:

- deployment configuration ID and hash;
- evaluation suite ID and hash;
- acceptance policy ID and hash;
- benchmark run IDs;
- source data distribution;
- metric scorecard;
- rule outcomes;
- critical-case outcomes;
- optional baseline reference;
- final verdict;
- decision summary;
- decision hash.

Markdown and PDF reports are renderings of the stored decision record.

## Sprint 4A Status Separation

A Gate Verdict answers whether policy rules passed. It does not describe the strength of the evidence or authorize production deployment by itself.

| Status | Question |
| --- | --- |
| Gate Verdict | Did this configuration pass the acceptance policy? |
| Evidence Trust | How trustworthy are source and score provenance? |
| Release Readiness | Are baseline, review, regression, and lineage controls ready? |
| Production Readiness | Can the current evidence be interpreted as production-ready? |

An approved local demonstration can therefore be represented as:

```text
Gate Verdict: APPROVED
Evidence Trust: LOCAL_DEMO_READY
Release Readiness: READY_TO_PROMOTE
Production Readiness: NOT_PRODUCTION_READY
```

## Preflight Semantics

`POST /api/v1/deployment-gates/preflight` accepts the same scope IDs as gate creation. It returns:

- configuration, suite, and policy summaries;
- active and critical case counts;
- matching completed runs, results, and metrics;
- source and score trust distributions;
- judge and critical-case review coverage;
- explicit or active baseline summary;
- blocking preconditions, warnings, and expected limitations;
- `can_evaluate`.

Preflight does not persist a Gate Evaluation and does not predict a verdict. Workload mismatch, no active cases, no completed runs, or no matching results are blocking preconditions. Synthetic-only or locally authored evidence is surfaced as a limitation rather than mislabeled as production evidence.

## Structured Decision Explanation

Gate scorecards preserve the existing `decision_summary` and add:

```json
{
  "decision_explanation": {
    "summary": "...",
    "blockers": [],
    "warnings": [],
    "next_actions": []
  }
}
```

The Gate report presents status, explanation, blockers, actions, trust, and critical cases before policy and metric tables. Raw snapshots and hashes use progressive disclosure in the UI.

## Trust-aware Release Mapping

- `synthetic_only` -> `INSUFFICIENT_EVIDENCE` release readiness.
- `needs_judge_review` or `unknown` -> `NEEDS_REVIEW`.
- `local_demo_ready` can become `READY_TO_PROMOTE` or `READY`, but production readiness remains `not_production_ready`.
- `production_evidence_ready` can become `production_ready` only when the gate, active baseline, review, and prompt-regression controls also pass.

Release decisions freeze the trust summary. Applying judge labels later changes the current snapshot and is visible through snapshot diff.

## Sprint 4B Tool Calling Rules

Executable tool traces contribute five versioned metrics:

- `tool_selection_accuracy`;
- `tool_argument_validity_rate`;
- `tool_execution_success_rate`;
- `tool_sequence_success_rate`;
- `tool_retry_recovery_rate`.

The `Executable Tool Calling Policy` applies these metrics through the existing threshold-rule
engine. It does not create a separate verdict type. Invalid selection, invalid arguments, execution
failure, and sequence mismatch can therefore block the same `Deployment Gate` used by all other
evaluation packs.

Critical tool cases also fail the existing `critical_case_failure_rate` calculation when the call is
invalid or execution is unsuccessful. Gate critical-case rows include the benchmark run ID and tool
execution status so the UI can link directly to the immutable trace.

Gate evidence snapshot v3 adds tool registry and trace versions while preserving all v2 trust and
adapter/scorer provenance fields.

## Sprint 4C RAG Rules

RAG traces contribute five versioned metrics:

- `rag_retrieval_recall`;
- `rag_citation_precision`;
- `rag_citation_recall`;
- `rag_groundedness_score`;
- `rag_unsupported_claim_rate`.

The `RAG Grounded Answer Policy` applies these metrics through the existing policy engine. Retrieval
misses, citations outside retrieved/relevant chunks, weak claim support, or unsupported claims can
therefore block the same Deployment Gate used by other packs.

Critical RAG cases also participate in critical-case blocking. Their Gate rows preserve benchmark
run ID and RAG status so the UI can open the underlying retrieval and generation trace.

Gate evidence snapshot v4 adds corpus, retriever, and RAG evaluation versions while preserving all
v2/v3 fields.

## Sprint 4D Runtime Reliability Rules

The Runtime Reliability Policy reuses the normal policy engine and blocks on:

| Metric | Default pack rule | Minimum samples |
| --- | ---: | ---: |
| `reliability_success_rate` | `>= 1.0` | 30 |
| `reliability_timeout_rate` | `<= 0.0` | 30 |
| `reliability_oom_rate` | `<= 0.0` | 30 |
| `p99_end_to_end_latency_ms` | `<= 2000` | 30 |
| `latency_variation_coefficient` | `<= 0.10` | 30 |
| `trial_coverage_rate` | `>= 1.0` | 30 |
| `context_stress_success_rate` | `>= 1.0` | 10 |

Timeout, OOM, and generic errors remain separate scorecard values. A failed reliability trace on a
critical case also triggers critical-case blocking, regardless of aggregate averages. The critical
outcome stores `runtime_reliability_status` and links to the originating benchmark run.

The evidence snapshot advances to `gate-evidence-snapshot-v5` and records reliability trace
versions. Runtime comparison does not issue release approval; only the Gate evaluates policy and
feeds readiness and signed decisions.

## Sprint 5A Bounded Agent Rules

The Bounded Agent Operations Policy reuses the same policy engine:

| Metric | Default pack rule | Minimum samples |
| --- | ---: | ---: |
| `agent_task_success_rate` | `>= 1.0` | 8 cases |
| `agent_plan_validity_rate` | `>= 1.0` | 8 cases |
| `agent_step_success_rate` | `>= 1.0` | 20 steps |
| `agent_action_sequence_accuracy` | `>= 1.0` | 8 cases |
| `agent_policy_violation_rate` | `<= 0.0` | 8 cases |
| `agent_final_response_rate` | `>= 1.0` | 8 cases |
| `agent_memory_provenance_rate` | `>= 1.0` | 5 actions |
| `agent_tool_retry_recovery_rate` | `>= 1.0` warning | 1 retry |

Plan parsing, step execution, action order, policy violations, response completion, memory
provenance, and retry recovery remain distinct evidence. A failed or policy-violating critical Agent
trace triggers critical-case blocking even when aggregate quality remains high.

Critical outcomes add `agent_execution_status` and link to the benchmark replay trace. Semantic
replay is diagnostic and cannot change a stored Gate verdict.

Gate evidence snapshot v6 records bounded Agent runtime, Agent trace, and operational-memory
registry versions while preserving previous snapshot fields.

## Sprint 5B Adaptive Agent Rules

The Adaptive Agent Operations Policy keeps the Sprint 5A task, plan, raw step, sequence, policy,
and response rules, then adds:

| Metric | Default pack rule | Minimum samples |
| --- | ---: | ---: |
| `agent_replan_success_rate` | `>= 1.0` | 2 replans |
| `agent_recovery_step_success_rate` | `>= 1.0` | 2 steps |
| `agent_approval_compliance_rate` | `>= 1.0` | 2 checkpoints |
| `agent_approval_provenance_rate` | `>= 1.0` | 2 checkpoints |
| `agent_pending_approval_rate` | `<= 0.0` | 2 checkpoints |
| `agent_observation_coverage_rate` | `>= 1.0` | 10 steps |
| `agent_unrecovered_failure_rate` | `<= 0.0` | 5 cases |

The pack sets raw `agent_step_success_rate >= 0.8` because a successfully recovered task preserves
its original failed step. Recovery success never rewrites that raw evidence.

Pending, denied, approval-bypassing, recovery-policy-violating, and unrecovered critical cases
block the Gate. Critical outcomes add `agent_halt_reason`, `agent_replan_count`, and
`agent_pending_approval_count`.

Gate evidence snapshot v7 records observation, recovery-policy, and approval-policy versions in
addition to the v6 Agent fields. Checkpoint approval is execution evidence only; it cannot replace
the Deployment Gate verdict, Release Readiness, or signed Release Decision.

## Sprint 5D Evidence Revision Rules

Gate evidence snapshot v8 computes a canonical `evidence_revision_hash` from the latest
`BenchmarkResult` revision for each logical root. Append-only parent and child results are therefore
not double-counted. The snapshot includes an evidence revision manifest with root, selected result,
revision number, and revision hash provenance.

A completed Gate changes to operational status `stale` when current evidence for the same
deployment configuration and evaluation suite no longer matches its stored revision hash. New
benchmark completion, checkpoint resume, and production evidence import trigger this check, while
read-time and scheduled reconciliation repair missed transitions.

Stale behavior is fail closed:

- the original verdict, scorecard, decision hash, and evidence snapshot remain preserved;
- Release Readiness reports `BLOCKED` and asks the operator to rerun the Gate;
- baseline promotion is rejected;
- a replacement evaluation links the stale Gate through
  `superseded_by_gate_evaluation_id`.

Existing signed Release Decisions remain immutable frozen records. Their operational notification
or revocation is outside the Sprint 5D boundary.
