# Bounded Synthetic Review Verification

This suite replaces mandatory manual functional checking, not independent human UX evidence.
Application capabilities and the existing blocked model release gate are unchanged.

## Scope and Metrics

- Ten existing manual flows, three rule-based reviewer policies: zero edits, at most two
  changed keys, and a guided upper bound of six keys. One correction save, no model retries.
- Four fixed behavior variants: missing time, contradictory priority, withdrawn request,
  and a safe file move despite an untrusted quoted instruction. Zero corrections for these.
- Actual default production generation: 34 requests, one seed, no endpoint switch or prompt tuning.
- Original model correctness, strict draft validity, uncorrected completion, corrected completion,
  changed keys, planned user edits, abandonment and code-only blocking are separate metrics.
- Reviewers can read the authored goal. They are idealized deterministic scripts, not realistic
  people or independent LLM judges. The target model gets only the request and public workspace.
- Final state, exact optional fields, Tokyo instants, file hashes, approval boundaries and
  replay idempotency are asserted independently of the executor's planning function.
- Service expiry uses an explicitly controlled clock. The separate browser test waits the
  actual 300 seconds, refreshes the page and submits a rejected stale approval.
- Five actual process kills: before effect, linked paths, completed move, modified destination,
  independent copy. One overlapping approval pair and subsequent idempotent replay.

No demographic personas, model-authored correctness grades, private folders, external calendar
accounts, unattended production approval, human attestation or broad model sweep are included.
Multiple policies use the same ten goals; they are not 30 independent task samples.
Functional automation may complete while model accuracy remains blocked and real UX unverified.

## Run

From the repository root, with the existing backend environment and isolated Ollama on 11435:

```powershell
New-Item -ItemType Directory -Path artifacts/personal-assistant-persona/my-run
.venv/Scripts/python.exe -m pytest experiments/personal_assistant_persona_e2e -q -p no:cacheprovider
.venv/Scripts/python.exe -m experiments.personal_assistant_persona_e2e.run --output artifacts/personal-assistant-persona/my-run/model
.venv/Scripts/python.exe -m experiments.personal_assistant_persona_e2e.protocol --output artifacts/personal-assistant-persona/my-run/browser-protocol.json
.venv/Scripts/python.exe tools/init_personal_assistant_review.py --workspace artifacts/personal-assistant-persona/my-run/browser-workspace
.\tools\start_personal_assistant_review.ps1 -Workspace artifacts/personal-assistant-persona/my-run/browser-workspace
node tools/verify_personal_assistant_personas.mjs --protocol artifacts/personal-assistant-persona/my-run/browser-protocol.json --output artifacts/personal-assistant-persona/my-run/browser
.venv/Scripts/python.exe -m experiments.personal_assistant_persona_e2e.verify --source artifacts/personal-assistant-persona/my-run/model --browser artifacts/personal-assistant-persona/my-run/browser --output artifacts/personal-assistant-persona/my-run/replay
```

Do not initialize or run over existing directories. Resolve occupied ports without terminating
unrelated processes. Use `--playwright-module` with an installed module path when necessary.
Do not run the model and browser generations concurrently on the one-model runtime.
The unit/real-process tests do not require a model and are included in CI; GPU/browser runs are
explicit local experiments, not claimed as CI checks. Keep raw requests, SQLite and transport
artifacts out of the public repository.

## Evidence

`protocol.json` and source archives are written before inference. `observations.json` preserves
raw drafts and edit decisions. `transport.json` captures actual public requests/responses without
rewriting them. `faults.json` stores actual process outcomes. `summary.json` includes SHA-256
digests. `verify.py` checks captured source hashes, public payload boundaries, replays all 34
workflows without inference and recomputes scores. Browser results include script/protocol hashes,
all ten raw drafts, corrections, state assertions and screenshots.

These are local reproducibility records, not cryptographically independent attestations.
