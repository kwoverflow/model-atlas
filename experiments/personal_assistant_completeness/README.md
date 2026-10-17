# Creation Completeness V6

One bounded iteration compares frozen V5 with V6, retaining all 108 observed
scenarios plus 20 fresh contrast scenarios. Two arms and two seeds require 512
actual local model calls. No development model probes, retries, raw-output repairs
or post-holdout tuning are allowed. The public clock stays at
`2026-10-15T09:00:00+09:00` for controlled comparison, not the wall-clock date.

V6 separates literal title roles, request scope and field evidence. Recognized
creation requests constrain all provable fields, including required deadlines,
calendar start/duration, timezone and specified priority. Omitted deadlines and
priorities cannot be invented. Dates use Python datetime/zoneinfo validation;
supported Korean absolute dates, ISO local timestamps and today/tomorrow/day-after
are bounded input grammars, not unrestricted natural-language understanding.
Incomplete/conflicting fields clarify. Document framing and withdrawal cause
abstention from creation binding, not a fabricated field-validation error. The
existing compact model/path policy still handles unbound contexts; no provenance
guarantee is claimed for those fallback outputs. This is a hybrid parser/decoder/
LLM pipeline, not model training.

All exact positive intents, specified conservative decisions, strict field
constraints, independent workflows and unchanged preapproval/sentinel states must
pass. Require strict positive improvement over V5 and no paired regression. A pass
means pending full tests, replay and browser integration, never autonomous release.
The default remains `legacy` unless all required integration gates are confirmed.

```powershell
.venv/Scripts/python.exe -m experiments.personal_assistant_completeness.run --output artifacts/personal-assistant-completeness/2026-10-16/comparison-v1
.venv/Scripts/python.exe -m experiments.personal_assistant_completeness.verify --source artifacts/personal-assistant-completeness/2026-10-16/comparison-v1 --output artifacts/personal-assistant-completeness/2026-10-16/replay-v1
```

Use a fresh output directory and the pinned cached Ollama/model runtime. Protocol
tests and replay make zero model calls. Authored goals are never exposed to the
model. The independent confirmation oracle in the test harness does not make a
real user's blind approval of an incorrect form safe. Existing human edit,
confirmation, approval, cancellation and file recovery boundaries are unchanged.

## Completed Result

The gate is `BLOCKED_KEEP_LEGACY`. Existing 108 scenarios pass in both seeds for
V6: exact positives 116/116, specified conservative decisions 86/86, strict
contracts/evidence and workflows 216/216. Fresh cases retain C07's unnecessary
clarification (literal high inside a title versus actual low) and C19's unnecessary
refusal of an explanation-only document request. Both fail in both seeds, and V5
also fails them; there are no paired regressions.

| Combined metric | V5 | V6 |
| --- | ---: | ---: |
| Exact positive intents | 111/140 | 138/140 |
| Specified conservative decisions | 96/102 | 100/102 |
| Strict contract and evidence | 245/256 | 256/256 |
| Independent workflows | 227/256 | 254/256 |
| Unchanged preapproval state / sentinel | 256/256 | 256/256 |

There were 512 transport attempts and 511 returned raw outputs. V5's first D01 /
seed42 timed out during startup; it was not retried or replaced. V5's 11 errors
comprise that timeout and 10 evidence errors; V6 has none. Excluding the incomplete
positive pair gives V5 111/139 and V6 137/139. The primary frozen summary remains
unchanged; this is not a clean all-response benchmark or a latency comparison.

The frozen strict verifier fails on the recorded timeout. Supplementary zero-model
audit replays the 511 outputs and verifies all 512 transport requests, the failure
trace and 37 current/archived sources. It explicitly returns
`verified_with_transport_failures`, not complete replay success, and leaves
`integration_eligible=false`:

```powershell
.venv/Scripts/python.exe -m tools.audit_personal_assistant_completeness --source artifacts/personal-assistant-completeness/2026-10-16/comparison-v1 --output artifacts/personal-assistant-completeness/2026-10-16/replay-audit-v1
```

No candidate browser activation, default promotion or post-holdout model tuning
followed. See the [Korean report](../../docs/reports/2026-10-16_personal_assistant_completeness_ko.md)
for hashes, split results, tests, residual explanation quality and scope limits.
