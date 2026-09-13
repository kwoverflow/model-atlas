# Paired Tool Fault Model Baseline

Updated: 2026-09-09

## Result And Decision

The new actual-runtime diagnostic captured 72 model generations and replayed each unchanged in
three fault environments. Tool selection was correct in 59/72 generations; both selection and
explicit argument values were correct in 43/72. All 72 outputs satisfied the public schema and
guard boundary. Normal fixture execution succeeded 59/72, including 16 outputs with wrong values.

This establishes a fresh, narrow baseline. It is not evidence of improvement over the incompatible
legacy recovery evaluations, and it does not update the official Gate. The next candidate should
target argument generation while retaining non-repairing validation and this frozen baseline.

## Experiment Design

- Case pack: `reference_workload/diagnostics/tool-fault-baseline-v1.json`, version
  `tool-fault-baseline-cases-v1`. Twelve locally authored Korean requests, two per registered Tool.
  Requests explicitly supply argument values; two ticket cases also specify priority.
- Source status: `local_authored_diagnostic`, `human_reviewed=false`, `gate_evidence=false`.
  This is not a finalized replacement for the existing 1.0.4 workload or its approval records.
- Unit: runtime entry x case x trial. The existing matrix supplies three entries and two trials
  each. The replay unit adds fault mode, but is not a new independent model generation.
- Model path: existing OpenAI-compatible adapter v21, legacy/default Tool prompt, existing v1/v2
  prompt bundles, temperature 0, max_tokens 256, seeds 42 and 43, serial execution.
- Tools: the fault registry removes `simulate_failure`; business schemas otherwise remain intact.
  Actual document IDs come from the hash-locked finalized 1.0.4 corpus. Tool order remains fixed.
- Pairing: one fresh response is replayed under `normal`, `transient_once`, and `permanent`.
  The environment setting is never supplied to model generation. Retries are executor-controlled.
- Isolation: the adapter receives an empty Tool contract plus public inputs, not expected Tool
  names or argument labels. The executor receives only the expected Tool name for existing
  selection gating. Exact argument labels are used solely by post-generation diagnostics and do
  not determine injection or repair output.
- Capturing: raw output, normalized output, actual HTTP request body/hash, guard audit, finish
  reason, runtime usage, model digest, source hashes, and all paired traces are retained.
- Persistence: database-free CLI, like the earlier Tool selection challenge runner. No
  Deployment Configuration, Benchmark Result, Portfolio, source approval, or Gate is created or
  modified. Results therefore do not appear as new official records in the application overview.

## Metric Definitions

| Metric | Meaning |
| --- | --- |
| Selection correct | Parsed Tool name equals the evaluator-only expected Tool |
| Raw schema valid | Raw response passes the v2 public Tool schema check without envelope repair |
| Normalized schema valid | Adapter-normalized response passes that schema check |
| Guard eligible | Public schema and trusted document membership/failure boundaries pass |
| Arguments exact | Parsed argument dictionary equals the explicit requested values, including keys |
| Selection and arguments exact | Both the Tool and complete argument dictionary match |
| Normal Tool success | Expected selection, valid call, and local handler execution succeed |
| Fixture passed | Attempts match the configured environment's expected failure/success pattern |

All aggregate generation metrics use all planned trials as the denominator. Runtime or measurement
errors remain explicit rows; `generated_count`, `error_count`, and mode `trace_count` expose missing
outputs/traces. The CLI completes with a nonzero exit code for such errors, not merely low accuracy.
An interrupted run keeps `status=running` and a flushed observation journal; do not analyze it as a
completed baseline. Existing output or journal paths are rejected before model execution.

## Observed Results

| Entry | Tool selection | Raw schema | Guard eligible | Normal execution | Tool and values exact |
| --- | ---: | ---: | ---: | ---: | ---: |
| `small-baseline`, Qwen 2.5 0.5B / v1 | 15/24 | 24/24 | 24/24 | 15/24 | 13/24 |
| `medium-candidate`, Qwen 2.5 1.5B / v1 | 24/24 | 24/24 | 24/24 | 24/24 | 16/24 |
| `prompt-variant`, Qwen 2.5 1.5B / v2 | 20/24 | 24/24 | 24/24 | 20/24 | 14/24 |
| Total | 59/72 | 72/72 | 72/72 | 59/72 | 43/72 |

