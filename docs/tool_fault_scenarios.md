# Environment-Owned Tool Fault Scenarios

Updated: 2026-09-09

## Purpose

The legacy recovery contract asks a model to produce `simulate_failure` as a Tool argument.
That mixes argument generation with the test harness's job of causing a failure. Adapter v21's
non-repairing guard no longer inserts this argument, so the legacy recovery results cannot serve
as a fair comparison of model recovery ability under the new guard.

This opt-in path moves fault injection into the executor. The model produces ordinary business
arguments. A separately configured, versioned environment controls faults without rewriting them.
This is infrastructure for a new baseline, not a model training change or a model-quality result.

## Execution Flow

1. An operator creates a separate Deployment Configuration with a persisted fault scenario.
2. Benchmark preparation validates the scenario, diagnostic data source, and selected case shape
   before creating a run. It does not migrate incompatible case labels.
3. The public Tool registry omits `simulate_failure`. The model-facing configuration omits the
   fault scenario, and private expected labels are not used to build public Tool descriptors.
4. Adapter v21 validates unchanged model arguments using the existing v2 guard, public schemas,
   and server-resolved corpus catalog. Missing or invalid arguments are not repaired.
5. The executor rejects invalid calls before any fault injection or handler invocation. For an
   eligible call, the trusted scenario can raise an error immediately before the local handler.
6. The trace records injected faults, real handler invocations, retries, execution outcome, and
   fixture outcome separately. Diagnostic runs cannot supply release Gate evidence.

Retries in this version are executor-controlled. There is no model observation/replanning loop.

## Configuration

Put this object in a new Deployment Configuration's `runtime_config_json`:

```json
{
  "tool_fault_scenario": {
    "schema_version": "tool-fault-scenario-v1",
    "mode": "transient_once",
    "max_attempts": 2
  }
}
```

The object's three fields are required. Supported modes are `normal`, `transient_once`, and
`permanent`. `max_attempts` must be an integer from 1 through 3, excluding booleans; transient
failure requires at least 2. The scenario is immutable during a trial and has a canonical SHA-256
hash. It also participates in the existing Deployment Configuration hash.

Execute through `POST /api/v1/benchmark-executions` using the new configuration ID and
`data_source="tool_fault_fixture_diagnostic"`. Other required benchmark IDs remain unchanged.
Do not put `tool_fault_scenario` in per-run `adapter_config_json`: overrides are rejected with
HTTP 422, including explicit null overrides. Legacy `tool_failure_simulation` authorization must
be absent or null when this path is active.

For document calls, configure and pin a retrieval corpus as described in
[Tool Argument Validation](tool_argument_validation.md). Public document IDs are not authority.

## Outcomes

For a valid call and a successful local handler where the handler is reached:

| Mode | Attempts | Injected faults | Handler invocations | Retries | Tool success | Fixture pass |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `normal` | 1 | 0 | 1 | 0 | true | true |
| `transient_once` | 2 | 1 | 1 | 1 | true | true |
| `permanent` | 1 | 1 | 0 | 0 | false | true |

Permanent failure is non-retryable. Its fixture passes only if execution fails and stops as
expected. It is never counted as a successful Tool execution. Unexpected handler errors or output
schema failures fail the fixture. Invalid arguments, wrong selections, and blocked calls have
`status="not_exercised"`, zero attempts, and `passed=false`.

`tool_execution_summary.fault_scenario_summary` is separate from existing Tool success metrics.
Trace attempts expose `fault_injected` and `handler_invoked`; the scenario audit includes
`scenario_hash`, `authority="test_environment"`, `gate_evidence=false`, and the explicit measurement
`executor_fixture_behavior_not_model_recovery_ability`.

## Versions And Compatibility

- Active path: registry `local-tool-fault-fixture-registry-v1`, trace `tool-execution-trace-v2`,
  scenario `tool-fault-scenario-v1`, summary `tool-fault-scenario-summary-v1`.
- Inactive path: existing registry and stored v1 trace format remain unchanged. API read models
  add optional fault fields, which can be null for historical records.
- Supported cases: standalone `tool_single_step` or `tool_failure_recovery` with exactly one
  generated Tool call and a direct expected `tool_name` contract.
- Unsupported: Agent/RAG contexts, multi-step sequences, and external side-effect handlers.
  Only registered handlers whose side-effect mode is `none` or `simulated` are allowed.
- Expected contracts containing `simulate_failure` in required fields, properties, or examples
  are rejected. Existing finalized 1.0.4 recovery cases therefore remain legacy cases.
- The canonical case pack, source approvals, default runtime matrix, and existing Deployment
  Configurations are not rewritten. This step creates no replacement human-reviewed case pack.

Gate evaluation rejects fault-enabled configurations. The evidence collector also excludes runs
whose data source is `tool_fault_fixture_diagnostic`, even if configuration settings later change.
These safeguards are release-evidence boundaries, not a new user authorization mechanism.

## Reproduce The Fixture Check

