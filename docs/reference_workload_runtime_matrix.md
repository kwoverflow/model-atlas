# Reference Workload Runtime Matrix

## Environment-Owned Fault Fixture Extension (2026-09-09)

The opt-in `tool-fault-scenario-v1` executor path separates test-environment faults from generated
Tool arguments. It requires a separate Deployment Configuration, compatible single-call cases,
and `data_source=tool_fault_fixture_diagnostic`. The canonical runtime matrix and finalized 1.0.4
recovery labels are unchanged; do not enable this setting on a legacy recovery matrix and treat
rejections as new model-quality failures. Scripted executor checks are not runtime model evidence.
See [Environment-Owned Tool Fault Scenarios](tool_fault_scenarios.md).

## Current Tool Argument Boundary (2026-09-09)

Adapter v21 uses a non-repairing standalone Tool guard. It does not fill query/document IDs, remove
invalid arguments, or derive failure simulation from natural language. Document IDs must exist in
the configured corpus, and simulation requires explicit runtime authorization. Rejected calls are
skipped before Tool handler execution. Legacy Tool selection remains the default.

The new 48-result finalized-1.0.4 diagnostic records selection 44/48 and fixture execution 5/48.
Normal Tool success is 5/30; recovery is 0/18 with simulation disabled and original labels unchanged.
This diagnostic is not authoritative evidence and is not an isolated model-quality comparison.
All 36 guard rejections had zero handler attempts. The earlier compiler-v1 results below remain
historical records; their repaired success totals must not be interpreted as raw argument quality.

See `tool_argument_validation.md` and
`reports/2026-09-09_model_atlas_evidence_remediation_11_tool_arguments.md` for definitions and evidence.

Updated: 2026-09-07

## Purpose

The Sprint 6A matrix compares concrete local configurations rather than model names alone. Each
identity binds an observed model digest, runtime and version, hardware profile, context length,
generation parameters, prompt bundle, corpus and retriever version, Tool schema version, and
concurrency target.

The orchestration layer does not implement inference. It validates the matrix and calls the
existing `run_benchmark_execution` service with the existing OpenAI-compatible adapter, scorers,
Tool executor, RAG evaluator, Agent executor, reliability traces, and database entities.

## Safety And Provenance

- Endpoint and model values come from environment variables or explicit non-secret CLI flags.
- API key values are read only from the named environment variable and are never persisted.
- `/v1/models` must expose the configured model.
- The local runtime registry must expose a valid SHA-256 model digest.
- The digest is persisted on the Model Artifact and Deployment Configuration identity.
- The reference RAG registry is injected per execution; the existing global default stays intact.
- Expected answers, expected Tool choices, and scorer-only reference contracts are not sent to the
  model. Public bounded Tool descriptors are supplied instead.
- A versioned Prompt Version is applied to the actual system prompt.
- Unavailable entries retain a reason and do not count as completed evidence.

## Modes

`smoke` executes one available configuration, one trial, and at most ten category-stratified
cases. It checks wiring and cannot support a release claim.

Smoke execution uses a dedicated `Reference smoke: <entry>` Deployment Configuration and persists
`reference_workload_mode=smoke` in its runtime identity. It therefore remains visible as actual
diagnostic evidence without replacing a portfolio configuration's evidence. The aggregate read
model selects the newest run that covers every active case with at least the matrix entry's
configured trial count; a newer partial smoke run cannot displace a complete portfolio run.

`portfolio` requires at least 60 active cases, three enabled configurations, and two trials per
case. Every completed run is stored with `data_source=local_actual_runtime`. A comparison is then
rebuilt from the exact persisted Benchmark Run, Result, Inference Metric, Evaluation Case, and
Deployment Configuration records.

`diagnostic` requires one to twenty explicit `--case-id` values and runs each enabled
configuration once with `max_tokens=384`. It uses dedicated `Reference diagnostic: <entry>`
Deployment Configurations and `data_source=local_actual_runtime_diagnostic`. Diagnostic evidence
cannot replace the complete portfolio selection, satisfy portfolio completion, or authorize a
release.

## Commands

