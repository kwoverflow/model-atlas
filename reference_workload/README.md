# Model Atlas Korean Operator Assistant Reference Workload

This directory is the versioned source contract for Sprint 6A's flagship workload.

- `manifest.json` allowlists repository-owned Markdown files and locks their SHA-256 values.
- `cases.jsonl` contains the immutable generated case contracts reviewed through the external ledger.
- `review_manifest.jsonl` records explicit human decisions bound to immutable case hashes.
- `review_assistance.json` contains detailed machine checks and source excerpts.
- `review_assistance.csv` is the compact, filterable triage view.
- `review_assistance.html` is a standalone guided review screen with local progress tracking.
- `review_attestation.json` contains the completed report-bound human batch attestation used to
  create the approval ledger.
- `runtime_matrix.example.json` documents environment-driven local runtime configurations.
- `runtime_matrix.json` is the bounded 256-token Portfolio execution matrix.

The source documents are project documentation intended for this local portfolio submission. They
are not production customer documents or production traffic.

Draft cases are never active evidence. A reviewer must inspect the source document and case ground
truth, then provide reviewer identity, notes, and the exact report-bound case confirmations. The
finalizer records the approval event time in UTC and writes hash-bound decisions. The bootstrap
command fails before database writes when the approved-case minimum is not met.

Run `python -m app.reference_workload.cli review-assist` to regenerate the machine review. It does
not approve cases. After a person inspects every required spot-check case and completes the
hash-bound attestation, `finalize-assisted-review` can create the review manifest in one audited
batch. The command records an actual approval event; it rejects blank or machine-like reviewers,
missing case confirmations, stale reports, modified reports, and any repair-required case.

Do not place API keys, model weights, runtime tokens, or private keys in this directory.

Current recorded state: all 64 cases, including all 20 critical cases, were approved through the
assisted-review contract on 2026-09-01. The idempotent bootstrap readiness gate passes. This is
source-case approval only; it is not output review, Gate approval, release authorization, or
production readiness.

## Actual Runtime Matrix

The matrix resolves endpoint and model names from environment variables, observes the model in the
runtime registry, and requires a real SHA-256 digest before creating evidence. It then resolves
idempotent Model, Model Artifact, Hardware Profile, Prompt Version, and Deployment Configuration
records and delegates inference to the existing OpenAI-compatible benchmark execution service.

Smoke mode selects up to ten category-stratified cases and executes the first available
configuration once. Portfolio mode requires at least 60 active cases, three enabled
configurations, and two trials per case. Missing endpoints, models, and digests remain explicit
`unavailable` entries; no fixture result is substituted.

```powershell
docker compose --profile runtime up -d ollama
docker compose exec ollama ollama pull qwen2.5:0.5b
docker compose exec ollama ollama pull qwen2.5:1.5b

$env:REFERENCE_MODEL_SMALL = "qwen2.5:0.5b"
$env:REFERENCE_MODEL_MEDIUM = "qwen2.5:1.5b"
make reference-smoke
make reference-run
make reference-compare
```

Generated matrix results are local actual-runtime evidence under
`artifacts/reference-workload/`. They are not production-captured evidence and never make
production readiness true by themselves.
