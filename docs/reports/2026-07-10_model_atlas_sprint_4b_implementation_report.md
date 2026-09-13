# Model Atlas Sprint 4B Implementation Report

Date: 2026-07-10

Status note: This report preserves the Sprint 4B completion state. Sprint 4C has since implemented
the recommended RAG Evaluation Pack; see
`2026-07-10_model_atlas_sprint_4c_implementation_report.md`.

## Implemented

- A versioned, bounded local Tool Registry with six deterministic handlers.
- Parsing for single-call, multi-step, and OpenAI-native response-shaped tool calls.
- Tool selection, argument, and handler-output validation.
- Actual in-process execution with retryable and permanent failure classification.
- Maximum call and attempt limits, retry recovery, and ordered multi-step context.
- Versioned execution traces persisted in benchmark result metadata and execution logs.
- Executable tool scoring and five tool-specific Gate metrics.
- A ten-case Tool Calling suite and dedicated Acceptance Policy.
- Tool Registry and benchmark execution detail APIs.
- Tool trace summary and case-step-attempt UI.
- Gate critical-case links to the originating benchmark trace.
- Gate evidence snapshot v3 tool provenance.

## Architecture Decisions

- The benchmark service, not the inference adapter, owns tool execution.
- Invalid, unexpected, or unregistered calls are skipped before handler invocation.
- All current tools are in-process fixtures with no network, filesystem, subprocess, credential, or
  production-system access.
- `create_ticket` is explicitly simulated and returns a deterministic ID.
- Result metadata and execution logs carry traces, avoiding a database migration.
- The existing metric, policy, Gate, readiness, frozen decision, and lineage paths remain
  authoritative; Tool Calling does not create a parallel release mechanism.
- The current schema validator implements the bounded JSON Schema subset required by registered
  tools rather than claiming full JSON Schema support.

## Files Added

- `backend/app/services/tool_execution.py`
- `backend/app/schemas/tool_execution.py`
- `backend/app/seed/tool_calling.py`
- `backend/tests/test_tool_execution.py`
- `backend/tests/test_tool_calling_pack.py`
- `frontend/components/ToolExecutionTracePanel.tsx`
- `frontend/app/benchmark-executions/[id]/page.tsx`
- `docs/tool_calling_evaluation.md`
- `docs/reports/2026-07-10_model_atlas_sprint_4b_implementation_report.md`

## Files Modified

- Benchmark execution service, schemas, API route, adapters, scorer registry, Gate metrics, and
  evidence snapshot provenance.
- Demo seed reset behavior and Makefile seed targets.
- Frontend benchmark form, API client/types, Gate detail, and shared status presentation.
- README, submission guide, architecture, data contract, deployment gate, extension contracts,
  Golden Demo, and project status documents.

## API Changes

- Added `GET /api/v1/benchmark-executions/tool-registry`.
- Added `GET /api/v1/benchmark-executions/{benchmark_run_id}`.
- Extended `POST /api/v1/benchmark-executions` with `tool_execution_summary`.
- Extended Gate critical-case outcomes with `benchmark_run_id` and `tool_execution_status`.
- Gate evidence snapshot v3 adds `tool_registry_versions` and `tool_execution_versions`.

## Compatibility Notes

- Existing API routes and fields remain available; new fields are additive.
- Existing benchmark and Gate database tables are unchanged.
- Legacy `required_arguments` tool schemas are normalized at read/execution time.
- The legacy `lookup_internal_document` demo tool remains executable through the new registry.
- Gate snapshot v2 records remain readable; new Gate evaluations create snapshot v3.
- Runs without tool cases receive an empty tool summary and retain previous behavior.
- Existing scorer and adapter provenance remains available; behavior-changing implementations use
  version 2 descriptors.

## Tests Added

- Registered execution and output capture.
- Wrong-tool and invalid-argument skip behavior.
- Transient retry recovery and permanent non-retryable failure.
- Multi-step order and prior-output context.
- OpenAI-native function-call normalization.
- Trace attachment, registry provenance, and aggregate summary.
- API registry/detail responses and Gate snapshot provenance.
- End-to-end ten-case pack execution and tool-specific Gate approval.
- Idempotent Tool Calling seed behavior.

## Verification Results

```text
Backend pytest: 96 passed, 1 upstream deprecation warning
Backend Ruff: passed
Frontend typecheck: passed
Frontend ESLint: passed
Frontend production build: passed
Docker Compose configuration validation: passed
```

The warning is the existing Starlette TestClient `httpx` compatibility warning. Docker Compose
structure validated, but live container health was not re-run because Docker named-pipe access is
not available inside the current sandbox.

## Manual UX Verification

- The benchmark form exposes the registry version, registered tools, and side-effect mode.
- Completed tool runs show call success, retry recovery, multi-step count, and a trace link.
- The trace page presents run status, aggregate execution states, provenance, case sequence, step
  validation, execution outcome, attempts, arguments, outputs, and errors.
- Gate critical tool rows link back to the benchmark execution detail.
- Type checking, lint, and the production route build passed for desktop and responsive markup.
- A new live-browser pass was not performed because the host browser policy blocks local navigation;
  no browser verification is claimed for the new trace page.

## Known Limitations

- Tools are deterministic local fixtures, not production-connected integrations.
- Execution is synchronous and in-process.
- Tool duration does not represent remote service latency.
- The model is not called again with tool output, so conversational recovery is not evaluated.
- JSON Schema support is intentionally bounded to the subset documented for current descriptors.
- Judge/human calibration is still required before locally authored results can support stronger
  evidence-trust states.

## Recommended Next Sprint

Sprint 4C should implement a RAG Evaluation Pack with versioned corpus and retrieval configuration,
retrieval recall, citation precision, groundedness, unsupported-claim rate, and RAG-specific
acceptance rules. It should reuse the same execution evidence, trust, Gate, readiness, frozen
decision, and audit contracts.
