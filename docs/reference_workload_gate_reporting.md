# Reference Workload Gate and Report Integration

## Purpose

Sprint 6A Phase 5 connects the selected reference-workload evidence to the existing Deployment
Gate and report surfaces. It does not introduce another evaluation engine, Gate engine, release
engine, or evidence store.

The integration has four boundaries:

1. Gate Preflight reads the existing workload, suite, policy, configuration, run, Result, and
   metric rows.
2. Gate evaluation persists the existing `GateEvaluation` and rule-result contracts.
3. Report generation reads the selected latest actual-runtime runs and stored Gate outcomes.
4. Production readiness remains independent from local Gate and release states.

## Commands

```powershell
make reference-gate
make reference-report
```

Equivalent Compose commands are:

```powershell
docker compose run --rm backend python -m app.reference_workload.cli gate
docker compose run --rm backend python -m app.reference_workload.cli report `
  --output-directory /artifacts/reference-workload
```

`reference-gate` runs non-persisting Preflight first. A configuration with a current completed Gate
for the same configuration, suite, and policy reuses that Gate. It does not create duplicate Gate
rows. A completed current runtime run is required.

## API

All report routes are read-only and live under `/api/v1/reference-workload`.

| Route | Result |
| --- | --- |
| `GET /report` | Structured `reference-workload-report-v1` JSON |
| `GET /report.md` | Markdown rendered only from the structured report object |

The Markdown renderer does not query the database or recompute metrics. This keeps JSON and
Markdown decision semantics aligned.

## Report contents

The report binds:

- workload, corpus, source manifest, and evaluation-suite versions and hashes;
- concrete configuration, model digest, runtime, context, prompt, and generation settings;
- source-case and model-output review coverage;
- selected-run configuration and category metrics;
- critical failures and review state;
- stored Gate verdicts, decision hashes, rule results, and release-readiness snapshots;
- separate evidence-trust, release-readiness, and production-readiness states;
- incomplete matrix and portfolio entries;
- reproduction commands, limitations, and linked evidence IDs.

## Generated artifacts

`make reference-report` atomically writes these files under `artifacts/reference-workload/`:

| File | Purpose |
| --- | --- |
| `reference-workload-report.json` | Canonical structured report |
| `reference-workload-report.md` | Human-readable rendering of the report object |
| `configuration-comparison.csv` | Compact configuration comparison |
| `critical-failures.json` | Failure-first review export |
| `reproduction-manifest.json` | Report hash, evidence IDs, commands, and artifact hashes |

The reproduction manifest lists the other four artifacts. It intentionally does not hash itself,
which avoids a circular digest contract. The CLI summary includes the manifest's own SHA-256.

## Recorded result

Recorded on 2026-09-02:

| State | Value |
| --- | --- |
| Evaluation | `COMPLETE` |
| Gate | `BLOCKED` for all 3 configurations |
| Evidence trust | `needs_judge_review` |
| Release readiness | `BLOCKED` |
| Production readiness | `not_production_ready` |
| Selected actual-runtime Results | 384 |
| Critical failures | 110 |
| Model outputs reviewed | 0 of 30 target |
| Portfolio checks | 7 of 8 passed |

The Gate result is an expected evidence result, not a pipeline error. Every Preflight was
evaluable, every Gate was persisted, and a second orchestration run reused all three Gate IDs.
The tested models failed eight blocker rules per configuration, including critical failure,
structured-output, Tool, RAG, and Agent targets. OOM, latency, and actual local-runtime coverage
passed.

Report SHA-256:
`66beef4b997260abbf381ba4265bb6458d52093eaa0ac4f1dc5ed4aeff76fb37`.

## Honesty boundary

The report must not be read as production validation. All 384 selected Results are locally
authored actual-runtime evidence and remain heuristic-only. There are no verified
production-captured Results and no reviewed model outputs. A future local Gate approval would
still not by itself establish production readiness.
