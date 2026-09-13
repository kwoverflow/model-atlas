# Model Atlas Evidence Remediation 3: Finalization and Diagnostic

Date: 2026-09-03 JST  
Finalized revision: `1.0.1`  
Source workload: `1.0.0`  
Decision: `DIAGNOSTIC_PASS`  
Production readiness: `not_production_ready`

## Outcome

The human-reviewed case-pack revision `1.0.1` was finalized without modifying the canonical
`1.0.0` files or historical runtime evidence. Reviewer `김대건` approved all four changed critical
cases. Final validation reports:

- 64 of 64 cases approved;
- 20 of 20 critical cases approved;
- zero draft and zero rejected cases;
- all category and critical-category minimums satisfied;
- `portfolio_ready=true` for the isolated revision;
- bootstrap allowed for revision-scoped diagnostic execution only.

The finalization report logical SHA-256 is
`f6c296a67b167c3726e3bc3c8d72a8c423e172d317b3fa6f8d5d464568dc780b`.

## Retrieval Verification

The final revision-scoped retrieval audit passed all four contracts:

| Case | Expected rank | Recall | Reachable |
| --- | ---: | ---: | --- |
| `KO-RAG-TOOL-001` | 3 | 1.0 | yes |
| `KO-RAG-TOOL-002` | 1 | 1.0 | yes |
| `KO-RAG-TOOL-003` | 1 | 1.0 | yes |
| `KO-AGENT-001` | 1 | 1.0 | yes |

Audit summary: four reachable, zero blocked, zero critical blocked. Its logical report SHA-256
remains `5863b810e43d273d36eebb8f9de610e65cd32df112cccc8d5d84f8652273d7fc`.

## Actual Runtime Diagnostic

The finalized pack ran the four P0 cases once against each of the three configured runtimes. All
three entries completed, storing 12 actual Results and 12 Inference Metrics across two observed
Ollama artifacts.

| Configuration | Model / prompt | Run ID | Agent success | Plan valid | Sequence | Policy violation | P95 ms |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `small-baseline` | `qwen2.5:0.5b` / v1 | `751d8fc1-f49d-4ed0-9bd5-95fe4f74f086` | 1.0 | 1.0 | 1.0 | 0.0 | 3,324.775 |
| `medium-candidate` | `qwen2.5:1.5b` / v1 | `ccc53dc6-666f-47c1-b440-a7b5244752bd` | 1.0 | 1.0 | 1.0 | 0.0 | 6,916.772 |
| `prompt-variant` | `qwen2.5:1.5b` / v2 | `78357187-e647-4d1f-aa65-126ea1a9b032` | 1.0 | 1.0 | 1.0 | 0.0 | 3,667.788 |

All configurations also achieved step success `1.0`, final-response rate `1.0`, observation
coverage `1.0`, runtime reliability success `1.0`, zero timeout, zero OOM, and zero generic error.
The previous final P0 diagnostic had task success `0.0` for every configuration. This rerun isolates
the improvement to the reviewed retrieval contracts plus the public-query compiler path.

Persisted-result inspection confirmed all 12 Results:

- used `retrieval_query_source=public_contract`;
- recorded `uses_expected_steps=false`;
- retrieved the expected chunk with recall `1.0`;
- completed the Agent task successfully;
- recorded zero policy violations.

Nine of 12 raw model plans already contained the complete `retrieve -> tool -> respond` sequence.
The three incomplete plans all came from the 0.5B configuration and contained `retrieve -> tool`;
the bounded compiler inserted the final `respond` action. Both 1.5B configurations produced the
complete three-action sequence for all eight Results. The `1.0` task-success result is therefore a
compiler-assisted pipeline result, not a claim that every raw model plan was independently
complete.

Expected chunk IDs remain evaluation metadata. They were not exposed to the model planner. The
RAG summary is not populated separately for these four cases because they execute through the
multi-step Agent evaluator; retrieval recall is recorded inside each Agent retrieval step.

## Evidence Boundary

The diagnostic data source is `local_actual_runtime_diagnostic`. Its matrix artifact explicitly
sets `authoritative_portfolio_evidence=false` and `gate_evidence=false`. It therefore demonstrates
that the blocker was resolved, but it does not replace the 384-result portfolio, approve a Gate,
or establish release readiness.

After the run, the live canonical overview still reports:

- workload version `1.0.0` and its original evaluation suite;
- 384 selected actual Results;
- 110 critical failures;
- zero of 30 model outputs human-reviewed;
- three of three Gate outcomes `BLOCKED`;
- eight failed blocker rules per configuration;
- production readiness `not_production_ready`.

Canonical file hashes remain identical to their pre-revision identities:

- `manifest.json`: `b5f4ea5c0e23cf14830c77414de6732307eb47153f3f82eab692149082893d98`;
- `cases.jsonl`: `81f95d1b7bb7b82f3b44bf0dc75725e7ffae2ab726ab75c83a579ae34e2ad015`;
- `review_manifest.jsonl`: `88f195d11e193255d17bc909df28d3e78966b44eb6bac4c746ebda4fb219481d`.

## Artifact Identity

- human attestation file SHA-256:
  `4c9e2b8ea0c7228e191fc877dc7a981dea8514a184e89086e4cfe54afbad5eb6`;
- finalization report file SHA-256:
  `1baf4cdcb4cccf3e90918f91192cc45f4fc0f5be8a7c01d773878d4199db1b6a`;
- finalized review manifest SHA-256:
  `48557273182f00b41a1169cdf5f560156fa4c784aa1b980f30d287ce54618141`;
- final retrieval audit file SHA-256:
  `09cac42b3ae5878aec9a06b386671d2c145367a0340e9799095d1157b93d8535`;
- final diagnostic matrix file SHA-256:
  `fb05fb9b00fbd9cae43df250ebcb0e30d6b53aac5aeed020ca6835677089f6f1`.

## Next Remediation Unit

The unreachable-contract blocker is closed. The next bounded diagnostic should address refusal and
version/scope behavior, followed by RAG citation grounding and Tool argument/recovery clusters.
The small-model path should also retain an explicit raw-plan completeness metric so compiler
recovery is not mistaken for native planning quality.
Only after those clusters improve should Model Atlas create a new full portfolio matrix and new
Gate evaluations. The outstanding 30-output human review requirement and production-captured
evidence boundary remain independent release blockers.
