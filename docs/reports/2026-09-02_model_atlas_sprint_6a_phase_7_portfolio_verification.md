# Model Atlas Sprint 6A Phase 7 Portfolio Verification

Recorded: 2026-09-02

## Executive result

Sprint 6A Phase 7 is complete as an implementation and portfolio-verification unit. The locked
Korean reference workload, approved case pack, actual Ollama portfolio matrix, stored comparison,
Gate orchestration, report artifacts, Docker services, database revision, backend tests, and
frontend build were verified from the running Compose environment.

This is not a release approval. All three reference configurations remain `BLOCKED`, human review
coverage is `0/30`, production-captured evidence is absent, portfolio completion is `7/8`, and
production readiness remains `not_production_ready`.

## Source and execution evidence

| Evidence | Verified value |
| --- | --- |
| Manifest SHA-256 | `151126c85c0a1ad71eff5da90cfaf2df977fdfb3cbea16e6bcc5a174c3f76711` |
| Corpus SHA-256 | `b6db4643768f1e9735507747aa88e54f93c7a3099dcb98ffbf6e9ac3e322e3cf` |
| Source files / chunks | 14 / 200 |
| Approved cases | 64 of 64 |
| Approved critical cases | 20 of 20 |
| Runtime matrix SHA-256 | `cfcf986f8e3a884a385a9873e370ccbe6f544b9628b15036db067033504845aa` |
| Suite SHA-256 | `2762c092dc552b3a46f18f9ac9362e1b77fad035932a573853535854175693d8` |
| Portfolio Results / Metrics | 384 / 384 |
| Portfolio configurations / artifacts | 3 / 2 |
| Trials per case | 2 |
| Stored comparison SHA-256 | `0c92a7b4793c2dd69d02a03a88e68ab19a233512dc50e1bc57ac7c6dcf716cd9` |

The persisted portfolio artifact replayed the exact three selected run IDs and retained the same
comparison hash:

- `small-baseline`: `2124b9f7-82f2-483f-939b-83a18400b9ab`;
- `medium-candidate`: `698428e8-59ec-4353-8f7d-ea592e60a206`;
- `prompt-variant`: `9da6d961-1e8a-460d-848e-b5c29ff2b59f`.

## Phase 7 smoke verification

Docker Ollama `0.31.1` exposed the observed `qwen2.5:0.5b` and `qwen2.5:1.5b` artifacts. The first
Phase 7 smoke run stored ten actual local-runtime Results under run
`2d6e4728-8043-4735-b745-939c2ad5b19a`. It revealed that a smoke run could reuse a portfolio
Deployment Configuration and temporarily become the aggregate read model's newest run.

The implementation now gives smoke runs a separate `Reference smoke: <entry>` configuration and
adds `reference_workload_mode=smoke` to its runtime identity. The aggregate read model also selects
the newest run that has complete active-case and trial coverage for each portfolio entry. A
regression test covers the newer-smoke-versus-older-complete-portfolio case.

The post-fix smoke run verified the boundary end to end:

| Field | Value |
| --- | --- |
| Run ID | `1122950f-e1a5-4f33-9acd-1d62231427f1` |
| Deployment Configuration ID | `abbfa944-512a-43d6-bf4b-936f879c3faa` |
| Results / Metrics | 10 / 10 |
| Success / error rate | 0.10 / 0.90 |
| Critical failure outcomes | 9 of 10 |
| RAG groundedness / unsupported claim rate | 0.0 / 1.0 |
| Tool execution success | 0.5 |
| Agent task success | 0.0 |
| Timeout / OOM rate | 0.0 / 0.0 |
| Artifact SHA-256 | `f7e21326bf1d26aaafe99bd57d76a4c184a43857d92b849a771f44a7a7d63c3c` |

After that run, the aggregate still selected exactly three 128-result portfolio runs, the review
queue remained 110 rows, Gate orchestration reused all three current reference Gates, and the
reference report remained bound to 384 Results. Smoke evidence is retained as honest diagnostic
history but no longer displaces portfolio evidence.

## Gate and count interpretation

All reference Gate Preflights could evaluate. The current outcomes are:

| Configuration | Gate ID | Failed blocker rules | Critical failure outcomes | Verdict |
| --- | --- | ---: | ---: | --- |
| `small-baseline` | `647347ea-40cf-494e-87b1-8531c3291fb0` | 8 | 51 | `BLOCKED` |
| `medium-candidate` | `38449033-db55-4494-bad7-dfb7aebc6dcd` | 8 | 36 | `BLOCKED` |
| `prompt-variant` | `9538a38c-05fb-4437-ba59-ef14944d582c` | 8 | 36 | `BLOCKED` |

