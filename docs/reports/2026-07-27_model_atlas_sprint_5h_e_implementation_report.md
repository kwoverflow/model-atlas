# Model Atlas Sprint 5H-E Implementation Report

Date: 2026-07-27

## Executive Summary

Sprint 5H-E closes the operating-lifecycle gap left after shared browser sessions were introduced
in Sprint 5H-C. Model Atlas can now audit, correlate, revoke, minimize, retain, and delete browser
session state through verified-role controls while preserving an append-only lifecycle ledger.

The implementation reuses the existing durable Agent worker for periodic cleanup. Multiple worker
replicas can observe the same interval bucket; the database job dedupe key creates one cleanup job.
Inactive provider ID-token ciphertext is removed immediately on revocation or by the next cleanup,
while session rows follow a configurable retention window and lifecycle events survive row
deletion.

This sprint improves control-plane identity operations. It does not change model quality,
Evidence Trust, Deployment Gate, production readiness, or release authorization.

## Problem Addressed

Before this sprint:

- expired and revoked browser sessions had no bounded retention policy;
- encrypted provider logout hints could remain after a session became inactive;
- operators could not enumerate active sessions or investigate a subject/provider-session scope;
- containment required knowing an individual opaque browser cookie;
- login, revocation, purge, migration, and deletion did not share one lifecycle ledger;
- metrics distinguished only active and revoked rows.

That was sufficient for a local login demonstration but incomplete for an operated control plane.

## Delivered Scope

### Persistence

- Added provider-session SHA-256 hash, keyed client fingerprint, and provider-token purge time.
- Added append-only `oidc_browser_session_events` with actor snapshots and per-session hash links.
- Backfilled provider hashes and migration-baseline events for existing sessions.
- Added `oidc_session_cleanup` to the durable job type constraint.
- Added Alembic revision `202607270001` on top of Sprint 5H-D.

### Security And Lifecycle

- Added verified-role audit and administrator policies.
- Added single-session, subject-wide, and provider-session-hash revocation.
- Preserved the operator's current session during bulk containment.
- Required normal CSRF-protected logout for the current session.
- Purged encrypted provider ID tokens and raw provider `sid` values on revocation.
- Preserved only bounded correlation hashes after token minimization.
- Recorded issuance, migration, revocation, token purge, and retention deletion.

### Durable Cleanup

- Added bounded inactive-session deletion with `FOR UPDATE SKIP LOCKED`.
- Preserved lifecycle events after parent session deletion.
- Added an independent bounded pass for inactive provider-token minimization.
- Added periodic interval-bucket enqueue from every worker with unique job dedupe.
- Added authenticated manual cleanup that returns a durable job.
- Reused worker claim leases, heartbeats, retry, dead-letter, and result evidence.

### API And UX

- Added overview, session list, event list, three revocation scopes, and cleanup APIs.
- Added session permissions to the normalized operator identity response.
- Added a Browser Sessions page under Audit.
- Added status and exact-subject filtering, current-session indication, fingerprints, token state,
  event hash lineage, role-aware disabled controls, reason confirmation, and refresh.
- Added `oidc_session_cleanup` labels to Agent Jobs.

### Operations

- Added expired, retention-due, inactive-provider-token, and cumulative audit-event metrics.
- Added warning alerting for overdue retention.
- Added critical alerting for inactive rows retaining encrypted provider token material.
- Added backend/worker Compose configuration for one shared cleanup policy.

## Key Design Decisions

1. **Minimize secrets before deleting audit state.** Provider token material is removed as soon as
   the session becomes inactive; the row may remain for the configured investigation window.
2. **Preserve correlation without preserving raw client data.** Provider `sid` uses SHA-256 and the
   local client descriptor uses keyed HMAC-SHA256.
3. **Keep current-session logout explicit.** Administrative mutation does not bypass browser
   cookie deletion, CSRF, or provider logout.
4. **Separate audit from administration.** ML Ops can inspect session evidence; only Admin and SRE
   Lead can mutate it.
5. **Reuse durable jobs.** Cleanup gains existing leases, retries, dead letters, and job evidence
   without a second scheduler.
