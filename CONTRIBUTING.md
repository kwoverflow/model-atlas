# Maintaining Model Atlas

Read [MVP_REVIEW_GUIDE_KO.md](MVP_REVIEW_GUIDE_KO.md) for the product, demo, and limits.
This repository is an EvalOps portfolio MVP, not a trained model or a production approval.

## Local Development

Use Python 3.12+ and Node 22. From the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ./backend
```

From `backend`, run `../.venv/Scripts/python.exe -m pytest` and
`../.venv/Scripts/python.exe -m ruff check app tests`.
On Linux/macOS use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.
From `frontend`, run `npm ci`, `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`.
From the root, run `python -m unittest discover -s tools/tests -v`.
The GitHub Actions workflow repeats these checks and audits the published source payload.

Use `deploy/mvp-review.compose.yml` for the isolated mock demo. Seed only a new review DB,
once, as described in the review guide. Do not seed, rebuild, or migrate a preserved real
evaluation environment merely to run these tests. The smoke helper adds synthetic records;
it is not a read-only health check.

## Ownership and Extension Points

| Change | Start here | Contract to preserve |
| --- | --- | --- |
| Runtime integration | `backend/app/services/inference_adapters` | Adapter result, raw output, errors, provenance |
| RAG orchestration | `backend/app/services/rag_pipeline/execution.py` | Expected labels must not reach generation |
| Retrieval | `rag_pipeline/retrieval.py`, `rag_pipeline/contracts.py` | Trace schema, stable ordering, corpus identity |
| Output scoring | `rag_pipeline/scoring.py`, `rag_pipeline/text.py` | Versioned thresholds, semantic and evidence contracts |
| RAG aggregation | `rag_pipeline/summaries.py` | Missing evidence differs from a zero score |
| Gate policy | `backend/app/services/deployment_gate` | Evidence collection separate from policy decisions |
| Release review | `release_readiness.py`, `release_decisions.py` | Role checks, immutable snapshot, drift detection |
| API or DB | `backend/app/schemas`, `backend/app/api/v1/routes`, `backend/alembic` | Explicit validation and migrations |
| UI | `frontend/app`, `frontend/components`, `frontend/lib` | Existing API contracts, responsive states |

Paths abbreviated as `rag_pipeline/...` are under `backend/app/services`.
`rag_evaluation.py` remains the compatibility facade. Existing callers need not change.
Pipeline modules depend on focused modules, never on that facade. Do not add business
logic to the facade. Dataclasses now have a different Python `__module__`; JSON contracts
are preserved, but historical Python pickle compatibility is not promised.

The RAG dependency direction is:

```text
contracts + text
  -> corpus / retrieval
  -> scoring
  -> execution
summaries -> contracts
rag_evaluation facade -> the modules above
```

Use the existing Adapter/Factory and service-layer patterns. Add a new abstraction only
when multiple implementations need it. Research retrievers belong in the optional
experiment path until an independently specified adoption gate passes; do not silently
replace the official retriever or weaken thresholds to make a case pass.

## Regression and Evidence Rules

- `backend/tests/test_rag_pipeline_contract.py` checks pre-refactor output fingerprints,
  facade identity, and acyclic imports. Do not refresh fingerprints just to silence a failure.
- Add focused tests for changed behavior and run the full backend suite for shared contracts.
- Changing a score, contract, or corpus is not a cosmetic refactor. Version it and record
  before/after results with a decision explaining compatibility and intended differences.
- Approved source documents and `reference_workload/revisions` bind exact file bytes.
  `.gitattributes` disables Git newline conversion. Do not run a repository-wide formatter.
- Source-case approval is not human review of model outputs. Mock evidence is not real inference.
- Preserve `BLOCKED` and `not_production_ready` until the applicable evidence genuinely changes.

## Public Review Packages

Only project sources and explicitly selected review receipts belong in Git. Historical
generated artifacts are included in the reviewed release ZIP, not indiscriminately committed.
Never force-add the entire `artifacts` directory. Never publish local environments, model
weights, DBs, credentials, logs, or old ZIPs. The intended delivery is software and evidence;
third-party model weights must be obtained separately under their own terms.

Stage the intended files, then scan the exact staged blobs:

```powershell
python tools/audit_publication.py --git-index .
powershell -NoProfile -File tools/build_evaluation_package.ps1 -VerificationPath artifacts/public-review/2026-09-13/verification.json
python tools/audit_publication.py --archive path/to/new-package.zip
python tools/verify_mvp_package.py path/to/new-package.zip --extract-to path/to/new-directory
```

The verification path above identifies this checkpoint. For a later release, create a new
dated verification receipt from that release's actual test results and pass its path instead.
Scan a final ZIP again after any rebuild. Checksums establish integrity, not publisher identity.
The built-in scanner only covers high-confidence patterns; inspect public payloads manually too.
No open-source license has been selected. Public visibility is not a grant of reuse rights.
