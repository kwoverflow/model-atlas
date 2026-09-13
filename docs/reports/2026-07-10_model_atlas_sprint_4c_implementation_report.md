# Model Atlas Sprint 4C Implementation Report

Date: 2026-07-10

Status note: This report preserves the Sprint 4C completion state. Sprint 4D has since implemented
the recommended Runtime Reliability Pack and advances current Gate evidence to snapshot v5. See
`2026-07-11_model_atlas_sprint_4d_implementation_report.md` for current verification.

## Implemented

- Versioned local RAG corpus registry and corpus hash.
- Deterministic lexical retriever descriptor and execution.
- Immutable RAG deployment configuration using `retrieval_config_json`.
- Pre-generation retrieval and sanitized adapter context.
- Structured answer, citations, and atomic claims contract.
- Retrieval recall, citation precision/recall, groundedness, and unsupported-claim evaluation.
- RAG scorer and five Gate metrics.
- Ten-case RAG suite and dedicated Acceptance Policy.
- Corpus and retriever APIs.
- Benchmark RAG summaries and case-level traces.
- RAG execution detail UI and Gate-to-trace navigation.
- Gate evidence snapshot v4 RAG provenance.

## Architecture Decisions

- Retrieval executes before adapter generation inside the benchmark orchestration boundary.
- The stored case remains unchanged; adapter-facing input is temporarily replaced with sanitized
  retrieved context and immediately restored.
- Expected relevant chunk IDs are not sent to the adapter.
- Corpus, retriever, and RAG trace implementations expose explicit versions.
- Existing result metadata and execution logs store RAG evidence, avoiding a database migration.
- RAG metrics use the existing policy engine and Gate verdict rather than a parallel approval path.
- Lexical retrieval and token-support groundedness remain explicit heuristics, not semantic judges.

## Files Added

- `backend/app/services/rag_evaluation.py`
- `backend/app/schemas/rag_evaluation.py`
- `backend/app/api/v1/routes/rag_evaluation.py`
- `backend/app/seed/rag_evaluation.py`
- `backend/tests/test_rag_evaluation.py`
- `backend/tests/test_rag_evaluation_pack.py`
- `frontend/components/RagEvaluationTracePanel.tsx`
- `docs/rag_evaluation.md`
- `docs/reports/2026-07-10_model_atlas_sprint_4c_implementation_report.md`

## Files Modified

- Benchmark orchestration and response/detail contracts.
- Mock and OpenAI-compatible adapters.
- Scorer registry, Gate metrics, critical-case outcomes, and snapshot provenance.
- Base seed reset behavior and Makefile seed targets.
- Frontend benchmark form, API types/client, execution detail, and Gate detail.
- README, architecture, data contract, deployment gate, extension contracts, Golden Demo, project
  status, roadmap, submission, and handoff documents.

## API Changes

- Added `GET /api/v1/rag/corpora`.
- Added `GET /api/v1/rag/corpora/{corpus_id}`.
- Added `GET /api/v1/rag/retriever`.
- Extended benchmark execution create/detail responses with `rag_evaluation_summary` and
  `rag_traces`.
- Extended Gate critical-case outcomes with `rag_evaluation_status`.
- Gate evidence snapshot v4 adds corpus, retriever, and RAG evaluation versions.

## Compatibility Notes

- Existing routes and fields remain available; new fields are additive.
- Runs without RAG cases receive an empty RAG summary.
- Existing benchmark, result, metric, and log tables are unchanged.
- Existing Deployment Configuration already owned `retrieval_config_json`; Sprint 4C activates it
  through a new immutable configuration rather than mutating an old one.
- Gate snapshot v2/v3 records remain readable; new Gate evaluations create v4.
- Tool Calling and non-RAG benchmark paths retain their previous behavior.

## Tests Added

- Corpus registry version/hash and descriptor coverage.
- Relevant lexical retrieval and recall.
- Ground-truth leakage prevention.
- Perfect citation and grounded claim evaluation.
- Invalid citation and unsupported claim failure.
- Invalid retrieval configuration trace behavior.
- RAG metadata, log, and summary provenance.
- End-to-end ten-case execution, APIs, Gate metrics, and approved policy path.
- Idempotent RAG seed behavior.
- Critical unsupported answer and blocked Gate path.

## Verification Results

```text
Backend pytest: 106 passed, 1 upstream deprecation warning
Backend Ruff: passed
Frontend typecheck: passed
Frontend ESLint: passed
Frontend production build: passed
Docker Compose configuration validation: passed
```

Compose structure validated successfully. Live container health was not re-run because Docker
named-pipe access is unavailable inside the current sandbox.

## Manual UX Verification

- The benchmark form shows corpus and retriever versions.
- Completed RAG runs show retrieval, citation, and unsupported-claim summaries.
- The execution detail shows retrieved chunks, rank and score, relevance/citation state, answer,
  claim support, errors, and raw trace.
- Gate critical RAG rows link to the originating benchmark trace.
- Type checking, lint, and production route generation passed.
- A live localhost browser pass is not claimed because the host browser policy blocks local
  navigation in this task.

## Known Limitations

- Corpus and retrieval are deterministic local fixtures.
- No ingestion, chunking, embeddings, vector database, hybrid retrieval, or reranking.
- Token overlap is not a semantic entailment judge.
- The model is called once after retrieval; conversational retrieval recovery is not evaluated.
- Local-authored evidence still requires judge/human calibration for stronger trust states.

## Recommended Next Sprint

Sprint 4D should implement a Runtime Reliability Pack with repeated trials, P50/P95/P99 latency,
concurrency, context stress, timeout, OOM, runtime comparison, and reliability-specific Gate rules.
