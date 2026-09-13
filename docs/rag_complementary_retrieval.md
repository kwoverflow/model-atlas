# Guarded Complementary Retrieval

Updated: 2026-09-12 / Evidence Remediation 27

## State

Implementation, live execution and Windows/Docker replays are complete. Complementary selection is
rejected: ordinary evidence coverage falls from 6/22 to 2/22, with four regressions. Guarded three-list
RRF improves this known development set to 8/22 without regressions, but still satisfies only one of
five ordinary critical contracts. Neither candidate is adopted. Default retrieval, approved labels
and official evidence remain unchanged.

## Results

Measured on approved 1.0.5, with unchanged top-k=5 and mandatory evidence groups:

| Variant | All RAG /48 | Ordinary /22 | Critical ordinary /5 | Gains / regressions against baseline |
| --- | ---: | ---: | ---: | --- |
| Default lexical | 25 | 6 | 1 | 0 / 0 |
| Previous bilingual RRF | 27 | 8 | 0 | 4 / 2 |
| Guarded bilingual RRF | 27 | 8 | 1 | 3 / 1 |
| Guarded three-list RRF top-5 | 27 | 8 | 1 | 2 / 0 |
| Complementary selection | 21 | 2 | 0 | 0 / 4 |

The 26 unchanged fallback cases account for 19 reachable contracts in every row. These are retrieval
coverage counts, not generated-answer correctness or overall model pass rates. The previous bilingual
row reuses pinned historical translations/results, not a new translation run.

Three-list RRF gains KO-RAG-007 and KO-RAG-008 while preserving all six baseline successes. Literal
repair alone restores KO-RAG-002 relative to the previous bilingual candidate, but also loses that
candidate's KO-RAG-004 gain. Guarded bilingual still regresses KO-RAG-011. Complementary selection
retains only KO-RAG-010 and KO-RAG-MULTI-008; it regresses KO-RAG-002, 005, 009 and 011.

The candidate pool contains all mandatory evidence for all 22 ordinary cases, including all five
critical cases. Selection, not absence from this top-50 pool, is the measured bottleneck. This is an
observation on the known pack, not evidence that candidate recall generalizes to new questions.

| Critical case | Required pool ranks | Required sources retained in final selection | Observed loss |
| --- | --- | --- | --- |
| KO-RAG-001 | 12 | 0/1 | Discarded in second shortlist round |
| KO-RAG-002 | 2 | 0/1 | Discarded in first shortlist round |
| KO-RAG-MULTI-001 | 5, 9 | 1/2 | Rank-9 signed-decision evidence discarded in first round |
| KO-RAG-MULTI-002 | 11, 6 | 0/2 | Discarded across first and second rounds |
| KO-RAG-MULTI-003 | 1, 14, 16 | 1/3 | Incident/paging evidence discarded across shortlist rounds |

All 168 local requests completed with valid response contracts: three guarded translation retries
and 165 source-selection calls. There were zero recorded candidate execution failures, but selection
quality was poor. All 22 translations pass the literal guard after retry; semantic accuracy remains
unverified. There were no task-answer calls, new model downloads or model training.

The existing qwen2.5:1.5b Q4_K_M/Ollama 0.31.1 run took about 16 minutes 36 seconds. Saved response
usage totals 363,311 prompt tokens and 1,974 generated tokens; maximum reported prompt length is
3,215 tokens. Selection used 6-9 calls per ordinary case. This cost, including reuse of 19 historical
translations, is not a fresh end-to-end production latency benchmark and does not justify adoption.

Next work should isolate ranking/selection quality and cost, using the successful guarded pool as
an experimental starting point. Compare a separately versioned selector with fixed inputs, preserve
baseline regression checks, and include independent questions before claiming generalization. Do not
add expected source IDs to the runtime path or enlarge top-k merely to meet known evidence labels.
Fresh answer/citation evaluation remains gated on retrieval readiness.

## Implementation

| Module | Responsibility |
| --- | --- |
| `backend/app/services/rag_complementary.py` | Literal-term guard, bounded native requests, public candidate pool, hierarchical source selection |
| `backend/app/reference_workload/rag_complementary_diagnostic.py` | Pinned prior evidence, selective translation retry, serial execution, raw journal, comparison and replay |
| `backend/tests/test_rag_complementary_diagnostic.py` | Input/response validation, budgets, source identity, failure handling and label isolation |

The previous bilingual implementation and its artifacts are not overwritten. This is a separately
versioned opt-in diagnostic, not a registered production retriever or a new trained model.

## Literal Preservation

