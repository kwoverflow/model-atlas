# Reference Output Review Plan

Updated: 2026-09-02

## Purpose

The output review plan turns the selected reference workload's critical failure rows into a
bounded, reproducible human-review queue. It reduces repeated inspection work without creating a
judge label, applying a score, or claiming human review.

The plan reads the same exact portfolio runs selected by the Reference Workload aggregate. It does
not inspect unrelated historical runs, smoke-only configurations, synthetic fixtures, or current
Gate-wide outcome totals.

## Read-only contract

`model-atlas-reference-output-review-plan-v1` is computed at read time and writes no database row.
Every candidate assessment contains:

```text
source: deterministic_failure_triage
applied: false
human_reviewed: false
```

The candidate copies inspectable heuristic scores and identifies the stored critical failure
reason. It is not included in Evidence Trust candidate-label coverage because no imported or
reviewed judge label exists. A verified reviewer must still confirm, override, or reject the
result through the existing append-only Judge Review decision path.

Heuristic-only and raw-label Judge Review rows now explicitly set `needs_review=true`. An existing
applied or human-reviewed decision remains the only condition that clears the review requirement.

## Clustering and priority

Failures are grouped by stable `(external_case_id, failure_reason)` identity. The cluster hash also
binds the exact sorted Benchmark Result IDs.

| Priority | Rule |
| --- | --- |
| `P0` | The same case and failure reason appears in every selected portfolio configuration |
| `P1` | The failure is repeated or appears in at least two configurations |
| `P2` | A single-configuration, single-result critical failure |

Priority reasons state configuration spread, result-row recurrence, critical category, and
unreviewed row count. The rules use stored evidence only and do not infer semantic correctness.

## Thirty-output selection

The default target is 30 outputs because that is the current portfolio human-review target.
Selection is deterministic:

1. choose one result from every cluster;
2. during representative selection, prefer the configuration with the lowest current count;
3. fill remaining slots by configuration count, cluster count, priority, score, and stable IDs;
4. hash the comparison identity, target, exact failure IDs, cluster records, and selected IDs.

The generated timestamp is excluded from `plan_hash`, so repeated reads over unchanged evidence
produce the same plan identity.

## Verified live result

The 2026-09-02 Compose database produced:

| Measure | Value |
| --- | ---: |
| Critical failure outcomes | 110 |
| Failure clusters | 20 |
| P0 / P1 / P2 clusters | 17 / 3 / 0 |
| Selected outputs | 30 |
| Selected P0 / P1 / P2 outputs | 27 / 3 / 0 |
| Unique critical cases covered | 20 |
| Risk categories covered | 8 |
| `small-baseline` selections | 10 |
| `medium-candidate` selections | 10 |
| `prompt-variant` selections | 10 |
| Human-reviewed outputs | 0 |
| Remaining human-review target | 30 |

Plan SHA-256 identity:

```text
587c35dbf6d4dba85b221551103e683ef903f82e8bdca37e4ab65cd81008a65e
```

Persisted JSON artifact SHA-256:

```text
65146e64040169b439da165471c9635aa25c1e6d2eeb601514ee21a290a705d5
```

The artifact is `artifacts/reference-workload/output-review-plan-v1.json`.

## Interfaces

```text
GET /api/v1/reference-workload/output-review-plan?target_count=30
GET /api/v1/judge-labels/review?benchmark_run_id=<run>&benchmark_result_id=<result>
```

The operator UI is available at:

```text
http://localhost:3000/reference-workload/review-plan
```

The Reference Workload page links to the prioritized plan. Each cluster and selected output has a
result-scoped Judge Review link. The focused Judge page returns one result row and preserves the
existing verified-role, separation-of-duties, append-only decision service.

## Evidence boundary

- Generating or downloading the plan does not apply labels.
- Candidate assessments do not increase Human Review or Evidence Trust coverage.
- The 30 selected rows are a review workload, not 30 completed reviews.
- The plan does not change Gate verdicts, report evidence, or release readiness.
- Local actual-runtime evidence remains non-production evidence.
- Production readiness remains `not_production_ready`.
