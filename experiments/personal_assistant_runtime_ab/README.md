# Personal Assistant Runtime A/B

Preregistered before corpus inference on 2026-10-11. This is a regression
comparison on the existing D01-D20 corpus, not a new holdout or a model ranking.

- Exactly two arms, 20 existing cases, seeds 42 and 1729: 80 requests, no retries.
- Same pinned Ollama 0.31.1, model digest, 8192 context, public input, system
  prompt, temperature 0, top_p 1, token budget 768 and approval policies.
- `chat`: existing OpenAI-compatible endpoint, full schema request.
- `generate`: native `/api/generate`, thinking disabled; the same validation
  schema is lowered to grammar hints (ASCII digit class, unbounded reason hint).
  Full reason length, field, temporal, decision/intent and execution checks remain.
- No response repair, output rewriting, human edits, expected fields in prompts,
  changed thresholds, model downloads or runtime upgrades.
- Both arms must preserve preapproval state. Adoption requires complete coverage,
  zero runtime errors, 40/40 strict schema checks, all blocking/control workflows,
  improved positive extraction and workflow success without outcome regression.
- All 40 workflows passing is still required to clear the sandbox E2E gate.
  Adoption of a better extraction path does not automatically clear that gate.
- Any corpus-informed follow-up needs a separate protocol. Do not loop on prompts.
- Synthetic effects live in exclusively created sandboxes; approvals are automated
  harness actions, not independent human attestations. Existing V2 evidence is
  immutable and is reported separately, not retroactively rescored as improved.

```powershell
$env:PYTHONPATH = 'backend;.'
.venv/Scripts/python.exe -m experiments.personal_assistant_runtime_ab.run `
  --output artifacts/personal-assistant-runtime-ab/2026-10-11/run-1 `
  --confirm-synthetic-only
```

Protocol and source snapshots are saved before inference. Requests, unmodified
runtime responses, raw output, strict scores, workflow evidence and hashes are
recorded. A nonzero exit means the complete E2E gate remains blocked, even if the
runtime-path adoption decision is positive.
