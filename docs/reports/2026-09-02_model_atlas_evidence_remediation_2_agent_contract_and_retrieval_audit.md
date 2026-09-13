# Model Atlas Evidence Remediation 2: Agent Contract And Retrieval Audit

Recorded: 2026-09-02

## Decision

The first P0 Agent remediation unit is complete, but it does not authorize Phase 7 release work.
The bounded Agent runtime now converts eligible model intent into a deterministic executable plan,
preserves the raw model output, and records compilation provenance. Actual Docker Ollama reruns
show that this fixes most structural planning failures for the two 1.5B configurations.

End-to-end Agent task success remains `0.0` for all three configurations. A separate retrieval
contract audit proves that all four scoped critical cases require a chunk ranked outside their
declared `top_k=5`. The current lexical retriever therefore cannot satisfy those case contracts.

## Problem Diagnosis

The original failures combined three independent problems:

1. The Agent prompt did not state exact fields for every action and small models emitted invalid,
   truncated, repeated, or misordered plans.
2. Agent Tool execution was followed by a second standalone Tool interpretation of the entire
   plan, which could replace an Agent success with `tool_execution_failed`.
3. Even a structurally valid `retrieve -> tool -> respond` plan could not succeed because the
   declared relevant chunk was not present in the retriever's top five results.

The third issue is a source case/retriever contract problem. Expected chunks, labels, and historical
results were not changed to make the rerun pass.

## Implemented Changes

- OpenAI-compatible Agent adapter v9 sends a compact public task contract for simple bounded plans.
- The system prompt defines exact action schemas and disallows unsupported wrapper fields and
  unnecessary repetition.
- Agent-owned Tool traces are no longer re-executed as standalone Tool outputs.
- `bounded-agent-plan-compiler-v1` compiles only the narrow public contract with exactly one
  retrieve, one allowed Tool, and one response action.
- The compiler never reads `expected_steps`; it validates model Tool intent and required public
  arguments, preserves raw output, and records source and compiled hashes.
- Diagnostic runtime mode uses separate Deployment Configuration identity and
  `local_actual_runtime_diagnostic`, one trial per configuration, explicit case IDs, and a 20-case
  limit.
- Retrieval contract audit records declared query, top-k, expected rank, retrieved IDs, corpus
  hash, case hash, and a blocking process exit without mutating evidence.

## Actual Runtime Evidence

Each run used four critical cases, all three enabled configurations, one trial per case, two local
Ollama artifacts, and 12 actual persisted Results. Diagnostic generation used `max_tokens=384`.

| Configuration | Plan validity v8 -> final | Sequence v8 -> final | Policy violation v8 -> final | Final response v8 -> final | Step success final | Task success final |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 0.00 -> 0.75 | 0.00 -> 0.75 | 1.00 -> 0.25 | 0.00 -> 0.75 | 0.6667 | 0.00 |
| `medium-candidate` | 0.00 -> 1.00 | 0.00 -> 1.00 | 1.00 -> 0.00 | 0.00 -> 1.00 | 0.6667 | 0.00 |
| `prompt-variant` | 0.00 -> 1.00 | 0.00 -> 1.00 | 1.00 -> 0.00 | 0.00 -> 1.00 | 0.6667 | 0.00 |

The final structural rates describe the complete runtime after the policy compiler, not raw model
planning accuracy. Raw outputs remain attached to every Result for review. The 0.5B configuration
still produced one plan that could not be safely compiled.

Final diagnostic run IDs:

- `small-baseline`: `d3dcce74-be13-4139-8cee-9947e192474d`
- `medium-candidate`: `6ca02a0d-0ce4-406e-ab20-3c690bbba6bc`
- `prompt-variant`: `9dd30ffb-83f7-462e-abd0-30f9bc878453`

Artifacts:

- baseline v8: `artifacts/reference-workload/runtime-matrix-diagnostic-agent-v8-20260902.json`
  (`896a5644e0e56e094883ddfa088797b9a648c5e06383eb4b9e1df712fe52441c`)
- compact prompt v9: `artifacts/reference-workload/runtime-matrix-diagnostic-agent-v9-20260902.json`
  (`77e97eb3951589787b832922434790c37c261516c532cda175612ecbbffe4aec`)
- compiler v1: `artifacts/reference-workload/runtime-matrix-diagnostic-agent-compiler-v1-20260902.json`
  (`549ae6f892623ff793a3a5e7156cc8561abd52a9a000691fad4ee68c51d33c7a`)

## Retrieval Contract Audit

| Case | Declared top-k | Expected chunk rank | Recall | Reachable |
| --- | ---: | ---: | ---: | --- |
| `KO-RAG-TOOL-001` | 5 | 8 | 0.0 | no |
| `KO-RAG-TOOL-002` | 5 | 40 | 0.0 | no |
| `KO-RAG-TOOL-003` | 5 | 14 | 0.0 | no |
| `KO-AGENT-001` | 5 | 15 | 0.0 | no |

Audit result: four blocked cases, four critical blocked cases, zero reachable cases. Artifact:
`artifacts/reference-workload/retrieval-contract-audit-agent-p0-20260902.json`, SHA-256
`27abea7c6edd10e211fc9edfe3d28873951858bf8eeb2f1d10ea9d44adc569ef`.

## Evidence Boundary

- Canonical 64-case portfolio matrix: unchanged.
- Authoritative persisted portfolio Results: unchanged at 384.
- Critical failure review queue: unchanged at 110.
- Human output review: unchanged at 0 of 30.
- Reference Gates: unchanged at three of three `BLOCKED`.
- Production readiness: `not_production_ready`.

The diagnostic configurations are excluded from portfolio selection by identity and data source.
Neither the compiler nor the audit changes expected labels, case hashes, historical Results, Gate
snapshots, or release decisions.

## Verification

```text
Focused Agent/runtime/audit tests: 30 passed, 2 known warnings
Backend full suite: 229 passed, 1 skipped, 2 known warnings
Backend Ruff: passed
Frontend ESLint: passed
Docker focused tests: 30 passed, 1 known warning
Docker Ruff: passed
Backend and Agent worker image build: passed
Backend and Ollama health: passed
Alembic current: 202608040001 (head)
Live authoritative overview: 384 Results, 110 critical failures, 0/30 reviewed
Live Gate outcomes: 3 of 3 BLOCKED
Actual final diagnostic Results: 12
Diagnostic completed entries: 3 of 3
Timeouts / OOM: 0 / 0
Retrieval audit: BLOCKED as designed
Production readiness: not_production_ready
```

## Required Next Unit

Create a reviewed reference case-pack revision that reconciles each declared query, expected chunk,
top-k, and retriever behavior. The revision must run this audit before approval. After that, rerun
the same four-case diagnostic and require non-zero task success before expanding to the other P0
clusters. A full candidate matrix and Gate recomputation come only after the bounded diagnostics
pass; release work remains disallowed.