```powershell
docker compose --profile runtime up -d ollama
docker compose exec ollama ollama list

docker compose run --rm `
  -e REFERENCE_RUNTIME_BASE_URL=http://ollama:11434 `
  -e REFERENCE_MODEL_SMALL=qwen2.5:0.5b `
  -e REFERENCE_MODEL_MEDIUM=qwen2.5:1.5b `
  backend python -m app.reference_workload.cli run `
  --mode portfolio `
  --matrix /workspace/reference_workload/runtime_matrix.json `
  --output /artifacts/reference-workload/runtime-matrix-portfolio.json

docker compose run --rm backend python -m app.reference_workload.cli compare-runtime `
  --input /artifacts/reference-workload/runtime-matrix-portfolio.json

docker compose run --rm backend python -m app.reference_workload.cli run `
  --mode diagnostic `
  --matrix /workspace/reference_workload/runtime_matrix.json `
  --case-id KO-AGENT-001 `
  --case-id KO-RAG-TOOL-001 `
  --output /artifacts/reference-workload/runtime-matrix-diagnostic.json

docker compose run --rm backend python -m app.reference_workload.cli `
  audit-retrieval-contracts `
  --case-id KO-AGENT-001 `
  --case-id KO-RAG-TOOL-001 `
  --output /artifacts/reference-workload/retrieval-contract-audit.json
```

The retrieval audit exits non-zero when any scoped contract is unreachable. That is the expected
CI behavior for a blocking result; the JSON artifact is still written first.

## Verified Smoke Evidence

On 2026-09-01, Docker Ollama `0.31.1` exposed two actual local artifacts:

