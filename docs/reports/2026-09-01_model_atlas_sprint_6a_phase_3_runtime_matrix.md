# Model Atlas Sprint 6A Phase 3 Runtime Matrix Report

Recorded: 2026-09-01

## Executive result

Sprint 6A Phase 3 is complete. A user-supplied, report-bound attestation was validated, all 64
reference cases including all 20 critical cases were approved, and the existing workload entities
were bootstrapped idempotently. The new runtime-matrix orchestrator then executed three concrete
Ollama configurations against the approved Korean operator workload.

The final matrix stored 384 Results and 384 Inference Metrics: 64 distinct cases, two trials per
case, for each of three configurations. It observed two real local model artifacts and retained
their exact SHA-256 digests. Rebuilding the comparison from the exact stored Benchmark Run IDs
produced the same comparison hash.

This is a successful evidence-pipeline result and an unsuccessful model-quality result. Every
configuration has critical-case failure of at least 0.90 and Agent task success of 0.0. Phase 3 is
ready as portfolio evidence, but no tested configuration is a release candidate and production
readiness remains `not_production_ready`.

## Review and bootstrap evidence

| Item | Recorded value |
| --- | --- |
| Review report SHA-256 | `4e3c3eb261005c6dafaf7b675e3e4698f54fc0074a3823e9338a3fda2a1774b0` |
| Review event time | `2026-09-01T08:43:24+00:00` |
| Approved cases | 64 of 64 |
| Approved critical cases | 20 of 20 |
| Workload profile ID | `f353d107-5257-46dc-8213-1becd92a3d64` |
| Evaluation suite ID | `d2649432-15ee-436d-a733-a36906fb4aec` |
| Acceptance policy ID | `8405ca90-8558-4c57-a8b4-306235d663d2` |
| Corpus SHA-256 | `b6db4643768f1e9735507747aa88e54f93c7a3099dcb98ffbf6e9ac3e322e3cf` |
| Suite SHA-256 | `2762c092dc552b3a46f18f9ac9362e1b77fad035932a573853535854175693d8` |
| Policy SHA-256 | `685845b4a980a8b000128d9af779703d841d6df049e7b927b599cbc89ad76b40` |

A second bootstrap resolved the same IDs and hashes and created no duplicate entities. The source
review approves case contracts only; it is not human review of model outputs.

## Runtime identity

Ollama `0.31.1` served both artifacts through its OpenAI-compatible endpoint.

