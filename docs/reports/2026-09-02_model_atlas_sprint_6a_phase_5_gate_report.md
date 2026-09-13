# Model Atlas Sprint 6A Phase 5 Gate and Report Integration

Recorded: 2026-09-02

## Executive result

Sprint 6A Phase 5 is complete. The three stored reference-workload configurations now flow through
the existing Gate Preflight and Deployment Gate services, and the selected stored evidence can be
exported as one hash-bound JSON, Markdown, CSV, failure, and reproduction package.

All three Gate evaluations are `BLOCKED`. This is the correct policy result for the observed model
quality: each configuration failed eight blocker rules. Evaluation execution is still `COMPLETE`,
evidence trust is `needs_judge_review`, release readiness is `BLOCKED`, and production readiness is
`not_production_ready`.

## Delivered behavior

- Added idempotent reference Gate orchestration over the existing Preflight and evaluator.
- Added read-only `GET /api/v1/reference-workload/report` and `/report.md` endpoints.
- Added a pure Markdown renderer that consumes the structured report object.
- Added atomic generation of five evaluator artifacts and SHA-256 reproduction metadata.
- Added JSON and Markdown download controls to `/reference-workload`.
- Linked comparison rows to an existing Gate or a preselected Gate Preflight flow.
- Added query-driven configuration, suite, and policy selection to the Gate form.
- Replaced the Phase 4 future-report placeholder with the live export action.
- Kept Gate, evidence trust, release readiness, and production readiness separate.

## Live decision state

| Configuration | Gate ID | Verdict | Failed blocker rules |
| --- | --- | --- | ---: |
| `small-baseline` | `2cd81270-d870-4bd2-a325-d98a990deb3f` | `BLOCKED` | 8 |
| `medium-candidate` | `38449033-db55-4494-bad7-dfb7aebc6dcd` | `BLOCKED` | 8 |
| `prompt-variant` | `9538a38c-05fb-4437-ba59-ef14944d582c` | `BLOCKED` | 8 |

The repeated Gate command created 0 new rows and reused all 3 existing current Gate evaluations.

## Artifact integrity

| Artifact | SHA-256 |
| --- | --- |
| `reference-workload-report.json` | `66beef4b997260abbf381ba4265bb6458d52093eaa0ac4f1dc5ed4aeff76fb37` |
| `reference-workload-report.md` | `782aa6456637e85b2f9a19c228c0847433eaf9ab7482a873d23f1fa1f6f4a387` |
| `configuration-comparison.csv` | `d617dc9a0042da3d1d4cd2322512f46436e03145da06109e9d8fbc4a2031ea82` |
| `critical-failures.json` | `7af29f4962f437a259604178cb9213135192c496bb3ae84b25c2b30a781db25f` |
| `reproduction-manifest.json` | `2f564cda9805c428af43372d6afde73f2f00351b84f7ba5f590e259e39481189` |

Independent host-side hashing matched the CLI output and reproduction manifest.

## Verification

```text
Focused reference-workload tests: 5 passed
Docker backend full suite: 217 passed, 1 upstream deprecation warning
Docker backend Ruff: all checks passed
Frontend ESLint: passed
Frontend TypeScript and Next.js production build: passed
Docker backend/frontend image build: passed
Live Gate first run: 3 created, 0 blocked by Preflight
Live Gate second run: 0 created, 3 reused
Live report: 3 configurations, 384 Results, 110 critical failures, 24 category rows
Portfolio completion: 7 of 8 checks passed
Desktop UI: document overflow 0, download links and 3 Gate links present
390px mobile UI: document overflow 0, report controls visible
Preflight deep link: configuration, suite, and policy selected correctly
Browser console: 0 warnings or errors
```

The warning is the existing upstream Starlette TestClient deprecation warning.

## Remaining evidence gap

The only failing portfolio check is model-output review: 0 of the target 30 outputs have an
applied judge label or explicit human review. The 110 critical failures and all 384 heuristic-only
Results remain available for failure-first review. Phase 6 bounded modularization is the next
implementation unit; review evidence and final portfolio verification remain explicit later work.
