# Bilingual Retrieval Diagnostic

Updated: 2026-09-11 / Evidence Remediation 26

## Decision

**Do not adopt this candidate.** On approved revision 1.0.5, translating questions and fusing
rankings increases whole-pack reachable contracts from 25/48 to 27/48, but regresses two previously
reachable cases. Ordinary critical reachability drops from 1/5 to 0/5. The four targeted critical
retrieval failures remain unresolved. The default retriever, adapters, scorer and Gate are unchanged.

This is retrieval evaluation, not answer quality, independent human review or production readiness.

## Components

| Module | Responsibility |
| --- | --- |
| `backend/app/services/rag_bilingual.py` | Label-blind BM25 rankings and equal-weight reciprocal rank fusion |
| `backend/app/reference_workload/rag_bilingual_diagnostic.py` | Query-only translation, finalized input validation, comparison, provenance and offline replay |
| `backend/tests/test_rag_bilingual_diagnostic.py` | Ranking, parsing, label isolation, fallback, replay and executed-source inventory tests |

The ranker accepts only corpus, original query, translated query and top-k. Expected source IDs and
facts are not arguments. The harness evaluates expected evidence only after obtaining candidate
rankings. All candidate modules remain opt-in and are not registered in the default execution path.

## Fixed Protocol

- Approved 1.0.5: 64 source cases including 20 critical cases; 14 frozen documents and 200 chunks.
- All 48 RAG-bearing cases are compared. Candidates apply to the 22 ordinary single-/multi-document
  cases. The other 26 preserve baseline preparations, including scope and refusal handling.
- One local query-only translation per unique ordinary question: 22 serial calls, seed 42,
  temperature 0, 256 output tokens and 60-second request timeout. No retry or translation repair.
- Translator receives a fixed system instruction and a JSON user message containing only
  `source_text`. It receives no corpus, expected source IDs, answer labels or case IDs.
- Structured output is `{ "english_query": "..." }`, with exactly one key and 1-512 characters.
  Reject duplicate keys, extra fields, blank/padded/non-ASCII output and incomplete finish reasons.
  These are structural checks; they do not certify faithful translation or instruction resistance.
- Existing SQLite FTS5 BM25 uses title/body weights 2:1 and the existing Korean-bigram tokenization.
  Fusion uses both BM25 language rankings, a fixed window of 50 and equal weights, summing
  `1 / (60 + rank)`. Return only five matching chunks; no irrelevant padding or label-based tuning.
- Failed translation retains its error and falls back to the unchanged baseline for the diagnostic
  variants. Failures stay in the denominator and block advancement to answer diagnostics.
- Compare baseline lexical overlap, original-query BM25, translated-query BM25 and bilingual RRF.
  No variant, prompt, fusion parameter or label was tuned after viewing this run's results.

