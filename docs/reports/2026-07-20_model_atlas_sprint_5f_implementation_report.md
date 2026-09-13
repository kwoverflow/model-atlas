# Model Atlas Sprint 5F Implementation Report

Date: 2026-07-20

## Executive Summary

Sprint 5F closes six production-shape gaps left after Sprint 5E: runtime artifact identity,
reviewed score provenance, browser identity, exported operations monitoring, Tool/RAG isolation,
and a target-matching local validation record.

Model Atlas can now observe a runtime manifest server-side, bind its SHA-256 digest to an immutable
deployment configuration, execute that configuration through the durable worker, apply
append-only verified human review decisions, and report a locally validated result without
claiming release or production authorization.

## Problem Addressed

Hardware-fit and token-based model recommenders can identify candidates likely to run. They do not
prove which artifact actually ran, whether labels were reviewed by an accountable operator, who
authorized browser actions, whether the control plane is operationally healthy, or whether Tool
and RAG evaluation stayed inside a defined security boundary. Sprint 5F adds those controls while
preserving Candidate Discovery, Deployment Gate, Release Readiness, and signed Release Decisions
as separate layers.

## Implemented Work

1. Added server-observed Ollama manifests, SHA-256 artifact attestations, SSRF bounds, actor
   provenance, idempotent records, and digest-pinned deployment configurations.
2. Added append-only judge review decisions for candidate approval, override, and rejection with
   RBAC, separation of duties, prior/applied score snapshots, rationale, and stable hashes.
3. Added browser OIDC Authorization Code + PKCE, state and nonce checks, RS256 ID-token validation,
   short-lived HttpOnly app sessions, UI identity controls, and a Keycloak development profile.
4. Added JSON and Prometheus metrics, derived alerts, an Operations page, Prometheus/Alertmanager
   configuration, and a bounded local alert sink.
5. Added versioned Tool/RAG isolation policies, fail-closed execution preflight, audit persistence,
   isolation UI, and hardened Docker examples.
6. Added a matching `qwen2.5:0.5b` configuration and completed a real five-case Ollama campaign.
7. Fixed the pre-existing traffic-receipt migration timestamp mismatch discovered by PostgreSQL
   observability verification.
8. Fixed Model Validation select overflow and UTC hydration consistency found during desktop and
   mobile browser QA.

## Database Revisions

| Revision | Change |
| --- | --- |
| `202607200001` | Model artifact attestations |
| `202607200002` | Judge label review decisions |
| `202607200003` | Traffic receipt timestamp schema alignment |

All migrations are additive. The verified Docker database is at `202607200003 (head)`.

## Verified Runtime Evidence

| Field | Value |
| --- | --- |
| Model | `qwen2.5:0.5b` |
| Digest | `sha256:a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67` |
| Configuration | `c3dd6a74-1772-4e50-9d86-49273cebb502` |
| Attestation | `ffb3c1bb-4ac1-49bc-a50f-940d28ce6c47` |
| Benchmark run | `161d4ee8-498a-41b0-882b-ae1360a99091` |
| Durable job | `7d75b87f-58c9-4806-bb74-20f4630407bc` |
| Results / metrics | 5 / 5 |
| Model and digest match | true / verified |
| JSON validity | 100% |
| Error / OOM rate | 0% / 0% |
| P50 / P95 latency | 1,992.097 ms / 2,886.165 ms |
| P50 throughput | 70.63 tokens/s |
| Human-reviewed coverage | 2 of 5, including 1 critical case |
| Validation status | `validated` |
| Release authorized | false |
| Production readiness | `not_production_ready` |

The quality values in this five-case local sample are not a general model benchmark. Two outputs
were manually reviewed for schema and factual consistency; three remain heuristic. Production
captured evidence, broader coverage, target hardware telemetry, and policy evaluation are still
required before a release claim.

## Verification

```text
Host backend pytest: 161 passed, 1 upstream warning
Docker backend pytest: 161 passed, 1 upstream warning
Backend Ruff: passed
Frontend typecheck: passed
Frontend lint: passed
Frontend production build: passed
Frontend Docker lint: passed
Compose runtime/IdP/observability config: passed
Isolation Compose config: passed
Prometheus endpoint: HTTP 200
Desktop and 390px mobile browser QA: passed
Browser console after final build: no warnings or errors
```

The remaining warning is Starlette TestClient's upstream `httpx` deprecation notice.

## Honest Boundary

- `validated` means the selected local runtime artifact and reviewed local evidence cleared Model
  Validation checks. It is not a Gate verdict or release decision.
- The attestation is a verified server observation, not a publisher signature or SBOM attestation.
- Browser sessions are process-local signed cookies; horizontal deployment needs shared session
  and revocation design.
- Prometheus and Alertmanager examples are local deployment assets; the reference sink is not a
  production paging service.
- Isolation preflight is integrated, while per-run OS sandbox orchestration remains future work.
- The current run is 0.5B local-authored evidence, not the originally described 7B target or a
  production traffic validation set.

## Recommended Sprint 5G

1. Run the target 7B artifact on representative GPU hardware and expand reviewed critical cases.
2. Add signed registry/SBOM provenance and attestation revocation.
3. Add shared browser sessions, provider logout, CSRF/proxy hardening, and horizontal JWKS cache.
4. Deploy durable metrics retention, owned paging routes, SLO dashboards, and alert delivery tests.
5. Execute Tool/RAG runs in per-job OS or Kubernetes sandboxes with resource and egress policy.
6. Replace the reference traffic path with a durable streaming/event platform where scale needs it.

