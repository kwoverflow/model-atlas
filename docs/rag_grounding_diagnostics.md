# RAG Retrieval And Grounding Diagnostics

Updated: 2026-09-10, Remediation 23

## Boundary

These are opt-in experiments, not registered production adapters or retrievers. The default
`lexical-overlap-v1`, `openai-compatible-v21`, RAG scorer, reviewed 1.0.4 case contracts, and
Deployment Gate are unchanged. There are no application database writes from this diagnostic.
The SQLite database used for candidate retrieval is in-memory and closed after each query.

The reference pack has 48 approved cases containing RAG contracts. Only the 22 ordinary
single-/multi-document RAG cases use candidate retrieval. The other 26, including scope,
refusal and Agent-related cases, retain the original preparation. Equality checks cover that
fallback; they are not new live-model success measurements.

## Components

| Module | Responsibility |
| --- | --- |
| `backend/app/services/rag_bm25.py` | Label-blind ranking over public query and corpus |
| `backend/app/services/inference_adapters/cited_rag.py` | Paired source/quote response and exact provenance validation |
| `backend/app/reference_workload/rag_grounding_diagnostic.py` | Offline comparison, live ablations, request journal and hashes |
| `backend/tests/test_rag_grounding_diagnostic.py` | Boundary, request-format, regression and contract tests |

### Retrieval Candidate

`sqlite-bm25-ko-bigram-v1` uses NFKC normalization, lowercase ASCII terms, Korean whole tokens
plus adjacent two-syllable tokens, and SQLite FTS5 BM25 with title/body weights 2:1. Chunk IDs
break ties deterministically. It never reads expected IDs or required facts. Evaluation labels
are applied only after the ranking is complete.

The core BM25 implementation comes from [SQLite FTS5](https://www.sqlite.org/fts5.html#the_bm25_function).
SQLite ranks lower scores first; the returned diagnostic score is the negated, positive value.
It is not a probability and cannot share the old overlap threshold. The harness requires
`min_score=0`, preserves `top_k=5`, and never pads empty results with irrelevant documents.
Queries are limited to 4096 characters and 256 distinct tokens. FTS expressions use sanitized,
quoted tokens and bound SQL parameters. No new Python dependency is required, but the Python
SQLite build must support FTS5. Its version is recorded in each report.

This is not a multilingual semantic retriever. Korean morphology, generic Korean fragments,
and English-only source text remain limitations. More algorithmic complexity is not evidence
of improved retrieval; the whole-pack comparison determines whether this candidate can advance.

### Paired Evidence Candidate

`cited-rag-candidate-v1` changes the ordinary RAG generation prompt and response representation:

```json
{
  "answer": "A concise answer in Korean",
  "evidence": [
    {"chunk_id": "retrieved-source-id", "quote": "An exact source excerpt"}
  ]
}
```

The validator requires one to three pairs, known sources, exact substrings, quote lengths
12-480 characters, and no duplicate pairs, extra fields, or duplicate JSON object keys.
It maps valid pairs to the existing `citations` and `claims` fields without changing the
model's answer or inventing missing evidence. Invalid output is retained and fails the candidate
contract. Raw output, normalized output, validation errors and the actual HTTP exchange are saved.

Exact quotation proves where text came from. It does **not** prove that the free-form answer is
correct, complete, relevant or entailed by the quote. The existing semantic/citation/retrieval
checks still run. In particular, the old citation score means approved chunk-ID membership,
not an independent semantic attribution judgment. Quoted claims are not directly equivalent
to the baseline's generated claims, so improved lexical grounding alone is not a quality win.

### Isolation And Reproduction

Supported ablations:

| Variant | Retrieval | Response |
| --- | --- | --- |
| `baseline` | Existing overlap | Existing JSON answer/citations/claims |
| `bm25` | Candidate | Existing response |
| `paired` | Existing overlap | Candidate paired source/quote |
| `bm25_paired` | Candidate | Candidate paired source/quote |

The default live experiment compares `baseline` and `paired` on the five ordinary critical RAG
cases. It uses the existing `qwen2.5:1.5b`, temperature 0, seed 42, one trial, serial execution
and 768 output tokens for both variants. Variant order rotates by case. This new token budget
must not be compared directly with the earlier 384-token canary. The matrix declares an 8192
context length, but this standalone harness does not verify or force the effective runtime
context window. Runtime identity is probed before and after the experiment.

From the repository root, using a freshly built backend image:

```powershell
docker compose run --rm --no-deps backend python -m app.reference_workload.rag_grounding_diagnostic --repository-root /workspace --output /artifacts/rag-grounding/new-offline.json
docker compose run --rm --no-deps backend python -m app.reference_workload.rag_grounding_diagnostic --repository-root /workspace --base-url http://ollama:11434 --live --output /artifacts/rag-grounding/new-live.json
```

Use repeatable `--variant` arguments for a different explicit ablation. Existing report or
journal paths are rejected. A status of `running` means incomplete, not valid evidence.
Each observation is flushed to the journal; a completed report binds the journal, all app
source files, revision JSON files, runtime matrix and corpus hash. Runtime/source changes or
a missing JSON-schema request contract invalidate the report. Errors remain in the denominator.

The adapter receives no expected facts or approved evidence IDs. It receives an empty
`expected_output_json={}` shape marker solely to enable the existing adapter's JSON-mode switch.
Request-level tests verify that the actual body includes `response_format.type=json_schema`.
This distinction is important: setting the marker to `None` disables constrained output in
the legacy adapter, even when the category is ordinary RAG.

## Evidence And Promotion

See [the experiment report](reports/2026-09-10_rag_grounding.md). The initial unconstrained
attempt is explicitly invalidated in `artifacts/rag-grounding/2026-09-10/live.invalidated.json`;
neither its partial rows nor its unfinished report should be counted as model-quality evidence.

Promotion requires no unexplained whole-pack regression, separate evidence-ID/fact-contract
review where needed, independently reviewed answer attribution, and fresh multi-configuration
evaluation. Do not modify approved labels to make a candidate pass. The diagnostic embeds the
five existing contracts and their expected source excerpts as review material, not as approvals.