| Model | Observed SHA-256 | Size |
| --- | --- | ---: |
| `qwen2.5:0.5b` | `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67` | 397 MB |
| `qwen2.5:1.5b` | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` | 986 MB |

The final v7 category-stratified Smoke run ID is
`75ddfcdb-868f-43bb-a726-f2302dc3255a`. It stored five Results and five Inference Metrics for the
`0.5b` baseline, covering four RAG cases and one Tool-bearing case. Retrieval recall averaged
`0.625`. RAG groundedness was `0.0` and unsupported-claim rate was `1.0`. The structured Tool case
passed selection, argument validation, execution, and sequence checks at `1.0`. Reliability
success was `0.2`, P95 end-to-end latency was `7,749.576 ms`, and no timeout or OOM was observed.

Earlier exploratory runs used adapter descriptor v6. They remain immutable historical local
evidence but are excluded from the final v7 comparison, which resolves only the exact run IDs
written by one matrix result artifact.

These are model-quality findings, not pipeline failures. They show that a small model can choose a
plausible Tool while still violating its argument schema, and can cite retrieved chunks while
making unsupported claims. No Gate or production-readiness claim follows from Smoke evidence.

## Verified P0 Agent Diagnostic

On 2026-09-02, three four-case diagnostic iterations separated Agent plan structure from retrieval
contract quality. The final compiler-v1 run stored 12 actual Results across all three
configurations. Plan validity and action-sequence accuracy reached `1.0` for both 1.5B
configurations and `0.75` for the 0.5B configuration. Final-response rates matched those values,
while policy-violation rates fell to `0.0`, `0.0`, and `0.25` respectively.

Task success remained `0.0`. The separate audit found the four expected chunks at ranks `8`, `40`,
`14`, and `15` under the declared lexical retriever, all outside `top_k=5`. These results are
bounded diagnostic evidence, not a correction to the canonical portfolio or a release claim. See
`docs/reports/2026-09-02_model_atlas_evidence_remediation_2_agent_contract_and_retrieval_audit.md`.

## Finalized Case-Pack Revision 1.0.1

Evidence Remediation 3 created an isolated `1.0.1` candidate for those four contracts. The revised
expected chunks rank `3`, `1`, `1`, and `1`, so the automated retrieval audit passes at
`top_k=5`. The Agent planner may receive the public bilingual query, but expected chunk IDs remain
evaluation-only and are never supplied to the model.

Reviewer `김대건` approved all four changes through the hash-bound attestation. Final validation
reports 64 approved cases, 20 approved critical cases, no drafts or rejections, and
`portfolio_ready=true` for the isolated revision.

The post-finalization diagnostic stored 12 actual Results across three configurations. Every
configuration achieved Agent task success, plan validity, action-sequence accuracy, final-response
rate, and runtime success of `1.0`, with zero policy violations, timeout, OOM, or generic error.
Persisted traces confirm 12 of 12 public-contract queries, 12 of 12 retrieval recalls at `1.0`, and
no use of expected evaluation steps as model input. Run IDs are
`751d8fc1-f49d-4ed0-9bd5-95fe4f74f086`,
`ccc53dc6-666f-47c1-b440-a7b5244752bd`, and
`78357187-e647-4d1f-aa65-126ea1a9b032`.

Nine raw model plans contained the complete `retrieve -> tool -> respond` sequence. The 0.5B
configuration omitted `respond` in three of four plans, and the bounded compiler inserted it. Both
1.5B configurations produced complete source sequences for all eight Results. The pass is thus an
end-to-end bounded-pipeline result, not uniform native-plan quality.

This diagnostic does not mutate the `1.0.0` files or replace the 384 stored portfolio Results. All
three authoritative Gates remain `BLOCKED`. See
`docs/reports/2026-09-03_model_atlas_evidence_remediation_3_finalization_and_diagnostic.md`.

## Finalized Refusal and Scope Diagnostic

Reviewer `김대건` approved the single `1.0.2` change through the report- and case-hash-bound
attestation. Finalization reports 64 approved cases, 20 approved critical cases, no drafts or
rejections, and `portfolio_ready=true`. The user query is unchanged and only the expected evidence
identity for `KO-RAG-SCOPE-001` differs from finalized `1.0.1`.

The final seven-case audit found all contracts reachable within `top_k=5`, with expected ranks
`1`, `2`, `1`, `2`, `2`, `1`, and `1` and retrieval recall `1.0` for every case. The following
actual-runtime diagnostic stored 21 Results across the three configurations. Every run retained
retrieval recall `1.0`, but RAG success was `0/7` for all configurations. JSON validity was `0/7`,
`1/7`, and `2/7`; both 1.5B configurations hit the 384-token diagnostic ceiling in five cases.
The v2 prompt was the strongest bounded result, with mean quality `0.356`, citation precision
`0.119`, citation recall `0.286`, groundedness `0.156`, and unsupported-claim rate `0.929`.

No timeout or OOM occurred. The failures are post-retrieval structured-output, citation, and claim
grounding failures rather than transport or retrieval failures. The current scorer also requires a
contract-aware refusal extension before `must_refuse`, required facts, and forbidden claims can be
claimed as directly evaluated semantics. The diagnostic remains isolated from Portfolio and Gate
evidence. See
`docs/reports/2026-09-04_model_atlas_evidence_remediation_4_refusal_scope_diagnostic.md`.

## RAG Contract and Refusal Scoring Diagnostic

Evidence Remediation 5 added the compact three-field RAG response contract, strict runtime JSON
schema, retrieved-ID citation enum, and `rag-evaluation-trace-v2` refusal semantics. A prompt-only
21-result iteration did not improve structured output, so a one-case schema probe was run before
the final bounded 21-result matrix.

In the final matrix, JSON validity improved from the original `3/21` to `20/21`, and 384-token
ceiling hits fell from `12/21` to `1/21`. Retrieval recall stayed `1.0` for every Result. Mean
citation precision/recall across the three configurations rose to `0.476/0.476`, while mean
groundedness rose to `0.405` and unsupported-claim rate fell to `0.786`. The medium v1
configuration was strongest: `7/7` valid JSON, `4/7` correct single citations, `3/7` semantic
contracts, `2/4` refusal requirements, mean quality `0.610`, and p95 latency `11,229.731 ms`.

RAG success nevertheless remained `0/7` for every configuration. The remaining blocker is no
longer primarily JSON transport: it is direct evidence selection, concise source-supported claim
generation, and refusal phrasing. The token-overlap semantic scorer is inspectable but not a judge
model and still requires calibration for paraphrases and compound status tokens. These runs remain
diagnostic and do not modify Portfolio or Gate evidence. See
`docs/reports/2026-09-04_model_atlas_evidence_remediation_5_rag_contract_and_refusal_scoring.md`.

## Deterministic Evidence and Refusal Diagnostic

Evidence Remediation 6 added `lexical-sentence-selector-v1`, selected-evidence provenance,
source-claim enums, and a bounded refusal answer contract. The selector uses only the public query
and retrieved top-k chunks; expected IDs, required facts, and forbidden claims remain evaluator-only.
`openai-compatible-v16`, `rag-retrieval-trace-v2`, `rag-evaluation-trace-v3`,
`rag-evaluation-summary-v3`, and `rag-evaluation-scorer-v3` identify the resulting contracts.

The final 21-result diagnostic produced valid JSON in `21/21`, groundedness `1.0` in `21/21`,
unsupported-claim rate `0.0` in `21/21`, and successful refusal semantics in `12/12`. No result hit
the 384-token ceiling; timeout and OOM counts were zero. Strict RAG success improved from `0/21` to
`11/21`.

| Configuration | Model / prompt | RAG success | Semantic | Refusal | Citation P/R | Grounded | Unsupported | Mean quality | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 0.5B / v1 | 3/7 | 4/7 | 4/4 | .571 / .571 | 1.000 | .000 | .807 | 5,275.777 |
| `medium-candidate` | 1.5B / v1 | 4/7 | 5/7 | 4/4 | .571 / .571 | 1.000 | .000 | .836 | 9,035.953 |
| `prompt-variant` | 1.5B / v2 | 4/7 | 5/7 | 4/4 | .571 / .571 | 1.000 | .000 | .836 | 9,607.522 |

Exact evidence-selection recall is `4/7` in each configuration. `KO-RAG-SCOPE-002`,
`KO-RAG-SCOPE-003`, and `KO-REFUSE-002` selected retrieved chunks that more directly state the
answer boundary but differ from the single expected ID in finalized `1.0.2`. Those three identity
mismatches account for nine strict failures; the remaining failure is the 0.5B scope answer copying
a forbidden proposition as a question. This exposes a case-contract limitation: one required ID
cannot represent multiple acceptable sources. Any `1.0.3` change should be isolated and reviewed,
and should model acceptable alternatives without weakening citation scoring.

Final evidence:

- run IDs: `30b4a30c-cff4-4eda-a557-b722fc0cd9d8`,
  `31199d00-f902-40c2-b9e5-4f9ae2cf68fe`, and
  `dbf12ff0-b12f-4a05-b48b-ba4f5981ec4f`;
- result artifact:
  `artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.2-evidence-compiler-v3.json`;
- artifact SHA-256: `89cc23531ed4a48507434c7143e57debbb8a003673371ea08eb75f72bc179823`;
- authoritative Portfolio/Gate evidence changed: no;
- production readiness: `not_production_ready`.

See
`docs/reports/2026-09-04_model_atlas_evidence_remediation_6_deterministic_evidence_and_refusal.md`.

## Finalized Acceptable Evidence Diagnostic

Evidence Remediation 7 adds `rag-evidence-contract-v2`. It preserves the reviewed
`relevant_chunk_ids` as the primary group while allowing explicitly reviewed alternatives through
`acceptable_evidence_groups`. All IDs in one group are required; satisfying any complete group is
enough. Retrieval, evidence selection, and citation evaluation use the same best-group algorithm.

The isolated `1.0.3` revision changes three critical cases only:

| Case | Primary group | Alternative group | Candidate audit |
| --- | --- | --- | --- |
| `KO-RAG-SCOPE-002` | `ko-247daa1b46cc86363d892938` | `ko-b70165b4b3f47cf87a34ff25` | reachable |
| `KO-RAG-SCOPE-003` | `ko-5177b421f19ca0909ee719f2` | `ko-9c59bd29a1b754b80c476d62` | reachable |
| `KO-REFUSE-002` | `ko-605f4586e724cc70f087851d` | `ko-8b7f33d47228772f0cbba790` | reachable |

The audit reports `3/3` reachable cases, zero blocked cases, and best-group recall `1.0`. A human
reviewer approved all three changed cases in an attestation bound to revision report identity
`d2b570fe347967de9b44f90c53276630292f11d814805aaf0ecba778a4e90401`. Finalization produced a
64/64 approved pack with all 20 critical cases approved and `portfolio_ready=true`.

The post-finalization 21-result diagnostic confirmed the projection. Citation recall and exact
evidence-selection recall improved from `.571429` to `1.0` in every configuration. Strict RAG
success improved from `11/21` to `14/21`; `KO-REFUSE-002` now passes in all three configurations
through alternative evidence group index 1. `KO-RAG-SCOPE-002` and `KO-RAG-SCOPE-003` also satisfy
selection and citation through group index 1 but still fail required-fact coverage, so the any-of
contract does not conceal their semantic-label mismatch. The 0.5B `KO-RAG-SCOPE-001` result still
violates one forbidden claim.

| Configuration | Before | After | Selection recall | Citation recall | Alternative matches |
| --- | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 3/7 | 4/7 | 1.0 | 1.0 | 3 |
| `medium-candidate` | 4/7 | 5/7 | 1.0 | 1.0 | 3 |
| `prompt-variant` | 4/7 | 5/7 | 1.0 | 1.0 | 3 |

Finalized revision artifacts are under `reference_workload/revisions/1.0.3/`. The diagnostic
artifact is
`artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.3-any-of-v2.json`
with SHA-256 `4ef70ace00c2c494e995d07fcc7a404a0f000229af1c7507c79da5eac94f1240`.
Neither this diagnostic nor case-pack eligibility updates Portfolio or Gate evidence, and
production readiness remains `not_production_ready`. See
`docs/reports/2026-09-06_model_atlas_evidence_remediation_7_finalization_and_actual_diagnostic.md`.

## Finalized Bounded Answer And Semantic Diagnostic

Evidence Remediation 8 separates answer construction from evaluator semantics. The
`rag-bounded-answer-contract-v1` compiler receives only the public query and the deterministically
selected source claim. It creates an exact scope or refusal answer before adapter execution; it
does not receive relevant IDs, required facts, forbidden claims, or a reference answer.

The finalized `1.0.3` pack was rerun across the same seven diagnostic cases and three runtime
configurations after rebuilding Docker with the new answer contract. All 21 outputs satisfied the
bounded-answer contract, and the 0.5B `KO-RAG-SCOPE-001` forbidden-claim failure disappeared.

| Configuration | Remediation 7 | Remediation 8 runtime | Bounded answers | Remaining failures |
| --- | ---: | ---: | ---: | --- |
| `small-baseline` | 4/7 | 5/7 | 7/7 | Scope 002, Scope 003 |
| `medium-candidate` | 5/7 | 5/7 | 7/7 | Scope 002, Scope 003 |
| `prompt-variant` | 5/7 | 5/7 | 7/7 | Scope 002, Scope 003 |

Across the matrix, retrieval, deterministic evidence selection, and citation contracts were
`21/21`; refusals were `12/12`; groundedness was `1.0`; unsupported-claim rate was `0.0`; and no
timeout or OOM occurred. The exact run IDs are
`5a581802-eea1-4e94-aacc-970267b0cb84`,
`2aaa0e8a-0263-4d98-8cdd-600e063b2e5b`, and
`fc6c16b2-4752-4479-b1ef-7a85bfd366d8`.

The result artifact is
`artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.3-bounded-answer-v1.json`
with SHA-256 `eda3beec3dd49bffbd5214b732640c17cecb8d73f8dc12495ae3ba191c56769b`.

The isolated `1.0.4` revision adds `rag-semantic-contract-v2` alternatives only for Scope 002 and
Scope 003. Reviewer `김대건` approved both changes through a v2 attestation bound to revision report
identity `6dfc5274162cd5b434e565d6b6683b6b146457c06a9788cff27906235547aec6` and each revised case
hash. Finalization produced 64/64 approved cases, all 20 critical cases approved,
`portfolio_ready=true`, and `bootstrap_allowed=true`.

The post-finalization 1.0.4 diagnostic converted the projection into actual local-runtime evidence:

| Configuration | 1.0.3 answer-contract run | Finalized 1.0.4 | Alternative semantic matches |
| --- | ---: | ---: | ---: |
| `small-baseline` | 5/7 | 7/7 | 2 |
| `medium-candidate` | 5/7 | 7/7 | 2 |
| `prompt-variant` | 5/7 | 7/7 | 2 |

All 21 cases passed semantic, bounded-answer, retrieval, deterministic selection, citation, and
grounding checks. Refusal success was `12/12`, average groundedness was `1.0`, unsupported-claim
rate was `0.0`, and there were no forbidden violations, timeouts, or OOMs. Scope 002 and Scope 003
used semantic group index 1 and citation group index 1 in all three configurations.

The exact run IDs are `69973089-6e68-4fea-bfc6-ea79b341f6bd`,
`0ecdbbe9-6e82-44dd-ac5c-aa5e97e66406`, and
`f48df4b4-2e69-4821-9b0d-426ae55a1641`. The result artifact is
`artifacts/reference-workload/runtime-matrix-diagnostic-refusal-scope-v1.0.4-semantic-v2.json`
with SHA-256 `054b5163ccbdf0f2da934b3bb9c0cdd1caa82b72a4020c8d32d2d3e6c46a7182`.

The diagnostic remains non-authoritative and cannot update Portfolio or Gate evidence. Passing
seven bounded contract cases does not establish broad model quality or production readiness.
Production readiness remains `not_production_ready`. See
`docs/reports/2026-09-07_model_atlas_evidence_remediation_8_finalization_and_actual_diagnostic.md`.

### Opt-in Tool selection diagnostic

Remediation 10 compares v18 and experimental v19 on the same explicitly selected finalized `1.0.4`
pack. Selection and normalized execution increased from `41/48` to `43/48`, but two new
`KO-RECOVERY-004` failures appeared in the 1.5B configurations. Final adapter v20 therefore retains
the legacy default and exposes `runtime_config_json.tool_selection_prompt` as an explicit opt-in
for `public-tool-selection-prompt-v1` in separately identified candidate configurations.

The default runtime matrix does not enable it. A database-free runner additionally checks 24 local,
unreviewed requests across three configurations: baseline selection `46/72`, enabled candidate
`56/72`, and candidate with reversed catalog order `65/72`. Order sensitivity and raw-argument
regressions prevent treating the best total as release evidence. No Portfolio, Gate, source case,
or source approval is changed. See `docs/tool_selection_diagnostics.md` and
`docs/reports/2026-09-07_model_atlas_evidence_remediation_10_tool_selection.md`.

### Tool argument and recovery diagnostic

Evidence Remediation 9 added `bounded-tool-call-contract-v1` to adapter
`openai-compatible-v18`. It preserves the model-selected Tool and raw output, then normalizes only
that Tool's arguments from the public request and public `available_tools` descriptor. The audit
record explicitly states `uses_expected_tool_contract=false`.

The before and after diagnostics used the same 16 single-step and recovery cases once across all
three configurations:

| Configuration | Before success | After success | Before argument validity | After argument validity | After recovered |
| --- | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | 4/16 | 10/16 | 4/16 | 11/16 | 3/6 |
| `medium-candidate` | 5/16 | 15/16 | 5/16 | 15/16 | 6/6 |
| `prompt-variant` | 5/16 | 16/16 | 5/16 | 16/16 | 6/6 |

Tool selection stayed `41/48` before and after; the contract did not repair selection errors.
Execution success improved from `14/48` to `41/48`, argument validity from `14/48` to `42/48`,
and recovery coverage from 8 to 15 recovered calls. Every call that actually retried recovered.

The baseline artifact is
`artifacts/reference-workload/runtime-matrix-diagnostic-tool-contract-pre-v18.json` with SHA-256
`05d5a0be20314fd59df0b9afe1628ede6117a3562beb287c11fc655baf6a9869`. Its run IDs are
`04141170-1364-40ee-98fc-a5c9dd9f19bc`, `69b26219-409d-4a87-a5d1-2ad4330c0123`, and
`eeb1649c-37b9-4697-ae7f-3a25b328498a`.

The final artifact is `artifacts/reference-workload/runtime-matrix-diagnostic-tool-contract-v18.json`
with SHA-256 `539d91fbea9a462d7da6e882e6fe1df2caf4573ef2a69059f24819f3820f835c`. Its run IDs are
`6a2480df-505c-4355-8652-47d793c8ee40`, `55b3b0ad-228c-4ed0-acea-4f8f9f33e501`, and
`4475f1b5-a0f6-46fc-b834-608345b9f84f`.

These runs are non-authoritative diagnostics and do not replace the 384-result Portfolio or its
three blocked Gates. See
`docs/reports/2026-09-07_model_atlas_evidence_remediation_9_tool_contract_diagnostic.md`.

Phase 7 reran the ten-case smoke path against `qwen2.5:0.5b`. The post-isolation run ID is
`1122950f-e1a5-4f33-9acd-1d62231427f1`, its dedicated Deployment Configuration ID is
`abbfa944-512a-43d6-bf4b-936f879c3faa`, and its artifact is
`artifacts/reference-workload/runtime-matrix-smoke-phase7-isolated.json` with SHA-256
`f7e21326bf1d26aaafe99bd57d76a4c184a43857d92b849a771f44a7a7d63c3c`. It stored ten Results and
ten Metrics, with success rate `0.1`, error rate `0.9`, nine critical failure outcomes, no timeout,
and no OOM. After the run, the aggregate still selected the exact three 128-result portfolio runs
and Gate orchestration reused all three current reference Gates.

## Verified Portfolio Evidence

The final v7 Portfolio matrix completed on 2026-09-01 with three configurations, 384 stored
Results, 384 stored Inference Metrics, 64 distinct approved cases per configuration, exactly two
trials per case, and two distinct observed model artifacts. No entry was failed or unavailable.

| Configuration | Model / prompt | Mean quality | JSON valid | Tool select | Tool args | Tool exec | RAG grounded | Unsupported | Critical fail | P95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | `qwen2.5:0.5b` / v1 | 0.224609 | 0.307692 | 0.6250 | 0.28125 | 0.25000 | 0.000000 | 1.000000 | 0.95 | 6,404.735 |
| `medium-candidate` | `qwen2.5:1.5b` / v1 | 0.307664 | 0.394231 | 0.9375 | 0.37500 | 0.37500 | 0.082589 | 0.909722 | 0.90 | 12,448.586 |
| `prompt-variant` | `qwen2.5:1.5b` / v2 | 0.301977 | 0.403846 | 1.0000 | 0.34375 | 0.34375 | 0.066369 | 0.944444 | 0.90 | 12,477.137 |

Retrieval recall was `0.638889` for every configuration because the same locked corpus and
retriever were used. The 1.5B v1 candidate produced the best overall quality, Tool argument and
execution rates, and RAG groundedness. The v2 prompt improved JSON validity, Tool selection, and
Tool sequence success, but regressed overall quality, Tool argument/execution rates, and RAG
groundedness relative to the same model with v1. Both 1.5B configurations roughly doubled P95
latency relative to the 0.5B baseline.

All configurations had zero timeout and zero OOM rates, but their strict evaluation success rates
were only `0.0625`, `0.0938`, and `0.0859`. All had Agent task success `0.0`, RAG success `0`, and
critical-case failure of at least `0.90`. The runtime matrix is complete evidence of an honestly
poor model-quality outcome; it is not a passing quality Gate.

Evidence identity:

- run IDs: `2124b9f7-82f2-483f-939b-83a18400b9ab`,
  `698428e8-59ec-4353-8f7d-ea592e60a206`, and
  `9da6d961-1e8a-460d-848e-b5c29ff2b59f`;
- matrix SHA-256: `cfcf986f8e3a884a385a9873e370ccbe6f544b9628b15036db067033504845aa`;
- comparison SHA-256: `0c92a7b4793c2dd69d02a03a88e68ab19a233512dc50e1bc57ac7c6dcf716cd9`;
- result-file SHA-256: `d6e717325c0202850630ba9c04ad929e13e010f1ea2335eb3b4bca7685aa3867`;
- output: `artifacts/reference-workload/runtime-matrix-portfolio-v7.json`;
- portfolio execution status: `ready`;
- production readiness: `not_production_ready`.

Running `compare-runtime` again rebuilt the comparison from the exact persisted run IDs and
retained the same comparison hash. This verifies stored-evidence reproducibility; it does not make
the quality result acceptable.