The guard extracts ASCII letter/number terms from the public question after NFKC normalization.
It checks case-insensitive whole-term boundaries, retaining punctuation in versions, dotted names,
underscores, slashes and identifiers. Hyphen-to-whitespace variation is allowed for terms such as
`burn-rate`. A match inside a longer word does not count. It does not use a case-specific dictionary,
expected source IDs, answer facts or human-review fields.

The pinned 2026-09-11 translation report contains three detected omissions: `Preflight`, `Calling`
and `schema`. Only those questions receive one new translation request with their required terms.
The other 19 captured translations are reused. Failed retries remain failures and use the baseline;
missing words are never silently appended to the model output. Original and retried text are kept.

This is a literal-preservation guard, not full semantic validation. Korean-only concepts, negation,
relationships and paraphrase correctness may still be wrong even when the guard passes. Some faithful
paraphrases of identifiers are conservatively rejected; the rule is not a translation-accuracy metric.

## Candidate Selection

1. Validate approved revision 1.0.5 and the previous report's exact hash, corpus and case identities.
2. Build original-query and guarded-English-query BM25 rankings, each with a 50-result window.
3. Fuse them with the public positive-score baseline top-5 using equal-weight RRF, constant 60.
   Keep at most 50 candidates. No expected evidence information participates in this computation.
4. Show complete candidate titles and text to the local model using temporary aliases such as S1.
   Actual chunk hashes, approval status and expected facts are not provided in the selection request.
5. When all sources do not fit, partition them without truncation into batches of at most 12 sources,
   shortlist at most three from each batch, and repeat until a final request fits. The final selection
   contains at most five sources, intended to cover complementary parts of the question.
6. Evaluate approved evidence-group coverage only after selection. Store pool coverage separately
   so failure to retrieve a source is distinguishable from failure to select an available source.

The selection prompt treats questions and source text as untrusted data. The response schema permits
only supplied aliases. Duplicate, unknown or excessive selections, extra fields, malformed JSON,
incomplete generation and unexpected model names are rejected. Empty selection is valid but is not
repaired or padded into a successful answer. A valid ID list does not establish semantic correctness.

Requests use local Ollama `/api/chat`, explicit `num_ctx=16384`, `num_predict=256`, temperature 0,
seed 42, `truncate=false`, `shift=false`, no streaming and a 120-second timeout. Each serialized
request is capped at 12,000 UTF-8 bytes. A single source too large for the budget is rejected rather
than sliced. Selection is limited to 12 calls per case; exhaustion is retained as a failure.

