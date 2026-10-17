# Field Provenance V5

One user-requested iteration preserves the frozen V4 evidence and adds bounded
public evidence for timezone, priority and ID-based todo completion. Literal
titles are data. Field modes are specified, omitted, public-default or ambiguous;
specified values retain request offsets. Within recognized creation contexts,
conflict or unknown values constrain the decoder to clarification.
Completion binds a complete literal ID command to the public task's status.
Raw model output is never repaired, rewritten or retried. This is a hybrid public
parser/decoder/LLM pipeline, not a newly trained or inherently safe model.

All prior 88 scenarios and 20 fresh scenarios are frozen before inference.
V4/V5 with two seeds require 432 actual calls. The clock remains identical to
the preceding V4 comparison for attribution. All strict/grounded drafts, exact
positive intents, specified conservative decisions, workflows and unchanged
preapproval state/sentinel must pass. Positive accuracy must strictly improve
without per-case regression. A pass remains pending integration, not deployment.
There is one candidate and one frozen run; no tuning follows holdout observation.

```powershell
.venv/Scripts/python.exe -m experiments.personal_assistant_field_grounding.run --output artifacts/personal-assistant-field-grounding/2026-10-15/comparison-v1
.venv/Scripts/python.exe -m experiments.personal_assistant_field_grounding.verify --source artifacts/personal-assistant-field-grounding/2026-10-15/comparison-v1 --output artifacts/personal-assistant-field-grounding/2026-10-15/replay-v1
```

Editable backend installation is required. Protocol tests and replay make zero
model calls. Outputs must be fresh. User edits/confirmation remain separate from
the original request's model-field evidence and do not authorize automatic action.

## Completed Result

The frozen 2026-10-15 run completed all 432 calls. The gate is
`BLOCKED_KEEP_LEGACY`; the default remains `legacy`, not V5.

| Combined metric | V4 | V5 |
| --- | ---: | ---: |
| Exact positive intents | 100/116 | 106/116 |
| Specified conservative decisions | 78/86 | 84/86 |
| Strict contract and field evidence | 216/216 | 210/216 |
| Independent workflows | 194/216 | 204/216 |
| Unchanged preapproval state / sentinel | 216/216 | 216/216 |

V5 fixes H03's invented priority and R16's completion-role error. It still drops
requested deadlines (D03, E01, E02). E02 is a new paired regression in both seeds.
Multi-quoted title/slot requests retain outer title quotes (E05, E07). The new
validator also misclassifies calendar wording (D08, D20) and a legitimate mention
of conflicting instructions (E09), producing six evidence errors, not runtime or
output-length failures. Correct-source constraints do not prove field completeness.

Zero-model replay passed all 432 rows, verifying 33 frozen/current source files,
actual transports, source spans, raw outputs, independent effects and summary.
No candidate browser integration or promotion followed the failed gate. No
post-holdout tuning was performed. See the [Korean report](../../docs/reports/2026-10-15_personal_assistant_field_provenance_ko.md)
for split results, hashes, tests and limitations.
