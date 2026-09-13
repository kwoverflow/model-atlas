# Model Atlas Sprint 5H-A Implementation Report

Date: 2026-07-20

## Decision Summary

Sprint 5H-A closes the gap between a mathematically valid local signature and a governed
production trust chain. It adds a purpose-scoped signing-key registry, append-only key lifecycle,
signed transparency checkpoints, Merkle inclusion verification, and dynamic production
eligibility.

The current model remains deliberately not production ready. Its key and transparency proof are
development-scoped; no external publisher, internal production CA, or signed production receipt
was fabricated.

## Implemented Scope

1. Public-JWK-only trust root registration for publisher, collector, and transparency purposes.
2. `development`, `internal_ca`, and `external` trust tiers.
3. Validity windows, idempotent registration, and explicit predecessor-based rotation.
4. Append-only `rotated`, `retired`, and `revoked` lifecycle events.
5. Registrar/revoker separation of duties.
6. Signed checkpoint verification with exact issuer, key, algorithm, `iat`, and `jti` policy.
7. RFC 6962-style Merkle leaf, node, and inclusion-root verification.
8. Dynamic supply-chain and production-receipt eligibility after key state changes.
9. Model Validation report v4, Trust Registry UI, Supply Chain UI, and operational metrics.
10. Development bundle generation for reproducible local evidence.

## Data And API Changes

Alembic `202607200005` adds:

- `evidence_trust_roots`;
- `evidence_trust_root_actions`;
- `supply_chain_transparency_proofs`;
- nullable managed publisher and collector trust-root references;
- immutable trust-tier snapshots on attestation and receipt records.

New API ownership is under `/api/v1/trust-registry`. Existing Supply Chain routes remain
compatible, with additive assurance and eligibility fields.

## Security Properties

- Symmetric or private JWK material is rejected.
- A key registered for one purpose cannot verify another evidence class.
- Inactive, expired, retired, or revoked keys fail managed verification.
- Static JWKS evidence is development-scoped and cannot establish production eligibility.
- Transparency proof IDs and log positions are replay protected.
- A valid checkpoint signature alone is insufficient without a matching Merkle path.
- Existing receipts lose trusted-production status when a required key is retired or revoked.

## Actual Evidence

The actual `qwen2.5:0.5b` supply-chain attestation was reconciled to a development publisher root
and received a valid development transparency proof.

| Evidence | Identifier | Result |
| --- | --- | --- |
| Publisher root | `dfcd3aef-1d73-4aa3-8963-52e24fc09863` | active, development |
| Collector root | `830f775f-d6c6-4d43-9624-ed9786362408` | active, development |
| Transparency root | `c92b14f2-1912-40cd-861a-e8cf14bb7453` | active, development |
| Supply-chain attestation | `4b8c6826-04e1-4d06-872f-90be73e5dda4` | managed, not production eligible |
| Transparency proof | `a16fc052-27e5-42b4-b875-1126d7e7bec1` | signature and Merkle proof valid |
| Production receipts | `0` | none fabricated |

Live API state after registration:

- active roots: 3;
- production-eligible roots: 0;
- transparency proofs: 1;
- production-eligible proofs: 0;
- managed attestations: 1;
- production-eligible attestations: 0;
- operational health: healthy, with zero active alerts.

Model Validation v4 reports `validated`, `development` publisher trust, `development`
transparency, `supply_chain_production_eligible=false`, and `release_authorized=false`.

## Verification

- Focused supply-chain, validation, and metrics tests: `7 passed, 1 warning`.
- Full Docker backend suite: `164 passed, 1 warning`.
- Frontend typecheck, lint, and production build: passed.
- Docker migration: `202607200005 (head)`.
- Actual development roots and transparency proof: verified through live APIs.
- Desktop browser QA passed for Trust Registry, Supply Chain, Model Validation, and Operations.
- Trust Registry root and transparency-proof forms passed at `390 x 844`; document width remained
  equal to viewport width while both evidence tables retained scoped horizontal scrolling.
- Final browser console: zero warnings or errors.

The responsive QA found and fixed one intrinsic-width regression caused by the long superseded-key
option. Form grids and controls now shrink within their mobile parent without clipping text or
moving table overflow onto the document.

The warning is the existing upstream Starlette `TestClient` deprecation warning.

## Deliberate Non-Claims

- The development key is not external publisher endorsement.
- A local signed checkpoint is not an independent public transparency log.
- An SBOM and inclusion proof do not establish vulnerability-free dependencies.
- A validated model report is not a Gate approval or release authorization.
- No target 7B GPU run or production traffic capture was available.

## Recommended Sprint 5H-B

1. Integrate an internal CA or external publisher/OCI registry adapter.
2. Add shared browser sessions, provider logout, and horizontally shared JWKS caching.
3. Persist SLO time series and test owned paging delivery.
4. Deploy the signed collector to staging and capture at least 20 reviewed results.
5. Add Kubernetes per-job sandbox orchestration and enforced egress/resource policies.
