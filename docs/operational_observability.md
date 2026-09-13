# Operational Observability

Updated: 2026-08-04, Sprint 5H-H

## Purpose

Sprint 5F exports control-plane state as metrics and actionable alerts. Sprint 5G extends the same
aggregation with supply-chain and production-receipt trust while separating unresolved work from
immutable historical totals. The JSON API, Prometheus text endpoint, Operations UI, and bundled
alert rules still share one read model. Sprint 5H-F persists interval snapshots, evaluates explicit
identity and worker SLOs, preserves incident transitions, and owns a signed durable paging path.
Sprint 5H-G adds paired-window burn rates, verified response actions, automatic escalation,
rotating key identity, and CA-verified HTTPS. See `incident_response_and_burn_rate.md` for the
extended contract and rotation runbook.
Sprint 5H-H adds projected secret reload, strict provider receipt correlation, seven-check staging
readiness, and executable rotation and outage recovery. See `staging_paging_qualification.md`.

## Surfaces

| Surface | Location |
| --- | --- |
| JSON metrics | `GET /api/v1/operations/metrics` |
| Derived alerts | `GET /api/v1/operations/alerts` |
| Reliability history | `GET /api/v1/operations/reliability` |
| Prometheus exposition | `GET /metrics` |
| Operator UI | `http://localhost:3000/operations` |
| Prometheus config | `deploy/observability/prometheus.yml` |
| Alert rules | `deploy/observability/model-atlas-rules.yml` |
| Alertmanager routing | `deploy/observability/alertmanager.yml` |
| Signed development paging sink | `https://localhost:9100/receipts` with the generated CA |
| SLO and paging contract | `docs/operational_slo_and_paging.md` |
| Staging qualification | `docs/staging_paging_qualification.md` |

Metrics cover online/offline workers, queue depth, dead letters, expired leases, oldest queue age,
collector health and replay receipts, release review/revocation state, stale Gates, verified model
attestations, verified/revoked supply-chain statements, signed production receipts, unverified
production-labeled runs, applied reviewed-label decisions, active/production-eligible/revoked trust
roots, eligible transparency proofs, proof-pending attestations, and eligible production receipts.
Sprint 5H-B also exports registered, healthy, degraded, stale, failed, and unsynced remote trust
source counts. Sprint 5H-C adds active/revoked database browser sessions and fresh/stale shared
OIDC document counts. Sprint 5H-D adds enabled, due, retrying, and exhausted trust-source schedule
counts. Sprint 5H-E adds expired and retention-due sessions, inactive retained provider tokens,
and cumulative lifecycle-event counts. Sprint 5H-F adds retained snapshot age/count, open
incidents, SLO breach/insufficient state, SLO compliance/target labels, and queued/failed delivery
counts. Identity and lease metrics contain no subject, cookie, raw token, or lease nonce labels.

Derived alerts include:

- queued work with no online worker;
- dead-lettered jobs;
- expired leases;
- stale collector sources;
- release decisions requiring review;
- stale Gate evaluations without a replacement;
- revoked supply-chain attestations;
- revoked signing trust roots;
- failed, stale, degraded, or never-applied trust sources;
- trust-source policies retrying or exhausted;
- browser sessions beyond the configured retention window;
- inactive browser sessions retaining encrypted provider token material;
- stale durable operational snapshots;
- breached identity or worker SLOs;
- permanently failed paging deliveries;
- production-tier attestations missing active transparency evidence;
- production-labeled runs without a trusted receipt.

Each alert has a stable key, severity, source metric, current value, threshold, summary, and route.
Prometheus rules add a hold duration to avoid transient paging.

## Local Profile

```bash
make observability-up
```

Default ports:

- Prometheus: `http://localhost:9090`;
- Alertmanager: `http://localhost:9093`;
- reference alert sink: `http://localhost:9099`;
- signed paging sink: `https://localhost:9100` with the generated CA.

The Alertmanager sink logs bounded local fixtures. The separate paging sink verifies HMAC key
reload, event-id correlation, and bounded provider receipts. Neither is a production on-call
service. Production deployments should use managed PKI, an external secret manager, an owned
paging destination, protected metrics, tested retention/restore, and monitoring for the monitoring
path itself.

## Verified State On 2026-07-20

- Prometheus endpoint returned HTTP 200 with text format `0.0.4`.
- Verified artifact attestations: 1.
- Verified supply-chain attestations: 1; revoked: 0.
- Verified production receipts: 0; unverified production-labeled runs: 0.
- Active trust roots: 3 development, 0 production eligible.
- Transparency proofs: 1 development, 0 production eligible.
- Applied reviewed-label decisions: 2.
- Queue depth, dead letters, and expired leases: 0.
- Historical release-review false positives were reduced from 3 to 0 by requiring an approved
  release or an explicit unresolved review action.
