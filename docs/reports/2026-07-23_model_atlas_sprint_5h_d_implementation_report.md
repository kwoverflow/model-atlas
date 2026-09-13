# Model Atlas Sprint 5H-D Implementation Report

Date: 2026-07-23

## Executive Summary

Sprint 5H-D closes the manual freshness gap in the managed trust plane. Remote JWKS Apply can now
run automatically from a governed per-source policy while preserving the security and evidence
boundaries built in Sprints 5H-A through 5H-C.

The implementation reuses the existing PostgreSQL durable-job worker rather than introducing a
parallel scheduler stack. Multiple workers safely scan due policies with `FOR UPDATE SKIP LOCKED`;
one transaction creates one run-sequenced job and schedule lease. The claimed job uses the existing
heartbeat lease, retry, lease recovery, and dead-letter behavior. Every attempt, including each
transient failure, creates an append-only trust-source sync receipt.

## Problem Addressed

Before this sprint, a remote source could become stale even when the service was healthy because a
governance operator had to remember to press Apply. That created four operating problems:

- freshness depended on human timing;
- multiple future worker replicas had no safe ownership protocol for due work;
- retry behavior was not policy-controlled at the source boundary;
- manual and automated evidence could not be distinguished in the attempt ledger.

Sprint 5H-D adds automation without weakening source registration, transport allowlisting, key
validation, root lifecycle, or release authorization.

## Delivered Scope

### Persistence

- Added one policy row per trust source with interval, jitter, retry, next-run, and identity state.
- Added schedule lease owner/fingerprint/expiry, monotonic run sequence, and failure counters.
- Added manual/scheduled trigger, schedule ID, job ID, attempt, and scheduled-for lineage to sync
  receipts.
- Extended the durable-job type constraint with `trust_source_sync`.
- Added Alembic revision `202607230001` on top of Sprint 5H-C.

### Execution

- Added horizontally safe due scans using PostgreSQL row locks and `SKIP LOCKED`.
- Added one-transaction schedule lease plus durable-job enqueue.
- Reused job claim, heartbeat, expired-lease recovery, and dead-letter operations.
- Added policy-controlled exponential retry with deterministic jitter.
- Classified network/HTTP/database-conflict failures as retryable and content/policy failures as
  terminal.
- Preserved at-least-once safety through idempotent Apply and append-only receipts.

### API And UX

- Added list/upsert/Run-now schedule APIs.
- Upgraded Trust Registry overview to v3 with automation counts.
- Added policy status, next run, and configuration controls to each source.
- Added authenticated Run now and client-side policy-bound validation.
- Added trigger, attempt, and linked job evidence to Sync History.
- Added `trust_source_sync` labels to Agent Jobs.

### Operations

- Added enabled, due, retrying, and failed schedule gauges.
- Added retrying warning and exhausted-retry critical alerts.
- Passed identical trust-source transport and scheduler settings to worker containers.
- Documented recovery, compatibility, and non-claims.

## Key Design Decisions

1. **Separate immutable source configuration from mutable automation policy.** Source provenance
   remains stable while operations can tune intervals and retries.
2. **Reuse the durable job queue.** Schedule ownership and execution ownership have separate,
   explicit leases without duplicating worker infrastructure.
3. **Keep the sync ledger authoritative.** Job state explains delivery; sync receipts explain trust
   evidence. Neither substitutes for the other.
4. **Use deterministic jitter.** Tests and incident review can reproduce timing while replicas do
   not synchronize every source on the exact interval boundary.
5. **Never treat automation as trust.** Automatic Apply executes the same allowlist, transport,
   public-JWK, freshness, and lifecycle rules as manual Apply.
6. **Discard the schedule lease nonce.** Only its SHA-256 fingerprint is persisted; the existing
   non-exported job lease token remains the execution authorization boundary.

## Verification Evidence

### Automated

- Backend pytest: `172 passed`, one upstream Starlette TestClient deprecation warning.
- Backend Ruff: passed.
- Frontend typecheck: passed.
- Frontend ESLint: passed.
- Frontend production build: passed.
- New tests cover one-run enqueue, success lineage, transient retry, per-attempt receipts, retry
  exhaustion, dead letter, metrics, and alerts.

### PostgreSQL And Docker

- Migration: `202607230001 (head)`.
- Containers: database and backend healthy; frontend and JWKS fixture running.
- Worker replicas online: 2.
- Controlled source: `ebd9e582-78d7-4e39-8a57-0de2248eae56`.
- Controlled policy: `a61be9e2-0f93-4b66-b0cf-e5ecd467fbde`.
- First due window under two workers: run sequence 1, durable jobs 1, scheduled receipts 1.
- First job: `c5ab1ad2-0bef-4b01-a57d-4f514622ac36`, completed on attempt 1.
- Result: one observed key, zero duplicate imports, one unchanged key, lease cleared, next run set.
- Schedule metrics after completion: enabled 1, due 0, retrying 0, failed 0.
- Final rebuilt-image Run now: run sequence 7, job
  `9838b5cd-dec7-4fa6-9ee4-debf9ba03e9f`, completed on attempt 1.
- Final receipt: `0b8cdae9-5125-4c20-b694-602fd16fad38`, with scheduled trigger and complete
  schedule/job/attempt lineage.
- Persisted job payload contained `schedule_lease_token_hash` with 64 hexadecimal characters and
  did not contain a raw `schedule_lease_token` field.
- Final service state: backend and database healthy, two scheduling-enabled Agent workers online,
  schedule lease cleared, and migration `202607230001 (head)`.

### Browser

- Local Keycloak PKCE login normalized `evaluator` to `ML Ops Lead`.
- The automation editor showed the persisted policy and enabled governance controls.
- A jitter equal to the interval disabled Save; restoring a valid value re-enabled it.
- Authenticated Run now passed Origin/CSRF enforcement and created run sequence 3.
- Resulting scheduled receipt: `b9e50633-a7cb-4963-9f30-5f39553fd447`.
- Linked job: `f0ccfe6d-da17-40b6-bd8e-26fd9feae26c`, succeeded.
- Mobile `390 x 844`: editor width 343px, input width 301px, no horizontal overflow.
- Final browser console warnings/errors: 0.

## Compatibility

- Source registration and manual Preview/Apply paths remain available.
- Existing sync rows receive migration defaults of `trigger=manual` and `attempt_number=1`.
- Existing durable job types and requeue operations are unchanged.
- No trust tier, production threshold, Gate, release decision, or evidence score contract changed.
- The migration is additive except for widening existing check constraints.

## Deliberate Non-Claims

- The development HTTP fixture is not external publisher or internal CA identity.
- PostgreSQL locking is not multi-region consensus or a general workflow engine.
- At-least-once execution can create more than one receipt after crash recovery; it cannot create a
  duplicate trust root for unchanged key material.
- No cron calendar, mTLS, OCI registry verification, timestamp authority, or external revocation
  distribution is implemented.
- No durable time-series SLO store or tested external paging destination is included.
- Model production readiness and release authorization remain false without representative target
  hardware, trusted production captures, and production-tier signed provenance.

## Recommended Next Work

1. Browser-session retention cleanup and subject/provider-session administration.
2. Durable time-series SLOs, owned paging delivery, and delivery-path tests.
3. Staging internal-CA or external publisher integration over TLS.
4. Target 7B representative GPU validation and reviewed signed production captures.
5. Per-job OS or Kubernetes isolation with enforced egress and resource policy.