From the repository root, with the Docker backend running:

```powershell
docker compose exec -T backend python -m app.reference_workload.tool_fault_diagnostic `
  --repository-root /workspace `
  --manifest /workspace/reference_workload/revisions/1.0.4/manifest.json `
  --trials 3 `
  --output /artifacts/reference-workload/tool-fault-fixture-repeat.json
```

For the host virtual environment, run from `backend`:

```powershell
../.venv/Scripts/python.exe -m app.reference_workload.tool_fault_diagnostic `
  --repository-root .. `
  --manifest ../reference_workload/revisions/1.0.4/manifest.json `
  --trials 3 `
  --output ../artifacts/reference-workload/tool-fault-fixture-host-repeat.json
```

Use a new output name for every execution; the command refuses overwriting. It resolves document
IDs from the manifest corpus, uses fixed valid calls for six local Tools, and applies three modes
for three trials each. It writes a diagnostic JSON artifact with implementation and manifest hashes.
It performs no model inference or database writes. Its exit status is nonzero if any fixture fails.

## Code Ownership

| Module under `backend/app` | Responsibility |
| --- | --- |
| `services/tool_fault_scenarios.py` | Immutable scenario, validation, hashing, outcome audit |
| `services/tool_execution.py` | Registry projection, guard boundary, fault injection, trace aggregation |
| `services/benchmark_execution.py` | Persisted configuration validation, trusted trial preparation |
| `services/tool_call_contract.py` | Existing non-repairing model argument guard |
| `services/deployment_gate/evaluator.py` | Reject fault-enabled release evaluations |
| `services/deployment_gate/evidence.py` | Exclude diagnostic runs from evidence collection |
| `schemas/tool_fault_scenarios.py` | Typed API scenario and summary contracts |
| `reference_workload/tool_fault_diagnostic.py` | Database-free scripted executor check |

Focused regression tests live in `backend/tests/test_tool_fault_scenarios.py` and
`backend/tests/test_tool_fault_benchmark.py`. They cover mode behavior, strict configuration parsing,
invalid calls, label isolation, argument preservation, concurrent trial independence, real handler
errors, compatibility, API serialization, early request rejection, and both Gate boundaries.

## Verified Results

On 2026-09-09, the scripted check passed 54/54 observations on both host and Docker. Each environment
recorded 18/18 normal Tool successes, 18/18 transient Tool successes, and 0/18 permanent Tool
successes. All 18 permanent scenarios passed their expected-failure checks. There were 36 injected
faults and 36 handler invocations per environment. This is repeated deterministic fixture coverage,
not 54 independent model answers or a statistical estimate of model reliability.

Artifacts under `artifacts/reference-workload/`:

- `tool-fault-fixture-v1-host.json`: SHA-256
  `72e68ac36ed4fad2e62734ea38ddb456fb874fe55e0771ac173452e6e8050ece`.
- `tool-fault-fixture-v1-docker.json`: SHA-256
  `75483eeb724c48bee0571ed100d4c9b417ae51422c254a467d087133d6aac583`.

Summaries, implementation hashes, corpus hash, and manifest file hash match between environments.
Artifact hashes differ because timestamps and measured durations differ. The referenced corpus
hash is `2772ab9a898529c052337ad6d06e4f0950333a316d72d79778dbc6cfe8cf0642`.

Final backend regression suite: host 356 passed, 1 skipped; Docker 357 passed. The host skip is the
Windows symlink-creation test. The 50 focused new tests passed, and Ruff passed in both environments.
Existing dependency deprecation warnings remain; no dependency upgrade was made to address them.
Backend and Agent worker were rebuilt and restarted. Alembic stayed at `202608040001 (head)`.

Finalized 1.0.4 source validation still reports 64 approved cases and all 20 critical cases approved.
The official overview at `2026-09-09T00:56:16Z` remains `BLOCKED`: 110 critical failures,
384 actual-runtime results, 0/30 target output reviews, and `not_production_ready`. Source-case
approval is not human review of actual model outputs. Existing authoritative results are unchanged.

## Next Baseline

The first compatible actual-model baseline is now complete as a separate database-free diagnostic:
72 generations, 216 paired traces, selection 59/72, exact Tool plus requested values 43/72. See
[Paired Tool Fault Model Baseline](tool_fault_model_baseline.md) for the protocol and limitations.
It does not migrate the canonical case pack or promote release evidence. The design requirements
below also apply to later candidate comparisons.

Create a separate, versioned diagnostic case set with ordinary business arguments and no
model-authored failure controls. Keep public inputs, model settings, Tool schemas, corpus, and
trial counts fixed across modes. Report Tool selection, raw schema validity, guard eligibility,
actual handler execution, and scenario compliance as separate measurements. Review any changed
evaluation labels before promoting them to an authoritative case revision.

The present fixtures do not test partial external writes, idempotency after a remote timeout,
document ACLs, real document content, query relevance, or model-driven recovery. Passing them
cannot authorize a release or remove the existing `not_production_ready` status.
