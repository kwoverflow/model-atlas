# Decision And Explanation Grounding V7

One user-requested iteration compares frozen V6 with V7 on all 128 previously
observed scenarios plus 20 fresh contrasts, with two seeds: 592 scored attempts.
The clock stays at `2026-10-15T09:00:00+09:00` for attribution. The same cached
qwen3.5:9b Q4_K_M, Ollama 0.31.1, native decoding, context 8192, max tokens 768,
temperature 0 and non-thinking setup are retained. If unloaded, one explicit
model-only load request is recorded separately before freezing, not scored as an
answer. No prompt probes, retries, output repairs or post-holdout tuning follow.

The new layer binds supported public request roles, field evidence and public
state to the decision and source-based explanation in the actual decoder. It
does not rewrite model output, reveal private goals or authorize execution.
Complete covered creation frames, exact completion IDs, established literal file
policy and complete explanation-only document frames have bounded certificates.
Conditional/unsupported input is explicitly insufficient. Unresolved fallback
outputs have no claimed explanation guarantee. This is a hybrid parser/decoder/
LLM result, not model training or evidence that the LLM independently reasons better.

Independent `GOLD` labels are authored separately from candidate functions. The
fresh 20 cases specify decision, sufficiency, reason code, exact clarification
fields and explanation facts, including 18 grounded cases and two intentionally
insufficient conditional cases. Schema agreement alone cannot pass this check.
Model-free tests also move priority words between title and instruction, change
public task state, add conditions/withdrawal/compound clauses and reject invented
explanation claims. Gold goals and labels never enter the target model's input.

Require all exact positive intents, specified conservative decisions, independent
flows, strict outputs, safety states and all 40 fresh label checks. Require positive
gain over V6, no paired regression and no runtime error in either arm. Passing is
pending replay, full tests and browser integration, never autonomous release or
an automatic default switch. One candidate and one frozen run are allowed.

```powershell
.venv/Scripts/python.exe -m experiments.personal_assistant_decision_grounding.run --output artifacts/personal-assistant-decision-grounding/2026-10-16/comparison-v1
.venv/Scripts/python.exe -m experiments.personal_assistant_decision_grounding.verify --source artifacts/personal-assistant-decision-grounding/2026-10-16/comparison-v1 --output artifacts/personal-assistant-decision-grounding/2026-10-16/replay-v1
```

Outputs must be fresh. Protocol tests/replay make zero model calls. The authored
confirmation oracle in sandbox effects does not protect a real user's blind
approval of incorrect fields. Request grammar coverage and correctness must be
reported separately from decoder consistency and application execution guards.

## Completed Results

All 592 scored requests returned; there was one separately recorded model-only
load request, zero retries or prompt probes. The frozen gate is
`PASS_PENDING_INTEGRATION`, with no paired regressions or runtime errors.

| Combined metric | V6 | V7 |
| --- | ---: | ---: |
| Exact positive intents | 154/158 | 158/158 |
| Specified conservative decisions | 116/124 | 124/124 |
| Strict contract/evidence | 296/296 | 296/296 |
| Independent workflows | 292/296 | 296/296 |
| Unchanged preapproval state / sentinel | 296/296 | 296/296 |
| Fresh separate label checks | Not applicable | 40/40 |

V7 fixes C07/C19 and the known default-timezone/optional-deadline explanation
issues. Of 296 candidate outputs, 224 have grounded certificates, four have
explicitly insufficient condition explanations, and 68 retain unbound fallback
explanations. The label checks do not certify every explanation or natural-language
interpretation, and both labels and implementation have local authorship.

Zero-model replay passed 592 outputs, checking 592 actual transports and 41
archived/current sources, public input/proof hashes, source spans and effects.

**Do not promote the candidate.** A separate post-freeze, zero-model exploratory
audit found three counterexamples in four explanation contrasts: quoted
prohibition, conditional creation, and file moves with `할일추가` inside filenames.
The outer no-execution decision is correct, but the certificate incorrectly
labels the inner summary as grounded. Decoder consistency cannot establish the
truth of its own evidence. These are preserved separately, not added retroactively
to the frozen score, and no candidate tuning follows them. The default remains
`legacy`; browser activation/integration and autonomous release were not approved.

```powershell
.venv/Scripts/python.exe -m tools.audit_personal_assistant_decision_semantics --output artifacts/personal-assistant-decision-grounding/2026-10-16/explanation-challenges-v1.json
```

See the [Korean assessment](../../docs/reports/2026-10-16_personal_assistant_decision_consistency_ko.md)
for split results, scope, source hashes, replay, tests and the distinction between
decision grounding and document-content explanation grounding.