The 1.5B/v1 configuration has the highest observed exact-call total here, but still substitutes
wrong query values in eight successful fixture calls. In `TFB-001`, it emits a Korean description
instead of the explicitly requested `release approval`. In `TFB-006`, `TFB-009`, and `TFB-011`, it
passes the request or explanatory sentence rather than the quoted search/customer/thread value.
Both trials show these four failures. The small entry has two successful calls with wrong values;
the prompt variant has six. Schema validity alone does not establish value correctness.

| Environment | Traces | Tool successes | Fixture passes | Not exercised | Handler invocations | Injected faults |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Normal | 72 | 59 | 59 | 13 | 59 | 0 |
| Transient once | 72 | 59 | 59 | 13 | 59 | 59 |
| Permanent | 72 | 0 | 59 | 13 | 0 | 59 |

The 13 wrong selections never reach a handler or fault injection. The 59 selected, eligible calls
recover once under the transient fixture and stop under permanent failure. None of this requires
model observation or replanning. Permanent fixture passes remain unsuccessful Tool calls.
Argument hashes matched in 72/72 generations. All responses ended with `finish_reason=stop`;
maximum completion length was 53 tokens. No runtime/measurement errors were recorded.

## Reproduce

With Docker running, execute from the repository root in PowerShell:

```powershell
docker compose exec -T backend python -m app.reference_workload.tool_fault_baseline `
  --repository-root /workspace `
  --base-url http://ollama:11434 `
  --output /artifacts/reference-workload/tool-fault-model-baseline-repeat.json
```

Default models are `qwen2.5:0.5b` and `qwen2.5:1.5b`; overrides are explicit CLI options and their
resolved identities are recorded. All enabled model identities are probed before generation.
Changing models, prompts, schemas, case pack, or corpus creates a new experiment, not a drop-in
replacement for the evidence below. The report records relevant hashes for comparison.

The saved baseline is `artifacts/reference-workload/tool-fault-model-baseline-v1.json`, SHA-256
`27975681d2f2b53bad53c44d19346e5d9d7a47fa28f32a7d226faeecd388497f`.
Its sibling `tool-fault-model-baseline-v1.observations.jsonl` is the incremental journal.

Independent reconciliation and the report input live under
`docs/reports/2026-09-09_tool_fault_baseline/`: `reproduce.ipynb`, `audit.json`, and `artifact.json`.
The notebook completed top-to-bottom, reconstructing exact calls directly from captured JSON and
using SQLite to reconcile totals. It checks source/journal hashes, unique/full trial coverage,
public requests, argument pairing, and handler/injection counts. It performs no model inference.
Re-running this particular notebook requires the recorded implementation hashes to remain current;
a mismatch is an audit warning to use the corresponding source revision, not to edit old hashes.

`tools/build_tool_fault_baseline_review.py` builds an executed companion notebook and canonical
report input from a completed diagnostic. It requires `nbformat`, `nbclient`, and a Python kernel
in the document-analysis environment, not in the backend production dependencies. Use a fresh
output directory for a new review. Windows Python 3.12 supplied those packages for this run.

## Verification And Boundaries

- New runner/pack regression tests: 11 passed. Full host backend: 367 passed, 1 skipped for Windows
  symlink creation. Docker backend: 368 passed. Host and Docker Ruff passed.
- Backend and Agent worker were rebuilt and restarted; no migration or inference-adapter change
  was introduced. The frontend was not changed.
- Source validation still reports 64 approved cases and all 20 critical cases approved under the
  unchanged corpus hash `2772ab9a898529c052337ad6d06e4f0950333a316d72d79778dbc6cfe8cf0642`.
- Official overview checked at `2026-09-09T01:14:11Z`: `BLOCKED`, 110 critical failures, 384 actual
  results, actual output review 0/30, `not_production_ready`. This baseline does not resolve them.
- Test dependency deprecation warnings remain. Notebook execution used the Windows ZMQ selector
  fallback and completed successfully; no backend dependency change was needed.

This experiment is not a measurement of free-form semantic quality, real document content, ACLs,
remote side effects, partial writes, or model-driven recovery. Two zero-temperature trials and
locally authored exact-literal requests do not justify statistical model ranking. Context lengths
in the matrix are declarations, not enforced request parameters in this adapter. Latency is captured
for audit, but was not measured under an isolated, controlled performance benchmark.

Next: test a separately versioned, opt-in argument-generation candidate against these fixed outputs
and new challenge requests. Keep selection errors, value errors, execution behavior, latency, and
token cost separate. Do not fill incorrect model outputs using evaluator labels or lower Gate rules.
