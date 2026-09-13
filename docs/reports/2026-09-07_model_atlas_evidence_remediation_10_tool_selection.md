# Model Atlas Evidence Remediation 10: Tool Selection

Date: 2026-09-07  
Decision: retain legacy defaults; keep the new selector as an opt-in experimental candidate.  
Authority: non-authoritative local diagnostics, not Portfolio or Gate approval.

## Finding

The new public Tool prompt improves aggregate selection but introduces individual regressions and
remains sensitive to catalog order. It is not a replacement for a fully validated deployment
candidate. No new model was trained, no model-selected Tool was corrected using an expected label,
and no failure was relabeled as a pass.

## Same-Pack Comparison

Both runs below explicitly use finalized case pack `1.0.4`, the same suite, corpus, model digests,
matrix, seed 42, temperature 0, 384-token limit, and one trial per case. The preceding Remediation 9
Tool diagnostics had used canonical `1.0.0`; they are historical context, not the paired baseline
for this report. The 16 Tool/recovery cases were rerun before and after this change.

Suite: `e51668dd-b098-42f5-8787-c2f2de2184ec`  
Suite hash: `fc516df11334ab07835da41532dcedf549b7620901b34374eed53e45e80d031e`  
Corpus hash: `2772ab9a898529c052337ad6d06e4f0950333a316d72d79778dbc6cfe8cf0642`

| Configuration | v18 selection / execution | v19 experimental selection / execution |
| --- | ---: | ---: |
| small-baseline | 10/16 | 13/16 |
| medium-candidate | 15/16 | 15/16 |
| prompt-variant | 16/16 | 15/16 |
| Total | 41/48 | 43/48 |

The experimental run fixed four previously failing selections and introduced two new failures.
Both new failures are `KO-RECOVERY-004` in the 1.5B configurations: customer lookup was replaced by
internal-document lookup. These are standard-criticality cases, but they still prevent claiming
regression-free improvement. The small model still fails `KO-TOOL-002`, `KO-TOOL-008`, and
`KO-RECOVERY-006`; `KO-TOOL-002` remains critical. Recovery successes total 15 in both snapshots,
with a different distribution across configurations.

| Configuration | Baseline run | Experimental run |
| --- | --- | --- |
| small-baseline | cf04fbbc-a963-4951-9295-93a464cce30f | ad3a1c77-bd47-4706-a787-3f8d4fe35ebe |
| medium-candidate | 974e11de-1d68-4708-967c-dfde5a378d2d | b2f4b4dc-79eb-4969-b314-e833db830d82 |
| prompt-variant | fedef8cd-2ee4-4b56-8b41-b5fb84e904d6 | f10e0dab-215c-4208-9738-d146a5fb0648 |

The v19 snapshots automatically enabled the experimental prompt for eligible cases during this
diagnostic. Final adapter v20 preserves the same prompt contract behind explicit configuration;
default executions use the legacy prompt. Therefore the default system must not be described as
having reduced its remaining seven Tool selection errors to five.

## Additional Requests

The challenge was authored before its candidate execution. It contains 24 new requests: eight
Korean paraphrases, six English requests, six negation/contrast requests, and four recovery requests.
Its labels were authored locally and have not received independent or human review.

| Configuration | v18 prompt replay | Experimental contract, registered order |
| --- | ---: | ---: |
| small-baseline | 12/24 | 12/24 |
| medium-candidate | 18/24 | 22/24 |
| prompt-variant | 16/24 | 22/24 |
| Total | 46/72 | 56/72 |

These are selection counts, also matched by normalized fixture execution counts. Raw and normalized
selection agree; the argument compiler does not change the selected Tool. Raw argument validity
decreased from 54/72 to 50/72, while normalized argument validity increased from 67/72 to 72/72.
This tradeoff is another reason not to call the aggregate result an unconditional model improvement.
In particular, a schema-valid `document_id` is not proof of a real, correctly resolved document.

The 1.5B configurations' negation/contrast selections improved from 4/6 and 2/6 to 6/6 and 5/6.
The 0.5B configuration remained at 1/6. Generalization is still limited, especially for the smallest
model. None of these small samples supports a production accuracy guarantee.

