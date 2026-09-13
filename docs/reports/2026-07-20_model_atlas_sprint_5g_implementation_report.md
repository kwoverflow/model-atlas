# Model Atlas Sprint 5G Implementation Report

Date: 2026-07-20

## Decision Summary

Sprint 5G closes the local supply-chain trust gap without claiming external production proof. Model
Atlas now verifies publisher-signed in-toto-style JWS statements, binds CycloneDX SBOMs to the
observed model digest, preserves append-only revocations, and requires signed receipts before a
production-labeled run contributes to production evidence thresholds.

The current `qwen2.5:0.5b` artifact has a verified development-key supply-chain statement. It still
has no production-captured run, so release authorization and production readiness remain false.

## Implemented Scope

1. Fail-closed JWS verification against configured JWKS, issuer, algorithm, `kid`, `iat`, and `jti`.
2. Signed model subject, runtime attestation hash, manifest hash, and CycloneDX SBOM binding.
3. Immutable supply-chain attestation plus separated append-only revocation action.
4. Signed production-capture receipts with replay protection and exact DB count validation.
5. Evidence Trust downgrade for unsigned `production_captured` labels.
6. Model Validation report v3 supply-chain and capture status.
7. Prometheus metrics and alerts for supply-chain and production receipt state.
8. Supply Chain UI for evidence import, inspection, and role-scoped revocation.
9. Operational review semantics that exclude historical non-approval decisions from critical
   release alerts.

## Data And API Changes

Alembic `202607200004` adds:

- `model_supply_chain_attestations`;
- `model_supply_chain_attestation_actions`;
- `production_evidence_receipts`.

New API ownership is under `/api/v1/supply-chain`. Existing routes and records remain compatible.
The model validation schema advances from `model-validation-report-v2` to v3 with additive fields.

## Actual Evidence

| Evidence | Value |
| --- | --- |
| Runtime attestation | `ffb3c1bb-4ac1-49bc-a50f-940d28ce6c47` |
| Supply-chain attestation | `4b8c6826-04e1-4d06-872f-90be73e5dda4` |
| Supply-chain attestation hash | `2101fcd10e711d9e099b99a8efbb3c1737af00e953bbf4fa3ba198b2c3625e1d` |
| Artifact digest | `sha256:a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67` |
| SBOM | CycloneDX 1.6 |
| SBOM digest | `1b0317ce490d00add3b378827abfd8559b77df305b68b42bf49d2ada6047c20a` |
| Publisher key | development RS256, `model-atlas-demo-2026` |
| Production receipt count | `0` |

The refreshed Model Validation report returns:

- `status=validated`;
- `artifact_attestation_status=verified`;
- `supply_chain_status=verified`;
- `production_capture_status=not_applicable`;
- `release_authorized=false`;
- `production_readiness=not_production_ready`.

## Operational Debt Closure

Three historical `REQUEST_CHANGES` records previously appeared as critical release-review work only
because their source Gate became stale. Operational status now reserves stale-review escalation for
approved releases or explicit unresolved review requests. The critical release-review count changed
from 3 to 0.

Six stale Gates belonged to two scopes. Current evidence was reevaluated:

- `79f809f7-321a-4a12-9aa6-72b789a02ca0`: `APPROVED` for captured local evidence;
- `12eb5552-23d7-4afe-bdea-676db76069c0`: `INSUFFICIENT_EVIDENCE` for the synthetic scope.

The old Gates remain immutable and point to their replacements. Operational stale metrics count
only stale Gates without a replacement, while retaining a separate historical total.

## Verification

- Host backend unit/integration suite: `163 passed, 1 warning`, including signed evidence success,
  replay rejection, revocation, separation-of-duties, and production receipt cases.
- Docker backend unit/integration suite: `163 passed, 1 warning`.
- Ruff, frontend typecheck, frontend lint, and frontend production build: passed on the host.
- Frontend lint and production image build: passed in Docker.
- Docker Compose configuration, image rebuild, and service recreation: passed; backend, database,
  and Ollama reported healthy after recreation.
- Alembic in Docker: `202607200004 (head)`.
- Actual RS256 JWS, CycloneDX hash, runtime digest, and operator identity: verified through API.
- Runtime API state: one active verified supply-chain attestation, zero revocations, zero production
  receipts, zero unverified production runs, zero unresolved stale Gates, and no active alerts.
- Desktop and 390 x 844 mobile browser QA: passed for Supply Chain, Model Validation, and Operations;
  no document overflow, incoherent overlap, or browser console warnings/errors were observed.
- The single test warning is an upstream Starlette `TestClient` deprecation warning and does not
  indicate an application failure.

## Deliberate Non-Claims

- The development signing key is not an external publisher endorsement.
- No production receipt was fabricated for the local-authored Ollama run.
- A verified SBOM does not imply vulnerability-free dependencies.
- A validated model report is not a Deployment Gate, release decision, or production approval.
- Target 7B GPU execution and Kubernetes per-job sandboxing were not possible without the relevant
  external hardware and cluster.

## Recommended Next Work

1. Obtain an external publisher or internal CA-backed registry signature.
2. Capture at least 20 reviewed production results through a configured collector and receipt JWS.
3. Add transparency-log or OCI registry verification and key revocation distribution.
4. Run the target 7B artifact on representative GPU hardware.
5. Move browser sessions, JWKS caches, metrics retention, and paging delivery to shared durable
   infrastructure.
