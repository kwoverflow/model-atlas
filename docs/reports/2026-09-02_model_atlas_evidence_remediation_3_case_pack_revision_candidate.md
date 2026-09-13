# Model Atlas Evidence Remediation 3: Case-Pack Revision Candidate

Date: 2026-09-02  
Revision candidate: `1.0.1`  
Source workload: `1.0.0`  
Decision: `HUMAN_REVIEW_REQUIRED`  
Production readiness: `not_production_ready`

> Follow-up on 2026-09-03 JST: reviewer `김대건` approved all four changes, revision `1.0.1`
> finalized at 64/64 approved cases and 20/20 approved critical cases, and the isolated 12-result
> diagnostic passed all four cases for all three configurations. See
> `2026-09-03_model_atlas_evidence_remediation_3_finalization_and_diagnostic.md`.

## Purpose

The second remediation unit proved that the bounded Agent compiler could produce structurally
valid plans, but all four P0 Agent/RAG tasks still failed because their expected chunks were
outside the declared lexical retriever's `top_k=5`. This unit creates an isolated case-pack
revision candidate that corrects those four retrieval contracts without changing the canonical
`1.0.0` workload, historical Results, stored Gate decisions, or production-readiness status.

## Candidate Result

| Case | Old rank | Revised rank | Revised evidence |
| --- | ---: | ---: | --- |
| `KO-RAG-TOOL-001` | 8 | 3 | `docs/deployment_gate.md` / `Sprint 4A Status Separation` |
| `KO-RAG-TOOL-002` | 40 | 1 | `docs/operational_slo_and_paging.md` / `SLO breached` |
| `KO-RAG-TOOL-003` | 14 | 1 | `docs/incident_response_and_burn_rate.md` / `Multi-Window SLO Contract` |
| `KO-AGENT-001` | 15 | 1 | `docs/deployment_gate.md` / `Verdicts` |

All four revised contracts achieve retrieval recall `1.0` within `top_k=5`. The revision audit
status is `pass`, but this only proves reachability and evidence identity. It does not prove model
task success, authorize labels, or replace the canonical portfolio.

Candidate state at generation time:

- 64 total cases;
- 60 unchanged approvals retained;
- 4 changed critical cases returned to `draft`;
- 16 approved critical cases out of the required 20;
- `portfolio_ready=false`;
- bootstrap disabled until the four changed cases are personally reviewed.

## Contract Design

Revision `1.0.1` declares `reviewed-bilingual-retrieval-query-v1`. The public retrieval query is
part of the executable case contract and can be supplied to the Agent planner. Expected chunk IDs
remain evaluation-only and are not exposed in the model prompt, planner context, or adapter user
payload. The execution trace records whether the query came from `public_contract`, `model_plan`,
or the original request.

The candidate generator is isolated to `reference_workload/revisions/1.0.1`. It copies unchanged
cases and approvals, revises exactly the four declared contracts, validates source path and heading
identity, writes artifacts atomically, and records old/new ranks, excerpts, case hashes, and source
hashes. Once a revision is finalized, the generator refuses to overwrite it; a further change must
use a new semantic version.

## Human Review Boundary

Open `reference_workload/revisions/1.0.1/revision_review.html` and review all four old/new evidence
pairs. For each case, choose `approved` or `rejected` and add review notes. Enter a real human
reviewer name, accept the attestation statement, and download `review_attestation.json`.

Finalization is intentionally a separate command:

```powershell
Copy-Item C:\Users\rokn2\Downloads\review_attestation.json `
  .\reference_workload\revisions\1.0.1\review_attestation.json
make reference-finalize-case-revision
```

Finalization verifies the report hash, every candidate artifact hash, all four revised case hashes,
the exact attestation statement, and one decision per changed case. Machine-like reviewer names are
rejected. The final review manifest and finalization report are written atomically. No attestation
was created or applied during this remediation unit.

## Evidence Identity

- logical revision report SHA-256:
  `0832df67b0aa15010bde4176423bb694ef3d2e1a5b375207fabc4c0cf18c3474`;
- source manifest SHA-256:
  `b5f4ea5c0e23cf14830c77414de6732307eb47153f3f82eab692149082893d98`;
- source cases SHA-256:
  `81f95d1b7bb7b82f3b44bf0dc75725e7ffae2ab726ab75c83a579ae34e2ad015`;
- source reviews SHA-256:
  `88f195d11e193255d17bc909df28d3e78966b44eb6bac4c746ebda4fb219481d`;
- revision manifest SHA-256:
  `c16a4b93103046644353dd913ff50658211e98fb4a59928a086a8b678ca7889e`;
- revision cases SHA-256:
  `3cb3fa44fe77d3baef817bbd856375a670ec6aaa85970484e312c0ce88f38513`;
- draft review manifest SHA-256:
  `1a26960f9f132edce7d9e34ac64c6dce9f53c787b3a0c9bd58777fccc4fe716d`;
- retrieval audit logical SHA-256:
  `5863b810e43d273d36eebb8f9de610e65cd32df112cccc8d5d84f8652273d7fc`.

## Verification

```text
Focused revision/Agent/runtime tests: 25 passed, 2 warnings
Backend full suite: 231 passed, 1 skipped, 2 warnings
Backend Ruff: passed
Docker focused tests: 25 passed, 1 warning
Docker Ruff and backend/worker image build: passed
Live backend health and authoritative 1.0.0 overview: passed
Alembic current: 202608040001 (head)
Retrieval contract audit: pass, 4 of 4 reachable within top_k=5
Canonical workload mutated: false
Historical Results mutated: false
Changed cases approved: false
Production readiness: not_production_ready
```

The warnings are an existing Starlette/httpx deprecation warning and a local Windows pytest cache
permission warning; neither changes test outcomes. In-app browser visual QA could not load the
local `file://` review artifact because the browser security policy blocks local-file navigation.
The HTML generation, attestation schema, hash binding, and finalization path were verified through
automated tests. Human visual and semantic review was pending at this candidate stage and was
completed in the follow-up report.

After rebuilding and replacing the backend and Agent worker containers, the live API still reports
canonical workload `1.0.0`, 384 actual Results, 110 critical failures, zero of 30 model outputs
human-reviewed, and three of three Gates `BLOCKED`. The Gate summaries retain eight failed blocker
rules per configuration and critical failure counts of 51, 36, and 36. The candidate therefore has
no effect on authoritative stored evidence.

## Next Decision at Candidate Generation

Do not rerun the four-case Agent diagnostic yet. First complete and apply the human attestation.
If all four cases are approved and finalization reports 64 approved cases, 20 approved critical
cases, and `portfolio_ready=true`, run a fresh isolated four-case diagnostic against revision
`1.0.1`. Preserve the current 384-result portfolio and all three `BLOCKED` Gates as historical
evidence; any improved run is new evidence and requires a new comparison and Gate evaluation.

That decision path was completed on 2026-09-03 JST. The new diagnostic remains isolated evidence;
the canonical portfolio and Gate outcomes remain unchanged.
