# Request Scenario Validation Verification

Date: 2026-09-10 (Asia/Tokyo). Scope: Evidence Remediation 19, local engineering QA only.

## Outcome

- Fixed pack: 15 cases; 14 expected behaviors, one known limitation, zero regressions/errors.
- No inference calls, external Tool execution, official result writes or human review attestations.
- Input QA: four live automated_qa attempts, not four participants. Three API attempts and one
  browser attempt test different save/submit paths. No usability success-rate claim is made.
- Official state: BLOCKED / 110 critical failures / 384 runtime results / output review 0/30 /
  not_production_ready, unchanged before/after API QA and after browser QA.

## Checks Run

| Check | Result |
| --- | --- |
| New scenario/input tests | 34 passed |
| Related tests, including existing contract and metadata compatibility | 85 passed |
| Full host backend suite | 569 passed, 1 skipped |
| Full Docker backend suite | 570 passed; two existing dependency deprecation warnings |
| Host and Docker Ruff app/tests | Passed |
| Smoke script Ruff | Passed |
| Frontend lint | Passed |
| Frontend TypeScript no-emit | Passed |
| Docker backend/worker/frontend builds | Passed |
| Docker migration | 202609100001 applied/head |
| Service check | DB/backend healthy, worker/frontend running |
| Live API smoke | Passed; existing request list and official metrics unchanged |
| Prior evidence-chain audit | diagnostic_only_with_false_block_and_false_allow_caveats |
| Finalized reference workload 1.0.4 validate | ready; 64/64 approved, critical 20/20 |

The reference workload's `ready` describes its approved case pack, not production readiness.
Its corpus SHA-256 remains `2772ab9a898529c052337ad6d06e4f0950333a316d72d79778dbc6cfe8cf0642`.

## API Evidence

[Immutable smoke output](../../../artifacts/structured-requests/2026-09-10-scenarios-api-smoke.json)
SHA-256: `24341b9411e9d73ad21d546c4c4d632cd30f99eed789c6a618b4ed9c2ba6d5cd`.

- Automated run: `047c37f4-7983-4ffa-a835-4e126c9b22a7`.
- SRC-01 attempt: `452087c2-0ef5-45b6-94db-1598de3396e3`. First save low, changed save high;
  stale submit rejected 409, final submission reports priority mismatch and one correction.
- SRC-04 attempt: `6cee8cd8-65ea-465a-aeba-27f4bad7aa38`. Explicit omission matches the key.
- SRC-09 attempt: `8a78896c-a339-46b6-84c7-549eb9b7953a`. Clarification matches the key.
- Repeated submissions return the existing result without recalculating time or corrections.

The smoke verifies the latest existing live request records (API limit 50), not an independent
full-database forensic diff. Runner isolation is also covered by tests and its separate DB setup.

Pack SHA-256: `129384ee15f7757de8e758630822bc0894a1e9b04d9677c88e128c320de635b0`.
The full JSON contains fixture definitions, actual traces, counts, implementation hashes,
submitted exercise records and official before/after snapshots. It is not blinded study material.

## Browser QA

Page: [local validation UI](http://localhost:3000/structured-requests/validation).

- Ran the full pack through the UI: `92147afc-2992-4a7e-be87-68101efb5653`, counts 14/1/0/0.
- Filtered known_limitation and confirmed SRC-15's semantic limitation is explicitly displayed.
- Clicked report download; parsed the actual downloaded JSON with the matching run ID/counts and
  gate_evidence=false. Browser download-event wait timed out, but the file was successfully created
  and verified at `C:/Users/rokn2/Downloads/request-scenarios-92147afc-2992-4a7e-be87-68101efb5653.json`.
- ArrowRight switched and focused the input tab. Default source was automated QA.
- Started SRC-01 `879566b8-d467-4c81-8409-1b18fab15834` as automated_qa. Value selection was required.
- Saved high, acknowledged, changed to low: acknowledgment cleared and submit disabled until save.
  Second save produced revision 2 / correction count 1. Explicit acknowledgment and submit matched
  the scenario key. Reload/reopen preserved the submitted result and disabled editing.
- Browser attempt elapsed time was 242.677 seconds, including automation pauses and other work.
  It is not evidence of a person's task completion time.
- Visually inspected full-page screenshots at 1440x1000 and 390x844. Document scroll width matched
  client width (1425 desktop, 375 mobile; the difference from viewport width is the scrollbar).
  Tables have local horizontal scrolling on mobile; page text and controls did not overlap.

Screenshots:

- [Desktop results](results-desktop.png)
- [Mobile limitation detail](results-mobile.png)
- [Desktop submitted input](study-desktop.png)
- [Mobile submitted input](study-mobile.png)

## Reproduction

From the project root with Docker Desktop running:

```powershell
docker compose build backend agent-worker frontend
docker compose up -d db backend agent-worker frontend
docker compose exec -T backend alembic current
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend python -m ruff check app tests
.venv/Scripts/python.exe tools/smoke_request_scenarios.py --output artifacts/structured-requests/scenarios-api-smoke-rerun.json
```

The smoke creates one separate report and three automated exercise records. It refuses to
overwrite an existing output file; select a new filename on subsequent runs. It uses the local
API at port 18000 and does not require Ollama. Do not relabel these records as participant evidence.

Frontend checks from `frontend/`:

```powershell
npm.cmd run lint
npx.cmd tsc --noEmit
```

Prior audit from the project root:

```powershell
py -3.12 -c "import sys; sys.path.insert(0,'tools'); from review_ticket_priority import audit; print(audit()['assessment'])"
docker compose exec -T backend python -m app.reference_workload.cli --repository-root /workspace --manifest /workspace/reference_workload/revisions/1.0.4/manifest.json --cases /workspace/reference_workload/revisions/1.0.4/cases.jsonl --reviews /workspace/reference_workload/revisions/1.0.4/review_manifest.jsonl validate
```

## Residual Limits

No independent participant results, blinded holdout, active-time measurement or actual main-lab
end-to-end usability study is available. The isolated runner does not reproduce PostgreSQL
concurrency, external delivery failures or production authorization. SRC-15 remains a genuine
semantic gap, deliberately visible rather than counted as a safety pass. These results authorize
neither candidate promotion nor removal of the official BLOCKED verdict.

[Korean usage and technical guide](../../request_scenario_validation.md)
