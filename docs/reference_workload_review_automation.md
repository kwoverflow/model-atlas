# Reference Workload Review Automation

## Purpose

Sprint 6A requires explicit human provenance before draft cases become active. Reviewing every
field in all 64 cases manually is slow, so Model Atlas provides deterministic review assistance
without converting a machine recommendation into a human decision.

The automation checks every case and narrows direct inspection to all critical cases plus one
non-critical risk sample per affected taxonomy category. A person then signs one report-bound
attestation covering the inspected sample and the machine-pass cases.

## Automated checks

The `review-assist` command validates:

- immutable case and corpus hashes;
- expected-fact, forbidden-claim, and refusal contracts;
- current corpus identity and referenced chunk integrity;
- lexical overlap between expected facts and source excerpts as an advisory signal;
- bounded Tool Registry membership and argument-schema compatibility;
- explicit failure fixtures and bounded retry count;
- bounded Agent steps, retrievals, Tool calls, and memory-write policy;
- exact duplicate queries;
- case criticality and category risk.

Lexical overlap is only a triage signal. It does not claim semantic equivalence or replace source
inspection.

## Triage policy

Each case receives one machine recommendation:

| Recommendation | Meaning |
| --- | --- |
| `eligible_for_bulk_review` | Structural checks passed and category sampling covers residual risk |
| `spot_check_required` | Critical case or selected non-critical category risk sample |
| `repair_required` | A blocker contract failed; approval generation is disabled |

All critical cases remain in the required human set. Among non-critical cases with residual risk,
the lexically first stable case ID in each category is selected as the category sample. Because
selection uses stable IDs rather than randomness, reruns are reproducible.

Current source result:

```text
case count: 64
eligible for bulk review: 38
required spot checks: 26
repair required: 0
report SHA-256: 4e3c3eb261005c6dafaf7b675e3e4698f54fc0074a3823e9338a3fda2a1774b0
```

## Generated files

```text
reference_workload/review_assistance.json
reference_workload/review_assistance.csv
reference_workload/review_assistance.html
reference_workload/review_attestation.json
```

The JSON report contains source paths, heading paths, source/chunk hashes, excerpts, checks, and
risk reasons. The CSV is the compact filterable view. The standalone HTML provides filters, a
master-detail review flow, browser-local progress, responsive desktop/mobile layouts, and a final
attestation download. The attestation template contains no reviewer identity, no confirmed case
IDs, and no approval by default.

Generating these files does not modify `review_manifest.jsonl` and does not increase the approved
case count.

## Workflow

1. Generate the assistance report:

```powershell
docker compose run --rm backend python -m app.reference_workload.cli review-assist
```

2. Inspect `review_assistance.csv`. Open the detailed JSON entries for the 26
   `spot_check_required` cases and compare their contracts with the included source evidence.

3. Complete `review_attestation.json`:

- provide a real human `reviewer` identity;
- keep the exact personal-review attestation statement;
- set `approve_automated_passes` to `true` only after accepting the machine-pass set;
- copy all `required_case_ids` into `confirmed_case_ids` only after checking them;
- add non-empty notes.

4. Record the approval ledger:

```powershell
docker compose run --rm backend python -m app.reference_workload.cli finalize-assisted-review
```

The command recomputes the current case-pack report, validates the stored report hash, rejects
stale or modified evidence, requires all required IDs, rejects machine-like reviewer identities,
and records the current UTC time only when the explicit human attestation succeeds.

5. Validate and bootstrap:

```powershell
docker compose run --rm backend python -m app.reference_workload.cli validate
docker compose run --rm backend python -m app.reference_workload.cli bootstrap
```

## Honesty boundary

- Machine generation time is machine metadata, not a human review timestamp.
- No automated check can populate a reviewer identity.
- No approval is created merely because all automated checks pass.
- `repair_required` disables assisted finalization.
- Local case approval does not imply Gate approval, release authorization, or production readiness.

## Recorded assisted-review outcome

On 2026-09-01, the user supplied a completed attestation bound to report SHA-256
`4e3c3eb261005c6dafaf7b675e3e4698f54fc0074a3823e9338a3fda2a1774b0`. The finalizer verified all
26 required spot-check confirmations, accepted the 38 automated-pass cases as an explicit batch,
and wrote 64 approved decisions with 20 approved critical cases. The approval event was recorded
at `2026-09-01T08:43:24+00:00`.

The resulting approval ledger passed validation and was bootstrapped idempotently. This event
approves the source-case contracts only. It does not manufacture human review of model outputs and
does not alter the production-readiness boundary.

## Model-output review remains separate

Source-case approval does not review any generated model output. The post-Phase 7
`model-atlas-reference-output-review-plan-v1` read model separately groups stored critical output
failures and selects a balanced 30-output review set. Its candidate assessments remain unapplied
and do not change review coverage. See `docs/reference_output_review_plan.md` and
`/reference-workload/review-plan`.