- Six historical stale Gates were reevaluated in two scopes and now point to replacements. The
  unresolved stale count is 0 while the separate historical total remains 6.

After reconciliation, the resulting control-plane health is `healthy` with no active derived
alerts. Historical records remain queryable and immutable.

## Sprint 5H-B Live State On 2026-07-21

- Registered trust sources: 1.
- Healthy trust sources: 1.
- Degraded, stale, failed, and unsynced trust sources: 0.
- Active trust roots: 4 development, including one source-backed current key.
- Trust-source alerts: 0.
- Overall control-plane health remained `healthy` with no active derived alerts.

The source was fetched through the Compose network and applied from an append-only receipt. It is
development-scoped and does not increase the production-eligible root metric.

## Sprint 5H-C Live State On 2026-07-22

- Browser sessions created by end-to-end Keycloak QA: 2.
- Active after logout: 0; server-side revoked: 2.
- Shared OIDC cache rows: 1 JWKS document.
- Stored browser and CSRF secrets: SHA-256 hash lengths 64.
- Stored provider ID tokens: encrypted for both QA sessions.
- The JWKS row correctly moved from fresh to stale after its configured five-minute TTL.

No identity value, cookie, CSRF token, or provider token is exported through metrics.

## Sprint 5H-D Live State On 2026-07-23

- Automatic trust-source policies enabled: 1.
- Due, retrying, and exhausted policies after completion: 0.
- Agent worker replicas online during the controlled run: 2.
- One due run sequence produced one durable job and one scheduled receipt.
- The linked job completed on attempt 1 and advanced the next-run timestamp.
- The policy and worker leases were clear after completion.

Retry and exhausted-policy alerts were also exercised in the backend suite. The live fixture stayed
healthy, so no trust-source schedule alert remained active after Docker verification.

## Sprint 5H-E Live State On 2026-07-27

- Browser sessions after final Keycloak login: active 1, expired 1, revoked 2.
- Retention-due sessions: 0.
- Inactive sessions retaining encrypted provider token material: 0.
- Lifecycle audit events: 7.
- Agent worker replicas online: 2.
- One shared periodic cleanup bucket created one durable job across both workers.
- Periodic cleanup job `968fafa9-466b-485f-968b-ac4ed3894beb` completed on attempt 1.
- The job deleted 0 rows, purged provider token material from 3 inactive rows, and left both
  cleanup backlog metrics at 0.
- Audit-only cleanup was rejected with HTTP 403.
- Admin cleanup job `a1d807df-7bf3-49e9-8056-80c9bd6847eb` completed on attempt 1.

The inactive-provider-token metric is critical because token minimization should follow
revocation or expiry promptly. Retention due is warning-level because it represents a cleanup
backlog without implying a currently usable credential.

## Sprint 5H-F Live State On 2026-07-27

- PostgreSQL migration: `202607270002 (head)`.
- Replica-dedupe checkpoint: 12 snapshots, 12 unique buckets, 12 cycle jobs, and 12 unique job
  dedupe keys.
- Agent worker replicas: 2; latest queue depth: 0.
- Prometheus target: `up`; alert rules loaded: 10.
- Identity-session SLO: breached after one bad interval in the active 99% window.
- Worker-control-plane SLO: met at 100% during the verification window.
- Signed first-attempt test page: delivered with HTTP 202 and matching payload hash.
- Controlled sink outage: four attempts exhausted and dead-lettered.
- Verified Admin requeue after sink recovery: completed and produced the expected receiver event
  ID.
- Final delivery backlog: queued 0, failed 0.

The durable history intentionally kept the identity breach even though later intervals were
healthy. It will resolve only when the configured rolling window again satisfies the objective.

## Sprint 5H-H Live State On 2026-08-04

- PostgreSQL migration: `202608040001 (head)`.
- Agent worker replicas: 2.
- Runtime key projection: active and retiring keys present; no static observability secret.
- Staging readiness: 7 passed, 0 failed.
- Active key rotated without sender restart to `2026-08-04-rotated`.
- Latest qualifying delivery stored matching provider event and receipt correlation.
- Controlled paging outage reached dead letter; verified SRE requeue recovered the same job.
- Twenty-six failed trust-source sync jobs were normalized after restoring the omitted fixture.
- Final health: `healthy`; open incidents: 0; paging dead letters: 0.

The source fixture, secret initializer, generated CA, and paging sink remain development-only. The
live run proves the adapter and failure-recovery contracts, not external provider availability or
production trust.
