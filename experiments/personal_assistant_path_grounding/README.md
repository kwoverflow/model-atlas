# Final Public-Path Candidate

This experiment compares `compact-grounded-v1` with `compact-path-grounded-v3`.
The failed V2 experiment and all its evidence remain unchanged. Its 20 observed
holdout cases are now regression cases, not unseen evidence.

The frozen 2026-10-11 run completed 288 actual calls and 288 model-free replays.
V3 passed all 58 specified conservative decisions, including 42 forbidden-path
trials, but rejected two legitimate path-like todo titles under both seeds.
Positive accuracy was 68/72. The gate is `BLOCKED_KEEP_LEGACY`; no candidate
browser activation or default change was performed. See the
[Korean result report](../../docs/reports/2026-10-11_personal_assistant_path_boundary_ko.md).

Before inference, the runner freezes 56 regression and 16 fresh holdout cases,
two seeds, the pinned local runtime, source snapshots and adoption criteria.
There are 288 actual calls, no retries and no output repair. Public inputs contain
only request, clock, timezone, events, tasks and the file inventory. Authored goal
fields are used only by the independent test harness.

V3 keeps the original compact prompt. An anchored, bounded Korean file-command
parser supplies literal source spans to a parity-tested lexical policy and native
decoding constraints. It abstains on quoted document context, withdrawal, compound
or uncertain requests. This is a hybrid pipeline result, not proof that the LLM
independently learned path safety. Filesystem guards and manual approvals remain
authoritative, including symlink, hardlink and parent-directory checks.

All candidate raw schema, exact positive intents, conservative decisions, workflows,
preapproval state and synthetic external sentinel checks must pass without positive
regression. A strict conservative improvement is required. A pass only permits
replay and browser integration; it does not enable autonomous execution. This is
the final candidate in this task: a failure retains the legacy default.

```powershell
.venv/Scripts/python.exe -m experiments.personal_assistant_path_grounding.run --output artifacts/personal-assistant-path-grounding/2026-10-11/comparison-v1
.venv/Scripts/python.exe -m experiments.personal_assistant_path_grounding.verify --source artifacts/personal-assistant-path-grounding/2026-10-11/comparison-v1 --output artifacts/personal-assistant-path-grounding/2026-10-11/replay-v1
```
