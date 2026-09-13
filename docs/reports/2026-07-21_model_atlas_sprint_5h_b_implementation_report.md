# Model Atlas Sprint 5H-B Implementation Report

Date: 2026-07-21

## Decision Summary

Sprint 5H-B replaces manually copied remote signing keys with a governed, auditable JWKS
synchronization path. It introduces allowlisted remote trust sources, strict fetch policy,
non-mutating Preview, atomic Apply, source-to-root lineage, freshness-aware fail-closed
eligibility, operational metrics, and an operator console.

The result is a stronger integration contract, not a production trust claim. The live evidence
uses a Compose-hosted development HTTP fixture. No external publisher or internal CA endorsement
was fabricated, and the imported key remains outside production eligibility.

## Problem Closed

Sprint 5H-A could answer whether a registered public key was active and governed, but an operator
still had to transfer that key into Model Atlas manually. That created four gaps:

1. the registry could not prove which remote snapshot supplied a key;
2. key rotation required manual registration and comparison;
3. stale or unreachable sources did not automatically affect source-backed eligibility;
4. operators lacked Preview, Apply, failure history, and source health signals.

Sprint 5H-B closes those gaps while preserving existing manually registered roots.

## Implemented Scope

1. Versioned remote JWKS source configurations with verified registrar provenance.
2. HTTPS-by-default, host-allowlisted, redirect-free, bounded network fetches.
3. Public-key-only JWKS validation with exact algorithm and key-ID policy.
4. Append-only Preview and Apply receipts, including failed attempts.
5. Atomic Apply with no partial import on malformed keys or collisions.
6. Immutable source and sync lineage on imported trust roots.
7. Snapshot-aware remote rotation and `source_key_current` evaluation.
8. `healthy`, `degraded`, `stale`, `failed`, `unsynced`, and `disabled` states.
9. Freshness-aware production eligibility and fail-closed stale behavior.
10. Source metrics/alerts plus Trust Registry source management and history UI.
11. Development-only Compose JWKS service and `make trust-source-up` workflow.

## Data And API Changes

Alembic revision `202607210001` adds:

- `evidence_trust_sources`;
- `evidence_trust_source_syncs`;
- nullable source and sync lineage on `evidence_trust_roots`;
- indexes and foreign keys for source, status, mode, and time-oriented reads.

New APIs:

- `GET|POST /api/v1/trust-registry/sources`;
- `POST /api/v1/trust-registry/sources/{id}/sync`;
- `GET /api/v1/trust-registry/source-syncs`.

Trust Registry overview advances additively to
`model-atlas-trust-registry-overview-v2`. Existing root and proof endpoints are preserved.

## Security And Failure Semantics

- URL credentials, query strings, fragments, redirects, disallowed hosts, oversized responses,
  and non-JSON/JWKS content types are rejected.
- Application defaults require HTTPS. HTTP needs both source-level and server-level development
  approval, and only a development-tier source can use it.
- Private RSA/EC/OKP fields and symmetric keys are rejected.
- Preview never mutates roots.
- Apply either imports the complete validated candidate set or none of it.
- A newer failed attempt reports `degraded` while the prior Apply is fresh; it becomes fail-closed
  when that snapshot is stale.
- A key missing from the latest Apply snapshot remains auditable but is no longer current.
- Manual roots are not silently converted to source-backed roots.

## Actual Compose Evidence

| Evidence | Result |
| --- | --- |
| Migration | `202607200005 -> 202607210001` applied transactionally |
| Fixture fetches | two HTTP 200 requests from backend Compose network |
| Trust source | `ebd9e582-78d7-4e39-8a57-0de2248eae56` |
| Preview | succeeded; 1 candidate; 0 imported |
| Apply | succeeded; 1 imported; 0 unchanged; 0 rejected |
| Imported root | `095ed9e0-b171-4c1f-8f44-4f0498f2c7e1` |
| Source/root state | `healthy`; `source_key_current=true` |
| Source metrics | registered 1; healthy 1; degraded/stale/failed/unsynced 0 |
| Source alerts | 0 |
| Production eligibility | false, by development-tier policy |

## Verification

- Backend full Docker suite: `166 passed, 1 warning`.
- Backend Ruff: passed.
- Frontend TypeScript: passed.
- Frontend ESLint: passed.
- Next.js production Docker build: passed.
- Live PostgreSQL migration and Compose Preview/Apply: passed.
- Live API lineage, freshness status, root currency, metrics, and zero-alert checks: passed.
- Desktop Trust Registry and Operations QA: passed with live source, sync, lineage, and metrics.
- `390 x 844` Trust Registry QA: passed; document overflow absent, four table scroll regions
  contained locally, and form-control overflow count zero.
- Trust source, root, and transparency form mode switching: passed.
- Final browser console: zero warnings or errors.

The warning is the existing upstream Starlette TestClient deprecation warning.

## Deliberate Non-Claims

- A local JWKS endpoint is not external publisher identity.
- Fetching a public key does not prove key custody or CA policy.
- Development HTTP is not an acceptable production transport.
- A healthy source does not make a development-tier root production eligible.
- This sprint does not provide automatic scheduled sync, mTLS, OCI signature verification,
  independent transparency logging, or online certificate revocation.
- Model Validation remains separate from Deployment Gate and release authorization.

## Recommended Next Work

1. Shared browser sessions, provider logout, CSRF/proxy review, and distributed OIDC JWKS cache.
2. Scheduled trust-source synchronization with a distributed lease and retry policy.
3. Staging internal-CA or external publisher integration over HTTPS.
4. Durable SLO retention and tested owned paging delivery.
5. Signed staging collector deployment and reviewed production captures.
6. Per-job OS or Kubernetes sandbox enforcement.
