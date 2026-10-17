# Literal Role Grounding V4

The frozen 2026-10-15 run completed 352 actual calls and 352 model-free replays.
V4 fixed the original F18/G13 creation failures and all eight fresh quoted-title
creation scenarios. Positive accuracy improved from 72/94 to 88/94, specified
conservative decisions passed 68/68, and no per-case regression was observed.
Timezone invention, omitted-priority invention and completion refusal remain
(D03/H03/R16, both seeds). The gate is `BLOCKED_KEEP_LEGACY`. No candidate browser
activation or default change was performed. The detailed
[Korean report](../../docs/reports/2026-10-15_personal_assistant_role_grounding_ko.md)
separates model errors from code/test successes and documents scope limits.

This user-requested iteration preserves V3 and its failed evidence. It adds one
bounded candidate for explicit quoted todo creation with no optional fields.
An anchored complete command binds `todo.create`, the exact literal title and
the decision based on the public open-task list. The title contents are data,
not filesystem targets or additional instructions. Uncertain, withdrawn,
compound, document-quoted or option-bearing requests retain V3 behavior.

The original compact prompt, model, strict executor and approvals are unchanged.
This is a public-parser/decoder/LLM pipeline, not newly learned model semantics.
The native model output is preserved, postvalidated and scored without repair.

The entire observed suite D20+H16+F20+G16=72 cases is regression. Sixteen fresh
role/target contrast scenarios are frozen before calls, including duplicates,
withdrawal, conflicting priority and actual forbidden file targets. Two seeds
and two arms (V3/V4) require 352 actual calls. No new cases or tuning are added
after observing the holdout. Full strict validity, exact positive intents,
specified conservative decisions, workflows, unchanged preapproval state and
external sentinel are required. Positive accuracy must strictly improve over V3
without per-case regression. A pass still requires integration before deployment.

```powershell
.venv/Scripts/python.exe -m experiments.personal_assistant_role_grounding.run --output artifacts/personal-assistant-role-grounding/2026-10-15/comparison-v1
.venv/Scripts/python.exe -m experiments.personal_assistant_role_grounding.verify --source artifacts/personal-assistant-role-grounding/2026-10-15/comparison-v1 --output artifacts/personal-assistant-role-grounding/2026-10-15/replay-v1
```

Backend setup installs the project in editable mode. No inference is performed by
the model-free protocol tests or replay verifier. Each run needs a fresh output.