6. **Retain events independently.** Session data minimization does not remove the lifecycle ledger.
7. **Describe the hash chain accurately.** It provides application-level tamper evidence but is
   not an externally anchored transparency log.

## Verification Evidence

### Automated

- Backend pytest: `175 passed`, one upstream Starlette TestClient deprecation warning.
- Backend Ruff: passed.
- Frontend typecheck: passed.
- Frontend ESLint: passed.
- Frontend production build: passed.
- Focused OIDC lifecycle and administration tests: `9 passed`.
- Tests cover issuance/revocation chains, fingerprints, immediate token purge, role separation,
  all revocation scopes, current-session preservation, cleanup dedupe, deletion, token
  minimization, and audit preservation.

The full backend suite used `--basetemp=tmp/pytest-5he` because a stale Windows global pytest
temporary directory had restrictive permissions. The project-local run completed normally.

### PostgreSQL And Docker

- Migration: `202607270001 (head)`.
- Database and backend: healthy.
- Frontend, Keycloak, and trust-source fixture: running.
- Agent worker replicas online: 2.
- Both workers observed one cleanup bucket and produced exactly one durable job:
  `968fafa9-466b-485f-968b-ac4ed3894beb`.
- Periodic job result: completed on attempt 1, deleted 0 rows, purged provider tokens from 3
  inactive sessions, retention due remaining 0, inactive provider tokens remaining 0.
- Auditor cleanup request: HTTP 403.
- Administrator manual cleanup job:
  `a1d807df-7bf3-49e9-8056-80c9bd6847eb`, completed on attempt 1.
- Post-login live state: active 1, expired 1, revoked 2, retention due 0, audit events 7.
- Prometheus state before the final browser login: active 0, expired 1, revoked 2, retention due 0,
  inactive provider token 0, audit events 6.

### Browser

- Development Keycloak PKCE login normalized `evaluator` to verified `ML Ops Lead`.
- Audit permission was true and administration permission false.
- Summary displayed active 1, expired 1, revoked 2, retention due 0, and audit events 7.
- Queue cleanup and all revocation actions were disabled for the audit-only role.
- Status filter reduced the table to the one active session.
- Audit Events displayed all seven issuance, migration, and purge records with prior/current hash
  fingerprints.
- Current active session displayed provider/client fingerprints and retained token state.
- Historical expired/revoked sessions displayed purged token state.
- Desktop document width matched the viewport; the fixed-width evidence table used its own
  horizontal scroll container.
- Mobile `390 x 844` document width matched the viewport and the table remained internally
  scrollable without page-level horizontal overflow.
- Final browser console warnings/errors: 0.

## Compatibility

- Existing opaque browser cookies and CSRF hashes remain valid through their original lifecycle.
- Existing sessions receive migration-baseline events and provider hashes where available.
- Bearer JWT, trusted proxy header, and local unverified identity precedence is unchanged.
- Current login, callback, and POST logout paths are unchanged.
- Evidence, trust, Gate, readiness, and release schemas are unchanged.
- The migration is additive except for widening the existing durable-job type check constraint.

## Deliberate Non-Claims

- Administrative revocation is local; provider back-channel logout is not implemented.
- IdP account disablement, SCIM, and enterprise identity lifecycle are not included.
- The hash-linked event ledger is not externally anchored or database-write-once.
- The development Keycloak profile does not establish production SSO or TLS.
- PostgreSQL job dedupe is not multi-region consensus.
- No durable time-series SLO store or owned external paging destination is included.
- Current model evidence still lacks target 7B representative GPU execution, production-tier
  publisher identity, and reviewed signed production captures.

## Recommended Next Work

1. Sprint 5H-F: durable time-series retention, explicit identity/worker SLOs, owned paging delivery,
   and end-to-end delivery tests.
2. Staging internal-CA or external publisher integration over TLS.
3. Target 7B representative GPU validation and reviewed signed production captures.
4. Per-job OS or Kubernetes isolation with enforced egress and resource policy.
5. Provider back-channel logout and external identity lifecycle integration where the selected IdP
   supports them.
