# Korean Operator Assistant Reference Workload

## Purpose

`model-atlas-operator-assistant-ko` is Sprint 6A's flagship workload. It evaluates whether a local
AI configuration can answer Korean Model Atlas operator questions with grounded citations, select
bounded Tools, refuse unsupported claims, recover from one bounded Tool failure, and produce a
bounded multi-step Agent trace.

The workload uses repository-owned project documentation. It does not use customer documents,
production traffic, web-scraped content, or private operational data.

## Corpus contract

The source allowlist is `reference_workload/manifest.json`. The loader:

- accepts only POSIX-style repository-relative allowlisted paths;
- rejects absolute paths, `..`, missing files, and resolved symlink escapes;
- validates locked SHA-256 values before reading content;
- splits Markdown by heading path;
- derives chunk IDs from file path, heading path, and content hash;
- records source and chunk hashes in metadata;
- publishes a deterministic corpus hash;
- does not open a database session or use the network.

Current locked source: 14 documents and 200 Markdown section chunks.

## Case taxonomy

| Category | Cases | Critical cases |
| --- | ---: | ---: |
| `rag_single_document` | 12 | 2 |
| `rag_multi_document` | 10 | 3 |
| `rag_version_or_scope` | 6 | 3 |
| `insufficient_evidence_refusal` | 8 | 4 |
| `tool_single_step` | 10 | 2 |
| `tool_failure_recovery` | 6 | 2 |
| `rag_tool_combined` | 6 | 3 |
| `agent_multi_step` | 6 | 1 |
| **Total** | **64** | **20** |

These contracts were generated as drafts and remained inactive until assisted human review was
completed on 2026-09-01. The external review ledger now approves all 64 cases, including all 20
critical cases, without changing the immutable case bodies.

## Review provenance

An approval in `reference_workload/review_manifest.jsonl` must contain:

- the stable case ID;
- the exact SHA-256 of the case contract excluding review state;
- `approved` or `rejected` decision;
- a real reviewer identity;
- a timezone-aware review timestamp;
- review notes.

Changing any case content invalidates the review hash. Missing metadata, duplicate reviews, unknown
case IDs, and stale hashes fail validation. Codex-generated reviewer identities or timestamps are
not accepted as project evidence.

### Assisted review

`review-assist` performs deterministic contract, source, Tool, Agent, refusal, recovery, duplicate,
and risk checks for every case. It writes a hash-bound JSON report, a compact CSV, and an empty
human-attestation template. The current report classifies 38 cases for bulk review, 26 for direct
spot checking, and 0 for repair. All 20 critical cases remain in the direct spot-check set.

This automation is triage, not approval. `finalize-assisted-review` writes review decisions only
after a real reviewer completes an attestation bound to the exact report hash and confirms every
required case ID. See `docs/reference_workload_review_automation.md` for the full workflow.

## Commands

```powershell
docker compose run --rm backend python -m app.reference_workload.cli lock-manifest
docker compose run --rm backend python -m app.reference_workload.cli draft-cases --force
docker compose run --rm backend python -m app.reference_workload.cli review-worksheet
docker compose run --rm backend python -m app.reference_workload.cli review-assist
docker compose run --rm backend python -m app.reference_workload.cli finalize-assisted-review
docker compose run --rm backend python -m app.reference_workload.cli validate
docker compose run --rm backend python -m app.reference_workload.cli bootstrap
docker compose run --rm backend python -m app.reference_workload.cli gate
docker compose run --rm backend python -m app.reference_workload.cli report `
  --output-directory /artifacts/reference-workload
```

`validate` and `bootstrap` intentionally return a nonzero status while approved cases are below
the taxonomy minimum. Bootstrap checks readiness before creating a workload, suite, case, metric,
or policy row. With the recorded approval ledger, both commands now pass and repeated bootstrap
runs resolve the same workload, suite, and policy identities without duplicate rows.

The worksheet is a UTF-8 CSV for human inspection. Its decision, reviewer, reviewed-at, and notes
columns are blank by design. Filling the worksheet does not itself activate a case; approved
evidence must still be written to the hash-bound JSONL review contract.

## Acceptance policy

Once the approved case taxonomy is complete, bootstrap creates
`Model Atlas Operator Assistant Local Evaluation Policy v1` using existing metric and policy
contracts. Targets cover critical failures, JSON validity, Tool validity and execution, RAG
citations and groundedness, unsupported claims, bounded Agent completion, OOM, latency, and actual
local-runtime coverage.

The thresholds are portfolio targets, not universal standards. A local Gate may satisfy the
policy while production readiness remains `not_production_ready`.

## Current status

Implementation phases 0 through 5, assisted review, the runtime matrix, aggregate API/UI, Gate,
and report export are verified. The recorded evidence state is:

- approved source cases: 64 of 64;
- approved critical source cases: 20 of 20;
- review report SHA-256:
  `4e3c3eb261005c6dafaf7b675e3e4698f54fc0074a3823e9338a3fda2a1774b0`;
- review recorded at: `2026-09-01T08:43:24+00:00`;
- workload ID: `f353d107-5257-46dc-8213-1becd92a3d64`;
- evaluation suite ID: `d2649432-15ee-436d-a733-a36906fb4aec`;
- acceptance policy ID: `8405ca90-8558-4c57-a8b4-306235d663d2`;
- actual-runtime evidence: 3 completed configurations, 384 results, and 2 model artifacts;
- runtime-matrix portfolio evidence status: `ready`;
- critical-failure review queue: 110 selected failures with Run and Judge links;
- model-output review: 0 reviewed of the target of 30;
- Gate outcomes: 3 of 3 configurations, aggregate verdict `BLOCKED`;
- evidence trust: `needs_judge_review`;
- release readiness: `BLOCKED`;
- broader Sprint 6A portfolio status: 7 of 8 checks passed, incomplete pending model-output
  review, bounded modularization, and final verification;
- production readiness: `not_production_ready`.

See `docs/reference_workload_runtime_matrix.md` for the runtime identity and execution contract,
and `docs/reference_workload_aggregate_ui.md` for the read model, API, and guided review flow.
See `docs/reference_workload_gate_reporting.md` for Gate orchestration, report contracts, artifact
hashes, and the current decision outcome.
Source-case approval does not constitute model-output review, Gate approval, release authorization,
or production evidence.
