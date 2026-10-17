# V8 Split Semantic Evidence

This candidate addresses the V7 audit counterexamples without modifying V7 or its
historical results. It is a bounded parser/policy/native decoder/LLM system, not
model training or a claim of general language understanding.

## Contract

`compact-semantic-grounded-v8` keeps the existing decisions and intent constraints.
Only the explanation-only document branch gets a new content explanation.
The three evidence dimensions deliberately do not share an overall `grounded` flag:

| Dimension | Status | Meaning |
| --- | --- | --- |
| `action_evidence` | `grounded` / `insufficient` | Supported outer request role, fields and public state |
| `content_evidence` | `verified` / `unverified` / `not_applicable` | Meaning established only inside the declared clause grammar |
| `explanation_evidence` | `bound` / `unverified` | Actual decoding binds the explanation, or it remains unverified |

`bound` does not mean that all content semantics were verified. The explanation
scope distinguishes `document_semantics`, `quotation_and_action_only`, and
`decision_only`. Every certificate has `authorizes_execution=false`.

For the existing full explanation-only frame, the inner grammar supports a single
Korean todo-add or file-move clause, requested/prohibited polarity, and the optional
literal condition `승인되면`. It does not infer that approval has occurred. Quoted
titles/paths are shielded before interpreting control words; argument, verb and
condition spans refer to the original user request. File meaning is distinct from
execution permission or path safety.

Only complete matches of at most 240 characters receive content claims. Other
content is explicitly unverified, quoted verbatim up to that limit, and retained
in full as source evidence. Longer quotations are omitted from the short reason
with an explicit limitation. Multiline quoted content, mixed outer frames and general paraphrases
are not certified by this bounded grammar. Unsupported content is not counted as
successful semantic interpretation.

## Frozen Comparison

- 148 prior scenarios, two seeds: 296 new V8 regression requests.
- 16 predeclared local contrasts, two seeds and V7/V8: 64 new requests.
- The 296 prior V7 observations are reused only after verifying protocol, raw
  observations and archived/current source hashes. They are not new model calls.
- Total: 360 new scored calls, 656 scored observations; no retries or raw repairs.
- The 12 supported contrasts produce 24 interpretation trials. Four out-of-scope
  contrasts produce 8 abstention trials, scored separately.
- Prompt, model, clock, native context/options and private-label isolation remain
  unchanged. Gold labels use no candidate functions, but share the same local
  author. This is not external or independent human validation.
- One scored run; no candidate changes after inspecting model outputs.
- Passing is `PASS_PENDING_INTEGRATION`, not default activation or autonomous use.

The first preparation attempt (`comparison-v1`) stopped before any scored request
because the sandbox parent directory was missing. Its frozen protocol and failure
record are preserved. Only that harness setup was corrected; the scored run is
`comparison-v2`. There was no target-model prompt tuning between attempts.

## Recorded Results

The scored run is `artifacts/personal-assistant-semantic-grounding/2026-10-16/comparison-v2`.
Its frozen gate is **PASS_PENDING_INTEGRATION**, not a release approval.

- V8 regression: exact positive intents **158/158**, specified conservative decisions
  **124/124**, independent workflows and strict contracts **296/296**. No paired regressions.
- V8 fresh: supported meaning **24/24**, explicit unsupported abstentions **8/8**,
  split evidence labels **32/32**, independent workflows **32/32**.
- V7 fresh: outer no-change decisions **32/32**, but **0/32** meet the new complete
  explanation-fact/abstention contract. This is a targeted contrast set, not a general
  explanation-accuracy estimate; absent V7 split metadata is not scored as zero accuracy.
- Both arms: no runtime errors or preapproval/sentinel changes. The scored run needed
  zero additional model-load requests. No prompt-probe calls, retries or output repairs.
- Supplementary model-free boundary audit: **12/12**, including the original V7 cases;
  six supported meanings and six abstentions. Not added to the fresh model score.
- V8 still has **68 unverified fallback explanations** in its regression observations.
  Bound explanations, content interpretation and safe abstention are separate measures.
- Zero-model replay: **656/656**, archived/current sources **50/50** verified.
- Local automated checks: backend **1,252 passed, 2 skipped**; personal assistant
  experiments **235 passed**; tools **24 passed**; Ruff and whitespace checks passed.

The candidate remains opt-in, with `legacy` unchanged. Browser integration and
default adoption are not performed by this experiment.

See the [Korean implementation and results report](../../docs/reports/2026-10-16_personal_assistant_semantic_evidence_ko.md).

## Reproduce

From the repository root, use the existing Python environment and isolated owned
Ollama endpoint `127.0.0.1:11435`. Do not reuse an output directory.

```powershell
$env:PYTHONPATH = "backend;."
.venv/Scripts/python.exe -m pytest experiments/personal_assistant_semantic_grounding -q -p no:cacheprovider
.venv/Scripts/python.exe -m experiments.personal_assistant_semantic_grounding.run --output artifacts/personal-assistant-semantic-grounding/reproduction/comparison
.venv/Scripts/python.exe -m experiments.personal_assistant_semantic_grounding.verify --source artifacts/personal-assistant-semantic-grounding/reproduction/comparison --output artifacts/personal-assistant-semantic-grounding/reproduction/replay
.venv/Scripts/python.exe -m tools.audit_personal_assistant_semantic_boundaries --output artifacts/personal-assistant-semantic-grounding/reproduction/audit.json
```

The final command is a post-freeze, model-free supplementary audit, not another
holdout or model score. Replay checks raw output, actual native decoding schema,
public payload, split evidence/source spans, provenance and independent effects.

The default remains `legacy`. No browser activation, live-user verification or
independent human attestation is implied by this experiment.