The current small-baseline Gate includes the immutable pre-fix Phase 7 smoke evidence, so it was
re-evaluated once. A subsequent Gate run created no new Gate and reused all three current IDs.

The following counts intentionally have different scopes:

- 110 is the failure-first review queue from the exact three selected portfolio runs;
- 123 is the sum of failed critical outcomes in the three current reference Gates;
- 131 is the Overview sum across the latest Gate for every Deployment Configuration, including
  eight outcomes from one older non-reference configuration.

The Overview labels this value `Critical failure outcomes` and states its scope as
`latest Gate for every configuration`; it is not presented as a unique-case count.

## Generated artifacts

The report command atomically regenerated the final artifact set. Host-side SHA-256 calculation
matched every reported hash.

| Artifact | SHA-256 |
| --- | --- |
| `reference-workload-report.json` | `95de5d4c812d397a3f93bb9c7db4adce534635b34699cb5eb2ef068b4c1c2bba` |
| `reference-workload-report.md` | `29ca0a6dbe359d08adbb4a71ec8f7068d287f7335fb439840d32fae58714ffa6` |
| `configuration-comparison.csv` | `d617dc9a0042da3d1d4cd2322512f46436e03145da06109e9d8fbc4a2031ea82` |
| `critical-failures.json` | `b915728f853b55da3b4caaa9bd5db5261e6a028323fe4e420adff3a4ad451d61` |
| `reproduction-manifest.json` | `7ba5aea39bcb59553cce552cd6fe7311cc7fdcda1cd5b91c89044e4f0592b712` |
| `runtime-matrix-portfolio-v7.json` | `d6e717325c0202850630ba9c04ad929e13e010f1ea2335eb3b4bca7685aa3867` |
| `runtime-matrix-smoke-phase7-isolated.json` | `f7e21326bf1d26aaafe99bd57d76a4c184a43857d92b849a771f44a7a7d63c3c` |

## Verification results

| Check | Result |
| --- | --- |
| Backend full test suite | 220 passed |
| Backend Ruff | Passed |
| Frontend ESLint | Passed |
| Next.js production build and TypeScript | Passed |
| Backend and Agent worker Docker build | Passed |
| Frontend Docker build | Passed |
| Alembic current | `202608040001 (head)` |
| Compose backend health | Healthy |
| Desktop browser QA | Passed at 1280 x 720 |
| Mobile browser QA | Passed at 390 x 844 |
| Document-level horizontal overflow | None |
| Browser warnings or errors | None |

The backend suite emits one upstream Starlette TestClient deprecation warning and one container
pytest-cache permission warning. Neither changes test results or runtime behavior.

## Reproduction commands

```powershell
docker compose --profile runtime up -d ollama
docker compose run --rm backend python -m app.reference_workload.cli validate

docker compose run --rm `
  -e REFERENCE_RUNTIME_BASE_URL=http://ollama:11434 `
  -e REFERENCE_MODEL_SMALL=qwen2.5:0.5b `
  -e REFERENCE_MODEL_MEDIUM=qwen2.5:1.5b `
  backend python -m app.reference_workload.cli run `
  --mode smoke `
  --matrix /workspace/reference_workload/runtime_matrix.json `
  --output /artifacts/reference-workload/runtime-matrix-smoke.json

docker compose run --rm backend python -m app.reference_workload.cli compare-runtime `
  --input /artifacts/reference-workload/runtime-matrix-portfolio-v7.json
docker compose run --rm backend python -m app.reference_workload.cli gate
docker compose run --rm backend python -m app.reference_workload.cli report `
  --output-directory /artifacts/reference-workload
```

The complete portfolio command is the same matrix command with `--mode portfolio`. It was not
rerun in Phase 7 because the already configured 384-result persisted matrix replayed exactly from
its bound run IDs and stable comparison hash. No planned or simulated portfolio value is reported
as a new execution.

## Remaining evidence gaps

- Human-reviewed model outputs: 0 of 30 required for portfolio completion.
- Production-captured Results with verified receipts: 0.
- Applied judge labels for the selected reference evidence: 0.
- Agent task success: 0.0 for every portfolio configuration.
- RAG groundedness remains 0.0 to 0.082589 with high unsupported-claim rates.
- Every reference Gate is blocked by all eight blocker rules.
- The best observed configuration is diagnostic only; no tested configuration is a release
  candidate.

The correct conclusion is that the implementation and evidence pipeline are reviewable and
reproducible, while model quality, review coverage, release authorization, and production
readiness remain incomplete.