| Model | Observed SHA-256 | Approximate size |
| --- | --- | ---: |
| `qwen2.5:0.5b` | `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67` | 397 MB |
| `qwen2.5:1.5b` | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` | 986 MB |

Each deployment identity also binds hardware profile, context length, generation settings, Prompt
Version, corpus/retriever version, Tool registry version, concurrency, and adapter descriptor.
Every final Result records `data_source=local_actual_runtime` and
`adapter_version=openai-compatible-v7`.

## Stored comparison

| Configuration | Model / prompt | Mean quality | JSON valid | Tool select | Tool args | Tool exec | RAG grounded | Unsupported | Critical fail | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | `0.5b` / v1 | 0.224609 | 0.307692 | 0.6250 | 0.28125 | 0.25000 | 0.000000 | 1.000000 | 0.95 | 6,404.735 |
| `medium-candidate` | `1.5b` / v1 | 0.307664 | 0.394231 | 0.9375 | 0.37500 | 0.37500 | 0.082589 | 0.909722 | 0.90 | 12,448.586 |
| `prompt-variant` | `1.5b` / v2 | 0.301977 | 0.403846 | 1.0000 | 0.34375 | 0.34375 | 0.066369 | 0.944444 | 0.90 | 12,477.137 |

The 1.5B v1 configuration is the strongest overall candidate among those tested. Against the 0.5B
baseline it improves mean quality by 0.083055, Tool selection by 0.3125, Tool argument validity by
0.09375, Tool execution by 0.125, and RAG groundedness by 0.082589. It reduces unsupported claims
by 0.090278 and critical failure by 0.05, at the cost of approximately 6,044 ms additional P95
latency.

The v2 prompt improves JSON validity, Tool selection, and sequence success over v1 on the same
1.5B model. It regresses mean quality, Tool argument/execution success, groundedness, unsupported
claims, and latency. Prompt changes therefore require multidimensional comparison rather than a
single format-compliance score.

Retrieval recall is 0.638889 for every entry because corpus and retriever are intentionally held
constant. All entries have zero timeout and zero OOM rates. Their strict evaluation success rates
are only 0.0625, 0.0938, and 0.0859, and all have zero Agent task success and zero successful RAG
cases. The evidence diagnoses model limitations rather than concealing them.

## Evidence identity

| Item | Value |
| --- | --- |
| Baseline run | `2124b9f7-82f2-483f-939b-83a18400b9ab` |
| Medium run | `698428e8-59ec-4353-8f7d-ea592e60a206` |
| Prompt-variant run | `9da6d961-1e8a-460d-848e-b5c29ff2b59f` |
| Matrix SHA-256 | `cfcf986f8e3a884a385a9873e370ccbe6f544b9628b15036db067033504845aa` |
| Comparison SHA-256 | `0c92a7b4793c2dd69d02a03a88e68ab19a233512dc50e1bc57ac7c6dcf716cd9` |
| Result-file SHA-256 | `d6e717325c0202850630ba9c04ad929e13e010f1ea2335eb3b4bca7685aa3867` |
| Result artifact | `artifacts/reference-workload/runtime-matrix-portfolio-v7.json` |

The output reports all four Portfolio completion checks as true: at least 60 active cases, at
least three completed configurations, at least two distinct artifacts, and at least 60 Results in
every completed run. SQL cross-checking confirmed 64 distinct cases and exactly two trials in each
run. Re-running `compare-runtime` retained the same comparison hash.

## Implementation

The orchestration is implemented in `backend/app/reference_workload/runtime_matrix.py` and exposed
through `run` and `compare-runtime` CLI commands. It validates environment names, runtime/model
availability, Ollama version, and observed model digest; resolves existing entity contracts; calls
the existing benchmark execution service; preserves unavailable and failed entries; and builds a
comparison from persisted evidence.

The existing OpenAI-compatible adapter now applies the configured Prompt Version, supports an API
key environment-variable name without persisting its value, and requests JSON objects for
structured cases. Expected answers, expected Tool calls, and scorer-only reference context are no
longer sent to the model. Public bounded Tool descriptors remain available to the model.

Benchmark execution accepts an explicit case-ID subset for deterministic Smoke sampling and an
execution-scoped RAG registry. Agent execution receives the same scoped registry. Local/private
OpenAI-compatible endpoints are accepted for local-only workload execution while remote endpoint
rules remain fail closed.

## Changed source and contract files

- `Makefile`
- `backend/app/reference_workload/__init__.py`
- `backend/app/reference_workload/cli.py`
- `backend/app/reference_workload/review_assistance.py`
- `backend/app/reference_workload/review_ui.py`
- `backend/app/reference_workload/runtime_matrix.py`
- `backend/app/schemas/entities.py`
- `backend/app/services/agent_execution.py`
- `backend/app/services/benchmark_execution.py`
- `backend/app/services/deployment_gate_resources.py`
- `backend/app/services/deployment_gate/evidence.py`
- `backend/app/services/inference_adapters/openai_compatible.py`
- `backend/tests/test_reference_workload_bootstrap.py`
- `backend/tests/test_reference_workload_cases.py`
- `backend/tests/test_reference_workload_review_assistance.py`
- `backend/tests/test_reference_workload_runtime_matrix.py`
- `reference_workload/README.md`
- `reference_workload/review_assistance.csv`
- `reference_workload/review_assistance.html`
- `reference_workload/review_assistance.json`
- `reference_workload/review_attestation.json`
- `reference_workload/review_manifest.jsonl`
- `reference_workload/runtime_matrix.json`
- `docs/extension_contracts.md`
- `docs/project_status.md`
- `docs/reference_workload.md`
- `docs/reference_workload_review_automation.md`
- `docs/reference_workload_runtime_matrix.md`
- `docs/reports/2026-09-01_model_atlas_assisted_case_review.md`
- `docs/reports/2026-09-01_model_atlas_sprint_6a_phase_3_runtime_matrix.md`

The assisted-review JSON, CSV, and standalone HTML are retained as the exact review aid bound to
the attestation. Generated runtime result JSON is retained under `artifacts/reference-workload/`.

## Verification

```text
Docker backend pytest: 212 passed, 1 upstream deprecation warning
Docker backend Ruff: all checks passed
Local backend pytest: 211 passed, 1 skipped, 2 warnings
Frontend lint: passed
Frontend Next.js 16.2.10 production build: passed
Docker Compose configuration: passed
Alembic upgrade/current: 202608040001 (head)
Final matrix: 3 completed, 0 failed, 0 unavailable, 384 Results, 2 artifacts
Stored comparison replay: same comparison SHA-256
One-off Docker run containers remaining: 0
```

The local skip is the expected Windows symlink case; it passes in Linux Docker. The additional
local warning is the pytest cache-path permission warning. Neither changes application behavior.

## Decision and next phase

Phase 3 is complete and its local actual-runtime evidence is reproducible. No quality Gate,
release decision, output-review minimum, or production evidence was fabricated. The next
specification unit is Phase 4: aggregate read model, API, and guided `/reference-workload` UI with
failure-first review links. Phase 5 must derive Gate and report outcomes from stored evidence.