The ranking implementation reuses [SQLite FTS5 BM25](https://www.sqlite.org/fts5.html#the_bm25_function).
Fusion follows the rank-based approach documented by
[Elasticsearch RRF](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion),
without adding Elasticsearch as a dependency. Translation uses the existing local
[Ollama structured-output API](https://docs.ollama.com/capabilities/structured-outputs).

## Results

Reachability means that one complete approved evidence group is present in top-5, not merely that
one useful document was retrieved. Comparisons below use the same finalized 1.0.5 labels throughout.
Do not compare them directly with earlier 1.0.4 scores, whose source contracts differ.

| Variant | All RAG /48 | Ordinary /22 | Critical ordinary /5 | Gains | Regressions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline lexical overlap | 25 | 6 | 1 | 0 | 0 |
| Original-query BM25 | 23 | 4 | 0 | 0 | 2 |
| Translated-query BM25 | 27 | 8 | 0 | 4 | 2 |
| Bilingual BM25 RRF | 27 | 8 | 0 | 4 | 2 |

Both translated candidates gain KO-RAG-004, KO-RAG-007, KO-RAG-008 and KO-RAG-012. Both regress
KO-RAG-002 and KO-RAG-011. Fusion and translated-only retrieval have the same pass/fail outcomes;
this does not mean that their full rankings or scores are identical. Nonordinary cases contribute
the same 19 reachable contracts to every variant, without new live answer-generation evidence.

All 22 translations pass structural parsing; this is **not 22/22 translation accuracy**. For example,
KO-RAG-002 translates to `What should be checked before Deployment Gate execution?`, dropping the
original technical term `Preflight` despite the preservation instruction. The required Preflight
section ranks 62 under translated BM25. No semantic approval is inferred from a valid JSON object.

Translation also does not solve the multi-source requirement. Translated BM25 ranks the signed
release section 2, but its paired workflow source 11. The model-identity and publisher sources rank
12 and 2; the incident case needs sources ranked 1, 22 and 29. A relevant single hit cannot satisfy
these AND contracts. These are diagnostic ranks, not proof of answer entailment or causal attribution
for every failure. In particular, removing a term is not the sole cause of the two regressions:
original-query BM25 also regresses those cases.

## Runtime And Cost

The existing `qwen2.5:1.5b` model ran on Ollama 0.31.1, GGUF/Q4_K_M. Registry-observed model digest:
`65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`.

The live report records 22 translation HTTP calls, 2,531 prompt tokens and 473 completion tokens.
Summed request wall time is approximately 15.0 seconds; the whole run is approximately 16.6 seconds.
These are one local run's measurements, not a latency benchmark or a cost-saving claim. The registry
reports context length 32,768; effective per-request context allocation was not independently verified.
Model/runtime registry identity was checked before and after, not cryptographically attested per call.

There were zero task-answer calls, zero output reviews and no application evidence DB writes from
this diagnostic. Windows/Docker replay reuses the same 22 captured translations and makes zero new
model calls. Reported request usage in replay describes the original calls, not additional usage.

## Evidence And Reproduction

Artifacts under `artifacts/rag-bilingual/2026-09-11/`:

- `live.json` and `live.translations.jsonl`: fixed protocol, input/source hashes, original requests,
  responses, usage, errors, all 48 rows and runtime identity.
- `replay-windows.json` and `replay-docker.json`: offline reranking with identical saved translations.
- `live-harness.py`: exact original live harness, retained before fixing Docker source inventory.
- `before.json`, `after.json`, `official-protection.json`: read-only official evidence protection.

The original Windows live inventory was complete. Afterwards, the harness was corrected to locate
executed app files independently of the workspace layout: Docker runs code under `/app`, while data
lives under `/workspace`. The original harness is preserved at its recorded hash. Replays use the
corrected inventory, include 254 executed app source files, and agree on source hashes across hosts.
This change affects provenance collection, not translation requests or retrieval algorithms.

All 48 rows match exactly between live, Windows replay and Docker replay. Content hashes, journal
hashes, original harness identity and replay request/response binding were independently checked.
Known development cases and one model/seed were used; this is not a held-out generalization result.

| Artifact | Exact file SHA-256 |
| --- | --- |
| Live report | `ed0dde864fedd8417e054c34a084890062079cfcc798bb9ac26febd8b23941e8` |
| Live translation journal | `3a23a55b39e617dae02c82a3f72d40788d1b233f6f0b46089c9f48680f8a5a61` |
| Original live harness | `09f3c32ddd24e4861fe2b4ebae0d4a5b79601f2dac02273be6f3dca43085b294` |
| Windows replay | `7666df3065125dfa37fd0f4af2c579c8f40111cb63d38bf94f37eea50b98f4a0` |
| Docker replay | `8550fa806ac9bb10d794e9ebacc77ba7d3be466052f130dc9770c1206a876ba4` |

Live report internal content hash:
`16682018ca02cbf6e0bbab5b43f07ad0397586ccb3b00a960a6808ea6d4ec8e5`.

Run from the repository root with the tested image. Use a new output path for each run; existing
report/journal paths are rejected. The first command makes 22 fresh local translation calls; the
second uses only saved responses and does not require a live Ollama endpoint.

```powershell
docker compose run --rm --no-deps backend python -m app.reference_workload.rag_bilingual_diagnostic --repository-root /workspace --base-url http://ollama:11434 --output /artifacts/rag-bilingual/new-live.json
docker compose run --rm --no-deps backend python -m app.reference_workload.rag_bilingual_diagnostic --repository-root /workspace --replay /artifacts/rag-bilingual/2026-09-11/live.json --replay-sha256 ed0dde864fedd8417e054c34a084890062079cfcc798bb9ac26febd8b23941e8 --output /artifacts/rag-bilingual/new-replay.json
docker compose run --rm --no-deps backend python -m pytest -q -p no:cacheprovider
```

## Verification And Remaining Work

New tests: 48 passed. Docker full backend: 844 passed, with two upstream deprecation warnings.
Host and Docker Ruff checks and the backend image build passed. No API/UI/schema changes.

Existing Docker containers were restarted, not recreated; the running backend image remains
`2388942c2481acd7553297e1d23a25e99ed92cba4c19765475197717b724178d`. The separately built/tested
image is `14f217a7819578ad9bd7942d818a9220c239bd2a3ed9f64b7cb776825b9ab85d`.

Official evidence remains BLOCKED, 110 failed critical observations, 384 runtime results, actual-output
human review 0/30, and not_production_ready. Canonical, finalized 1.0.4 and approved 1.0.5 sources are
preserved. The official-protection CLI also re-scores the same earlier 60 canary outputs; those are
not fresh calls from this experiment. Periodic background operational jobs are outside that claim.

The next experiment must address technical-term loss and the ranking of complementary evidence,
while keeping query/label separation and whole-pack regression checks. A no-regression retrieval
candidate would still require fresh answer/citation evaluation and separate review before adoption.
The current experiment stops at its failed retrieval advancement check; aggregate gains are not
grounds to bypass the four unresolved critical failures.
