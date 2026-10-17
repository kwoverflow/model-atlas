# One Bounded Stabilization Candidate

Candidate `compact-grounded-v1` combines a compact allowlisted user payload, a concise prompt,
native Ollama generate, decision-consistent decoding branches and a title enum derived only from
one explicit quoted creation target in the public request. It preserves inner punctuation and
abstains from title grounding for multiple, unmatched or document-context quotes.

This is hybrid request-grounded pipeline accuracy, not standalone model intelligence. No response
is stripped, repaired, retried or replaced by an expected answer. Existing acceptance schemas,
planner, approval, cancel and recovery contracts are unchanged. Incomplete completions preserve
their raw text but cannot count as accepted drafts.

## Fixed Test and Adoption Policy

- Existing D01-D20 regression: 20 cases x two seeds x two arms = 80 calls.
- New H01-H16 holdout: 16 cases x two seeds x two arms = 64 calls.
- No observations or case IDs in target model input; no gold fields or hidden final-state goals.
- Both arms use the same fixed clock, model digest, real public state, token limit and seeds.
  Transport, prompt and request grounding differ as one candidate bundle; no endpoint-only claim.
- Human-review draft-path adoption requires complete coverage, every candidate strict schema and
  workflow check, every positive intent exact, every new holdout conservative decision correct,
  zero runtime/incomplete-generation errors, unchanged preapproval state and improvement over the
  baseline on positive intent counts in both splits. One failed criterion retains the old default.
- Code-only regression blockers are reported as workflow guards, not correct model decisions.
- Autonomous release remains BLOCKED, even if the human-reviewed path is adopted. No real accounts,
  personal folders, user UX or broad generalization are validated here.
- One candidate and one comparison. No holdout-driven tuning or reruns selecting the best output.

The standalone synthetic connection probe is a runtime smoke check, not a scored evaluation case.
Historical experiments retain their source archives and results.

## Run

```powershell
.venv/Scripts/python.exe -m pytest experiments/personal_assistant_stabilization -q -p no:cacheprovider
.venv/Scripts/python.exe -m experiments.personal_assistant_stabilization.run --output artifacts/personal-assistant-stabilization/my-run
.venv/Scripts/python.exe -m experiments.personal_assistant_stabilization.verify --source artifacts/personal-assistant-stabilization/my-run --output artifacts/personal-assistant-stabilization/my-replay
```

Use fresh directories. The pinned synthetic-only runtime must be on localhost:11435.
The protocol and source archives are saved before inference. Raw observations and real transport
responses remain under ignored artifacts; never upload personal databases or request logs.

## Recorded Decision (2026-10-11)

The fixed comparison completed all 144 calls. The candidate passed 72/72 strict schema checks,
44/44 positive intent comparisons and 72/72 workflow checks. Holdout conservative decisions were
10/12: H15 proposed an upper-directory move under both seeds instead of refusing it. The existing
code guard blocked the move. The preregistered decision remains `KEEP_LEGACY_DEFAULT`; autonomous
release remains `BLOCKED_UNCHANGED`. No prompt, schema or criteria were adjusted after this result.

The candidate is an explicit local-review opt-in through `PERSONAL_ASSISTANT_DRAFT_STRATEGY`.
The default remains `legacy`; inference failures never silently retry or fall back. Historical
results and frozen source archives remain unchanged. See the
[Korean successor report](../../docs/reports/2026-10-11_personal_assistant_accuracy_stabilization_ko.md).

## Browser Integration Audit

Use a new initialized synthetic workspace and explicitly select the candidate before starting
the backend. This reuses the fixed M01-M10 browser regression, not an unseen benchmark.
The audit records raw draft accuracy separately from any oracle-assisted form correction.

```powershell
.venv/Scripts/python.exe tools/verify_personal_assistant_stabilization_browser.py freeze --source artifacts/personal-assistant-stabilization/my-run --output artifacts/personal-assistant-stabilization/my-browser-plan
node tools/verify_personal_assistant_personas.mjs --protocol artifacts/personal-assistant-stabilization/my-browser-plan/protocol.json --output artifacts/personal-assistant-stabilization/my-browser-evidence
.venv/Scripts/python.exe tools/verify_personal_assistant_stabilization_browser.py verify --source artifacts/personal-assistant-stabilization/my-browser-plan --evidence artifacts/personal-assistant-stabilization/my-browser-evidence --output artifacts/personal-assistant-stabilization/my-browser-verification.json
```

All paths must be fresh. Browser verification waits for the real 300-second approval expiry.
No correction can promote a failed raw draft score or override the fixed adoption decision.