Final adapter v20, with the option explicitly enabled, reproduced the registered-order selection
counts of 12/24, 22/24, and 22/24. Reversing only the catalog order with the same final implementation
produced 18/24, 24/24, and 23/24, or 65/72 in total. The catalog order is therefore a material
sensitivity, not an accepted accuracy optimization. Both orders are retained; neither is promoted
to a default. Individual generated arguments varied across runs despite the fixed seed and
temperature, so exact output determinism is not claimed.

## Implementation And Controls

- Added `backend/app/services/tool_selection_prompt.py` with a pure public-input projection,
  dynamic Tool-name enum, exact-match Korean description labels, and audit records.
- Preserved configured system prompts, public instructions, raw output, all candidate Tool names,
  and the existing argument compiler. No request keywords map directly to a selected Tool.
- Kept custom descriptions unchanged and retained legacy handling for unsupported schemas and
  non-standalone execution paths.
- Added opt-in configuration in adapter v20. Missing configuration or `legacy` preserves default
  behavior; invalid setting values fail explicitly.
- Added an extensible challenge fixture and a database-free diagnostic runner with model digests,
  source hashes, separate raw/normalized metrics, repeat trials, and catalog-order controls.
- Added tests for secret-label invariance, new Tools, custom descriptions, order preservation,
  schema fallback, path isolation, preserved instructions, and opt-in/default behavior.

Early alternatives were rejected: public-input shortening and compact English argument catalogs
each selected only 7/16 on the 0.5B tuning subset; selection-only variants also failed to remove the
document/customer ambiguity. These were exploratory tuning runs, not additional independent tests.

## Evidence Files

All result paths below are under `artifacts/reference-workload/`.

| File | SHA-256 |
| --- | --- |
| runtime-matrix-diagnostic-tool-selection-v1.0.4-v18.json | 4aac9352f1957143b27a5e112bbcd567294aea292eb0c1a9585b169050be6db7 |
| runtime-matrix-diagnostic-tool-selection-v1.0.4-v19.json | 719533dbceba6963891dc822e033d493ee344a116cc6589ebfd37f7be69b5234 |
| tool-selection-challenge-v18.json | ec3af94f39efd6b71a3f9fd69b53f6850883ff142f8fcee55560991d17c77cbd |
| tool-selection-challenge-v19.json | 849263d8dd0447e7a0503d50eca574cd5055977bf5af1dfc50f6729cc17d164e |
| tool-selection-challenge-v20.json | cb3a7e6a6ee873d969ce096a25072461f87cd102667305d1b4369ffecc5b4d24 |
| tool-selection-challenge-v20-reversed.json | e80e6be33cabaf3f9e8c0decf5a763fedaa5aa59a0cdfd02c5f0ed695f724c10 |

Challenge fixture SHA-256: `a45e110c8d0bf41694f6acb7c5681ec407f74aa57aeee5773bef5492129846ff`.

## Verification

- Final host backend suite: 282 passed, 1 skipped. The existing Starlette/httpx deprecation warning
  remains; this change does not alter dependencies.
- Final Docker backend suite: 283 passed, with dependency deprecation warnings only.
- Ruff checks: application, tests, and the diagnostic runner passed.
- Docker backend and Agent worker rebuilt and recreated; backend, database, and Ollama healthy.
- Alembic remains at head `202608040001`; no schema migration was introduced.
- Finalized `1.0.4` validation remains ready: 64/64 approved cases and 20/20 critical cases.
- Both 48-result matrix diagnostics completed all three entries; 288 challenge calls completed
  without uncaught inference errors. Selection/execution failures remain counted above. This
  excludes exploratory tuning calls and does not represent 384 independent test cases.

The diagnostic script is database-free. Registry fixture handlers have no external side effects.
All scored Tool executions remain local fixtures, not production-captured Tool traffic.

## Next Decision

Proceed to the planned evidence-trust and argument-boundary review, including semantic argument
validity, failure-injection intent, raw-versus-normalized scoring, and catalog-order sensitivity.
Do not enable the new prompt globally based on a better total or a better catalog ordering.
After choosing an explicitly versioned candidate, run the complete workload and collect actual
output reviews before reevaluating Gates.

The 64 approved source cases remain intact. Official Portfolio evidence remains 384 Results,
the current overview remains BLOCKED with 110 critical failures, actual-output reviews remain
0/30, and production readiness remains `not_production_ready`.

Usage and reproduction: `../tool_selection_diagnostics.md`.