Listwise passage comparison is informed by the
[RankGPT research](https://arxiv.org/abs/2304.09542), but this implementation is a bounded
hierarchical selection experiment, not a reproduction of that paper's method or results. It reuses
the existing SQLite BM25/RRF primitives and the existing local model. Native request controls follow
the [Ollama chat API](https://docs.ollama.com/api/chat) and
[context configuration](https://docs.ollama.com/modelfile).

## Comparison Boundary

All 48 RAG-bearing cases are compared. Only the 22 ordinary single-/multi-document cases use the
candidate; the other 26 retain their baseline preparation. The five ordinary critical cases remain
a separately reported subset. Queries, top-k=5, mandatory evidence groups, expected facts, refusal
requirements, criticality and weights are not changed.

The fixed ablations are baseline lexical overlap, the saved previous bilingual result, guarded
two-language fusion, three-list candidate-pool RRF top-5, and complementary source selection.
Candidate execution errors and blocked translations retain baseline output while remaining visible
as failures. A fallback success must not be presented as a successful model selection.

Eligibility for a subsequent answer diagnostic requires no candidate execution failures, no
baseline-to-candidate regressions, and all five ordinary critical retrieval contracts satisfied.
This does not authorize default adoption or Gate promotion. No task-answer generation, application
evidence DB writes or human-output approvals are performed by this experiment.

These are known development cases, one local model and one seed. Neither the model's preferences
nor source-ID validity constitutes independent human review. Source order and hierarchical
shortlisting can affect results; an earlier discarded source cannot be recovered by the final stage.
Scores on selected chunks remain their candidate-pool RRF scores, not model confidence scores.

## Audit Trail

Artifacts are isolated under `artifacts/rag-complementary/2026-09-12/`. The live report binds its
raw request journal, prior report, corpus, source inventory and before/after runtime identities.
Each request preserves its exact body, response or error, request hash and measured latency.
Offline replay checks the same request sequence and content, consumes every saved request, and
recomputes selection and all case metrics without new model calls. Incomplete reports cannot be
used as replay evidence.

The original live harness is preserved in `live-harness.py`. The only subsequent application change
adds `--previous` for Docker's separate `/artifacts` mount, retaining the exact pinned file hash.
Ranking, prompts and selection logic are unchanged; the replay source inventories match each other.
Official before/after snapshots and
their comparison are separate from candidate scores and do not rewrite the 384 historical results.

### Artifact Hashes

Paths below are relative to `artifacts/rag-complementary/2026-09-12/`:

| File | SHA-256 |
| --- | --- |
| `live.json` | `7f7536daba6baf4c20ba2a0d30a1856f2b4d854a7a3f614ecb9f84a69c5be15a` |
| `live.requests.jsonl` | `1aea3e3c1ea5231d320b558d34a9d18a10ea07630dee1747573366b1705874da` |
| `live-harness.py` | `07799e5a669f8fd2e2ce1d82a22a749daba4f83b4393a2fb6071b370f67948f3` |
| `replay-windows.json` | `2cfab8ce9cf5110d5951fd83386de99922c8642d9d0a11fd71210ebfb21d7f18` |
| `replay-docker.json` | `386f0562091f06f684f294fefaa3d46247ed7b79612104b706f0622112df0315` |
| `before.json` | `906096d7a71b92d92169a1679dcc25c27811dfaa2632b6fde1a0fb6ced8e8b3e` |
| `after.json` | `0d6d6f7d213924220fd92c5dbed4b427d7f63795cc219f62da5fcb55f558a86d` |
| `official-protection.json` | `52653b2e35461fed96760b6922bb298fbe3cdbfeef6ad19a951ce18b48ddb82e` |

Live report content hash: `ac84ba49d577e00214c2f256c393a0a34f0964c33072378fc5feed3a5e0faa0a`.
All 48 result rows, 22 translation records and 168 raw request/response records match both replays
exactly, with zero new model calls. Live source and runtime before/after identities are unchanged.

Official protected state is unchanged: BLOCKED, 110 critical failure observations, 384 runtime results,
0/30 output reviews, and `not_production_ready`. Canonical/1.0.4 snapshot source checks show no added,
removed or changed paths. Approved 1.0.5 case, manifest and review hashes also match their prior values.
The protection command additionally re-scores 60 saved canary outputs with the existing versioned
evaluator; its 22-to-34 pass comparison is historical replay, not 60 fresh inferences or today's RAG
result. The running default backend image was not replaced.

## Reproduction

Use new output paths; the CLI refuses to overwrite a report or request journal. Commands below do
not rerun inference. Windows PowerShell, from `backend`:

```powershell
../.venv/Scripts/python.exe -X utf8 -m app.reference_workload.rag_complementary_diagnostic `
  --repository-root .. `
  --replay ../artifacts/rag-complementary/2026-09-12/live.json `
  --replay-sha256 7f7536daba6baf4c20ba2a0d30a1856f2b4d854a7a3f614ecb9f84a69c5be15a `
  --output ../artifacts/rag-complementary/2026-09-12/replay-windows-check.json
```

Docker, from repository root, after building the backend image:

```powershell
docker compose run --rm --no-deps backend python -m app.reference_workload.rag_complementary_diagnostic `
  --repository-root /workspace `
  --previous /artifacts/rag-bilingual/2026-09-11/live.json `
  --replay /artifacts/rag-complementary/2026-09-12/live.json `
  --replay-sha256 7f7536daba6baf4c20ba2a0d30a1856f2b4d854a7a3f614ecb9f84a69c5be15a `
  --output /artifacts/rag-complementary/2026-09-12/replay-docker-check.json
```

Omitting both replay flags executes new local inference and requires the pinned model/runtime.
It is not necessary to reproduce the saved result. Replays prove captured-run reproducibility,
not that a new nondeterministic model run would produce identical outputs.

## Test Maintenance

Focused coverage adds 57 tests, including separate/default prior-path handling with a fixed hash.
Host candidate/JWT tests: 62 passed. Final rebuilt Docker image, without test bind overrides:
901 passed, two upstream deprecation warnings. Host and Docker Ruff checks passed.
Candidate image config: `680c444d13783692663f12c013810d446f43bee5f5e58a8087bed5f9a40c791d`.

Initial Docker verification exposed two test-environment problems:
the new fixture depended on a host-layout artifact path, and a JWT test mutated the final encoded
signature character, producing a noncanonical Base64URL segment under the newly installed PyJWT.

The search unit fixture now creates an explicitly synthetic prior comparison from the approved pack;
it no longer depends on saved experiment files. The JWT fixture changes decoded signature bytes and
re-encodes them canonically, retaining the exact signature-rejection assertion and also asserting
that the header remains parseable. Production authentication code and dependency constraints are
unchanged. This is test repair, not relaxed authentication or a JWT security fix.
Dependencies remain lower-bounded rather than fully locked; future image builds may resolve different
versions. Dependency locking and the test-client deprecation warnings remain maintenance follow-ups.
