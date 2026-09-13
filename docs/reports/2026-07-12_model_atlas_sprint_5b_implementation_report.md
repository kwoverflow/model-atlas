# Model Atlas Sprint 5B Implementation Report

Date: 2026-07-12

## Implemented

- `bounded-agent-runtime-v2` with additive v1 trace-read compatibility.
- Versioned observation envelope for every executed Agent step.
- One-shot observation-driven recovery branch selection.
- Maximum two recovery steps and a combined execution-step budget.
- External approved, denied, and pending human checkpoint decisions.
- Guarded actions using executor-enforced `requires_approval` references.
- Approval actor, reason, source, policy version, and SHA-256 decision hash provenance.
- Fail-closed halt behavior for pending, denied, bypassed, malformed, and over-limit paths.
- Semantic replay of approval and recovery evidence with volatile timing removal.
- Seven additional Agent Gate metrics and critical-case detail fields.
- Gate evidence snapshot v7 observation, recovery-policy, and approval-policy provenance.
- Five-case Adaptive Agent Operations suite and dedicated Acceptance Policy.
- Benchmark execution approval controls and expanded Agent trace UI.

## Architecture Decisions

- Recovery does not mutate or hide the original failed step.
- A recovered failure remains visible in raw step success and receives separate recovery credit.
- The executor selects only a predeclared branch whose trigger index and error type match the real
  observation.
- A policy or approval violation cannot trigger recovery.
- Approval decisions are request-side evidence and are removed from model adapter input.
- Merely supplying a decision does not bypass the required checkpoint action.
- Decisions are stored in run config so semantic replay uses the original evidence.
- Agent checkpoints permit a guarded step but do not replace Deployment Gate or signed release
  authorization.

## Versions

| Component | Sprint 5B version |
| --- | --- |
| Agent runtime | `bounded-agent-runtime-v2` |
| Agent context | `agent-context-v2` |
| Agent trace | `agent-execution-trace-v2` |
| Agent summary | `agent-execution-summary-v2` |
| Observation | `agent-observation-v1` |
| Recovery policy | `bounded-recovery-policy-v1` |
| Approval policy | `human-checkpoint-policy-v1` |
| Mock adapter | `mock-adapter-v6` |
| OpenAI-compatible adapter | `openai-compatible-v6` |
| Heuristic scorer registry | `heuristic-scorer-v5` |
| Agent scorer | `agent-execution-scorer-v2` |
| Gate calculation | `deployment-gate-sprint-5b-v1` |
| Gate snapshot | `gate-evidence-snapshot-v7` |

## Files Added

- `backend/app/seed/adaptive_agent_operations.py`
- `backend/tests/test_adaptive_agent_operations_pack.py`
- `docs/agent_recovery_and_approval.md`
- `docs/reports/2026-07-12_model_atlas_sprint_5b_implementation_report.md`

## Main Modified Areas

- Agent executor, trace, summary, replay, and runtime descriptor.
- Benchmark execution request and run provenance.
- Mock and OpenAI-compatible adapter contracts.
- Agent scorer and Deployment Gate metric calculation.
- Gate evidence snapshot and critical-case outcomes.
- Base seed cleanup lists and Make targets.
- Benchmark execution form, detail trace, and Gate detail UI.
- Architecture, contracts, demo, status, roadmap, submission, and handoff documentation.

## Request Contract

`POST /api/v1/benchmark-executions` adds `agent_approval_decisions`. Each decision requires an
`approved` or `denied` value, actor, and reason. Omitted checkpoints are pending. At most 20
checkpoint decisions are accepted per request.

Existing routes remain unchanged:

- `GET /api/v1/agents/runtime`
- `GET /api/v1/agents/memory-registry`
- `POST /api/v1/agents/replay/{benchmark_result_id}`

## Gate Metrics Added

- `agent_replan_success_rate`
- `agent_recovery_step_success_rate`
- `agent_approval_compliance_rate`
- `agent_approval_provenance_rate`
- `agent_pending_approval_rate`
- `agent_observation_coverage_rate`
- `agent_unrecovered_failure_rate`

## Test Coverage Added

- Approved checkpoint and guarded action execution.
- Pending and denied checkpoint halting.
- Decision input actor/reason validation.
- Checkpoint bypass prevention.
- Contract-required guard-reference omission prevention.
- Permanent tool failure and fallback recovery.
- Empty retrieval and refined-query recovery.
- Recovery-step limit enforcement.
- Overlapping recovery-trigger rejection.
- Original failure preservation with separate recovery credit.
- Approval and replan semantic replay.
- Approved Gate path and pending-approval blocked Gate path.
- Adaptive seed idempotence.
- Full existing Tool, RAG, Reliability, Gate, readiness, release, and lineage regression suite.

## Verification Results

```text
Backend pytest: 133 passed, 1 upstream deprecation warning
Backend Ruff: passed
Frontend typecheck: passed
Frontend ESLint: passed
Frontend production build: passed
Alembic head/static SQL: passed (single head: 202607110001)
Docker Compose configuration: passed
```

## Verification Boundaries

- Live localhost browser QA is not claimed because the host browser policy blocks local navigation
  in this task.
- Live Docker health is not claimed because Docker named-pipe access is unavailable in the current
  sandbox.
- Compose validation emitted a sandbox-only access warning for the user-level Docker config, but
  completed successfully with exit code 0.

## Known Limitations

- Approval actor strings are evidence fields, not authenticated identities.
- Benchmark execution is synchronous and cannot persist a paused task for later resumption.
- Recovery uses predeclared branches rather than a live second model call.
- Decisions have no expiry, revocation, or policy-specific approver group.
- Tools, corpus, memory, and recovery scenarios are deterministic local fixtures.

## Recommended Next Sprint

Sprint 5C should add authenticated policy-scoped approvers, persisted pause/resume checkpoints,
decision expiry and revocation, and an optional bounded live replan callback with explicit model-call
cost, latency, and provenance evidence.
