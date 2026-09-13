"use client";

import {
  Archive,
  Ban,
  CalendarClock,
  Eye,
  FileKey2,
  KeyRound,
  ListTree,
  Network,
  Play,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  TimerReset,
  Upload,
  X
} from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  EvidenceTrustRoot,
  EvidenceTrustSource,
  EvidenceTrustSourceSchedule,
  EvidenceTrustSourceSync,
  ModelSupplyChainAttestation,
  OperatorIdentity,
  TransparencyProof,
  TrustRegistryOverview
} from "@/types/api";

type TrustRegistryConsoleProps = {
  overview: TrustRegistryOverview;
  sources: EvidenceTrustSource[];
  schedules: EvidenceTrustSourceSchedule[];
  syncs: EvidenceTrustSourceSync[];
  roots: EvidenceTrustRoot[];
  attestations: ModelSupplyChainAttestation[];
  proofs: TransparencyProof[];
};

type RegistryMode = "source" | "root" | "proof";

export function TrustRegistryConsole({
  overview,
  sources,
  schedules,
  syncs,
  roots,
  attestations,
  proofs
}: TrustRegistryConsoleProps) {
  const [mode, setMode] = useState<RegistryMode>("source");
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionRoot, setActionRoot] = useState<EvidenceTrustRoot | null>(null);
  const [actionType, setActionType] = useState<"retired" | "revoked">("retired");
  const [actionReason, setActionReason] = useState("");
  const [ticketReference, setTicketReference] = useState("");

  const [sourceName, setSourceName] = useState("");
  const [sourcePurpose, setSourcePurpose] =
    useState<EvidenceTrustSource["purpose"]>("model_publisher");
  const [sourceIssuer, setSourceIssuer] = useState("");
  const [sourceTrustTier, setSourceTrustTier] =
    useState<EvidenceTrustSource["trust_tier"]>("development");
  const [endpointUrl, setEndpointUrl] = useState("");
  const [sourceAlgorithm, setSourceAlgorithm] =
    useState<EvidenceTrustRoot["algorithm"]>("RS256");
  const [freshnessSeconds, setFreshnessSeconds] = useState("3600");
  const [allowInsecureHttp, setAllowInsecureHttp] = useState(false);
  const [scheduleSource, setScheduleSource] = useState<EvidenceTrustSource | null>(null);
  const [scheduleEnabled, setScheduleEnabled] = useState(true);
  const [scheduleInterval, setScheduleInterval] = useState("3600");
  const [scheduleJitter, setScheduleJitter] = useState("60");
  const [scheduleMaxAttempts, setScheduleMaxAttempts] = useState("3");
  const [scheduleRetryBase, setScheduleRetryBase] = useState("5");
  const [scheduleRetryMax, setScheduleRetryMax] = useState("300");
  const [scheduleRetryJitter, setScheduleRetryJitter] = useState("2");
  const [scheduleRunImmediately, setScheduleRunImmediately] = useState(true);

  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState<EvidenceTrustRoot["purpose"]>("model_publisher");
  const [issuer, setIssuer] = useState("");
  const [keyId, setKeyId] = useState("");
  const [algorithm, setAlgorithm] = useState<EvidenceTrustRoot["algorithm"]>("RS256");
  const [trustTier, setTrustTier] = useState<EvidenceTrustRoot["trust_tier"]>("development");
  const [sourceType, setSourceType] = useState<EvidenceTrustRoot["source_type"]>("development");
  const [sourceUri, setSourceUri] = useState("");
  const [jwkJson, setJwkJson] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [supersedesId, setSupersedesId] = useState("");

  const [attestationId, setAttestationId] = useState(attestations[0]?.id ?? "");
  const [checkpointJws, setCheckpointJws] = useState("");
  const [entryJson, setEntryJson] = useState("");
  const [logIndex, setLogIndex] = useState("0");
  const [inclusionPath, setInclusionPath] = useState("");

  useEffect(() => {
    let active = true;
    async function loadIdentity() {
      const response = await browserApiFetch(`${API_BASE_URL}/operator-identity/me`, {
        cache: "no-store"
      }).catch(() => null);
      if (active && response?.ok) {
        setIdentity((await response.json()) as OperatorIdentity);
      }
    }
    void loadIdentity();
    return () => {
      active = false;
    };
  }, []);

  const governanceOperator = useMemo(() => {
    const role = identity?.role?.toLowerCase() ?? "";
    return Boolean(
      identity?.identity_verified &&
        ["admin", "model governance", "ml ops lead"].includes(role)
    );
  }, [identity]);
  const evidenceOperator = useMemo(() => {
    const role = identity?.role?.toLowerCase() ?? "";
    return Boolean(
      identity?.identity_verified &&
        ["admin", "model governance", "ml ops lead", "sre lead"].includes(role)
    );
  }, [identity]);
  const eligibleOperator = mode === "proof" ? evidenceOperator : governanceOperator;
  const sourceById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources]
  );
  const scheduleBySourceId = useMemo(
    () => new Map(schedules.map((schedule) => [schedule.trust_source_id, schedule])),
    [schedules]
  );
  const selectedSchedule = scheduleSource
    ? scheduleBySourceId.get(scheduleSource.id) ?? null
    : null;
  const scheduleHasActiveJob =
    selectedSchedule?.status === "leased" || selectedSchedule?.status === "retrying";
  const schedulePolicyInvalid =
    Number(scheduleInterval) < 60 ||
    Number(scheduleJitter) < 0 ||
    Number(scheduleJitter) >= Number(scheduleInterval) ||
    Number(scheduleMaxAttempts) < 1 ||
    Number(scheduleRetryBase) < 1 ||
    Number(scheduleRetryMax) < Number(scheduleRetryBase) ||
    Number(scheduleRetryJitter) < 0 ||
    Number(scheduleRetryJitter) > Number(scheduleRetryMax);

  function updateTrustTier(value: EvidenceTrustRoot["trust_tier"]) {
    setTrustTier(value);
    setSourceType(
      value === "development"
        ? "development"
        : value === "internal_ca"
          ? "internal_ca"
          : purpose === "transparency_log"
            ? "transparency_log"
            : "external_registry"
    );
  }

  async function submitSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("Registering federated trust source");
    const response = await browserApiFetch(`${API_BASE_URL}/trust-registry/sources`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: sourceName.trim(),
        source_kind: "jwks",
        purpose: sourcePurpose,
        issuer: sourceIssuer.trim(),
        trust_tier: sourceTrustTier,
        endpoint_url: endpointUrl.trim(),
        allowed_algorithms: [sourceAlgorithm],
        allow_insecure_http: allowInsecureHttp,
        freshness_seconds: Number(freshnessSeconds),
        enabled: true
      })
    });
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  async function syncSource(sourceId: string, syncMode: "preview" | "apply") {
    setBusy(true);
    setNotice(`${syncMode === "preview" ? "Previewing" : "Applying"} remote JWKS`);
    const response = await browserApiFetch(
      `${API_BASE_URL}/trust-registry/sources/${sourceId}/sync`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode: syncMode })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  function openSchedule(source: EvidenceTrustSource) {
    const existing = scheduleBySourceId.get(source.id);
    const defaultInterval = Math.max(60, source.freshness_seconds);
    setScheduleSource(source);
    setScheduleEnabled(existing?.enabled ?? true);
    setScheduleInterval(String(existing?.interval_seconds ?? defaultInterval));
    setScheduleJitter(
      String(existing?.jitter_seconds ?? Math.min(60, defaultInterval - 1))
    );
    setScheduleMaxAttempts(String(existing?.max_attempts ?? 3));
    setScheduleRetryBase(String(existing?.retry_base_seconds ?? 5));
    setScheduleRetryMax(String(existing?.retry_max_seconds ?? 300));
    setScheduleRetryJitter(String(existing?.retry_jitter_seconds ?? 2));
    setScheduleRunImmediately(!existing);
    setNotice(null);
  }

  async function submitSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scheduleSource) return;
    setBusy(true);
    setNotice("Saving automatic synchronization policy");
    const response = await browserApiFetch(
      `${API_BASE_URL}/trust-registry/sources/${scheduleSource.id}/schedule`,
      {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          enabled: scheduleEnabled,
          interval_seconds: Number(scheduleInterval),
          jitter_seconds: Number(scheduleJitter),
          max_attempts: Number(scheduleMaxAttempts),
          retry_base_seconds: Number(scheduleRetryBase),
          retry_max_seconds: Number(scheduleRetryMax),
          retry_jitter_seconds: Number(scheduleRetryJitter),
          run_immediately: scheduleRunImmediately
        })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  async function runScheduleNow() {
    if (!scheduleSource || !selectedSchedule) return;
    setBusy(true);
    setNotice("Queueing automatic synchronization");
    const response = await browserApiFetch(
      `${API_BASE_URL}/trust-registry/sources/${scheduleSource.id}/schedule/run`,
      { method: "POST" }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  async function submitRoot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsedJwk: Record<string, unknown>;
    try {
      parsedJwk = JSON.parse(jwkJson) as Record<string, unknown>;
    } catch {
      setNotice("Public JWK must be valid JSON");
      return;
    }
    setBusy(true);
    setNotice("Registering public trust root");
    const response = await browserApiFetch(`${API_BASE_URL}/trust-registry/roots`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        purpose,
        issuer: issuer.trim(),
        key_id: keyId.trim(),
        algorithm,
        public_key_jwk_json: parsedJwk,
        trust_tier: trustTier,
        source_type: sourceType,
        source_uri: sourceUri.trim() || null,
        valid_until: validUntil ? new Date(validUntil).toISOString() : null,
        supersedes_trust_root_id: supersedesId || null
      })
    });
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  async function submitProof(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsedEntry: Record<string, unknown>;
    try {
      parsedEntry = JSON.parse(entryJson) as Record<string, unknown>;
    } catch {
      setNotice("Transparency entry must be valid JSON");
      return;
    }
    setBusy(true);
    setNotice("Verifying checkpoint and inclusion path");
    const path = inclusionPath
      .split(/[\s,]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    const response = await browserApiFetch(
      `${API_BASE_URL}/trust-registry/transparency-proofs`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          supply_chain_attestation_id: attestationId,
          signed_checkpoint_jws: checkpointJws.trim(),
          entry_json: parsedEntry,
          log_index: Number(logIndex),
          inclusion_path: path
        })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  async function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!actionRoot) return;
    setBusy(true);
    setNotice(`Recording ${actionType}`);
    const response = await browserApiFetch(
      `${API_BASE_URL}/trust-registry/roots/${actionRoot.id}/actions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action_type: actionType,
          reason: actionReason.trim(),
          ticket_reference: ticketReference.trim() || null
        })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  return (
    <>
      <section className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Trust sources"
          value={overview.trust_source_count}
          detail={`${overview.healthy_source_count} healthy, ${overview.automatic_schedule_enabled_count} automated`}
          tone={overview.failed_source_count || overview.stale_source_count ? "amber" : "teal"}
        />
        <SummaryCard
          label="Active roots"
          value={overview.active_root_count}
          detail={`${overview.production_eligible_root_count} production eligible`}
          tone="teal"
        />
        <SummaryCard
          label="Transparency proofs"
          value={overview.transparency_proof_count}
          detail={`${overview.production_eligible_proof_count} production eligible`}
          tone="violet"
        />
        <SummaryCard
          label="Eligible attestations"
          value={overview.production_eligible_attestation_count}
          detail={`${overview.production_tier_attestation_pending_count} pending proof`}
          tone={overview.production_tier_attestation_pending_count ? "amber" : "teal"}
        />
      </section>

      {scheduleSource ? (
        <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
                <CalendarClock size={18} aria-hidden="true" />
                Automatic Synchronization
              </h2>
              <div className="mt-1 text-sm text-neutral-500">{scheduleSource.name}</div>
            </div>
            <div className="flex items-center gap-2">
              {selectedSchedule ? (
                <Badge tone={scheduleStatusTone(selectedSchedule.status)}>
                  {selectedSchedule.status}
                </Badge>
              ) : null}
              {selectedSchedule ? (
                <button
                  type="button"
                  onClick={() => void runScheduleNow()}
                  disabled={
                    busy ||
                    !governanceOperator ||
                    !selectedSchedule.enabled ||
                    scheduleHasActiveJob
                  }
                  className="inline-flex h-9 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium text-neutral-700 disabled:opacity-40"
                >
                  <TimerReset size={16} aria-hidden="true" />
                  Run now
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => setScheduleSource(null)}
                title="Close automation settings"
                aria-label="Close automation settings"
                className="inline-grid h-9 w-9 place-items-center rounded-md border border-line text-neutral-600"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
          <form onSubmit={submitSchedule} className="grid min-w-0 gap-4 p-5">
            <label className="flex min-w-0 items-center gap-3 text-sm font-medium text-neutral-700">
              <input
                type="checkbox"
                checked={scheduleEnabled}
                onChange={(event) => setScheduleEnabled(event.target.checked)}
                className="h-4 w-4 rounded border-line"
              />
              Automation enabled
            </label>
            <div className="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <TextField
                label="Interval seconds"
                value={scheduleInterval}
                onChange={setScheduleInterval}
                type="number"
              />
              <TextField
                label="Schedule jitter seconds"
                value={scheduleJitter}
                onChange={setScheduleJitter}
                type="number"
              />
              <TextField
                label="Maximum attempts"
                value={scheduleMaxAttempts}
                onChange={setScheduleMaxAttempts}
                type="number"
              />
              <TextField
                label="Retry base seconds"
                value={scheduleRetryBase}
                onChange={setScheduleRetryBase}
                type="number"
              />
              <TextField
                label="Retry ceiling seconds"
                value={scheduleRetryMax}
                onChange={setScheduleRetryMax}
                type="number"
              />
              <TextField
                label="Retry jitter seconds"
                value={scheduleRetryJitter}
                onChange={setScheduleRetryJitter}
                type="number"
              />
            </div>
            <label className="flex min-w-0 items-center gap-3 text-sm text-neutral-700">
              <input
                type="checkbox"
                checked={scheduleRunImmediately}
                onChange={(event) => setScheduleRunImmediately(event.target.checked)}
                className="h-4 w-4 rounded border-line"
              />
              Queue the next run immediately
            </label>
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={
                  busy ||
                  !governanceOperator ||
                  scheduleHasActiveJob ||
                  schedulePolicyInvalid
                }
                className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Save size={16} aria-hidden="true" />
                Save policy
              </button>
              {selectedSchedule ? (
                <span className="text-xs text-neutral-500">
                  Run {selectedSchedule.run_sequence} / {selectedSchedule.consecutive_failures} consecutive failures
                </span>
              ) : null}
              {notice ? <span className="text-sm text-neutral-600">{notice}</span> : null}
            </div>
          </form>
        </section>
      ) : null}

      <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <Network size={18} aria-hidden="true" />
            Configured Trust Sources
          </h2>
          <Badge tone={overview.healthy_source_count === overview.trust_source_count ? "teal" : "amber"}>
            {overview.healthy_source_count} healthy
          </Badge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1380px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Endpoint</th>
                <th className="px-4 py-3">Tier / transport</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Freshness</th>
                <th className="px-4 py-3">Automation</th>
                <th className="px-4 py-3">Keys</th>
                <th className="px-4 py-3 text-right">Sync</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sources.map((source) => {
                const schedule = scheduleBySourceId.get(source.id);
                return (
                <tr key={source.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{source.name}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {label(source.purpose)} / {source.issuer}
                    </div>
                  </td>
                  <td className="max-w-[300px] px-4 py-3">
                    <div className="truncate font-mono text-xs" title={source.endpoint_url}>
                      {source.endpoint_url}
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {source.allowed_algorithms_json.join(", ")}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={source.production_eligible ? "teal" : "neutral"}>
                      {label(source.trust_tier)}
                    </Badge>
                    <div className="mt-1 text-xs text-neutral-500">
                      {source.endpoint_url.startsWith("https://") ? "HTTPS" : "development HTTP"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={sourceStatusTone(source.status)}>{source.status}</Badge>
                    <div className="mt-1 text-xs text-neutral-500">
                      {source.enabled ? "enabled" : "disabled"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <div>{formatDuration(source.freshness_seconds)}</div>
                    <div className="mt-1 text-neutral-500">
                      {source.next_sync_due_at
                        ? `Due ${formatDate(source.next_sync_due_at)}`
                        : "No successful apply"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Badge tone={schedule ? scheduleStatusTone(schedule.status) : "neutral"}>
                        {schedule?.status ?? "manual"}
                      </Badge>
                      <button
                        type="button"
                        onClick={() => openSchedule(source)}
                        disabled={busy || !governanceOperator}
                        title="Configure automatic synchronization"
                        aria-label={`Configure automation for ${source.name}`}
                        className="inline-grid h-8 w-8 place-items-center rounded-md border border-line text-neutral-600 disabled:opacity-40"
                      >
                        <Settings2 size={15} aria-hidden="true" />
                      </button>
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {schedule
                        ? `${formatInterval(schedule.interval_seconds)} / next ${formatDate(schedule.next_run_at)}`
                        : "Operator initiated only"}
                    </div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    <div>{source.current_key_count}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {source.last_successful_apply_at
                        ? `Applied ${formatDate(source.last_successful_apply_at)}`
                        : "Not applied"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex gap-2">
                      <button
                        type="button"
                        onClick={() => void syncSource(source.id, "preview")}
                        disabled={busy || !governanceOperator || !source.enabled}
                        title="Preview remote JWKS"
                        aria-label={`Preview ${source.name}`}
                        className="inline-grid h-9 w-9 place-items-center rounded-md border border-line text-neutral-600 disabled:opacity-40"
                      >
                        <Eye size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        onClick={() => void syncSource(source.id, "apply")}
                        disabled={busy || !governanceOperator || !source.enabled}
                        title="Apply remote JWKS"
                        aria-label={`Apply ${source.name}`}
                        className="inline-grid h-9 w-9 place-items-center rounded-md bg-ink text-white disabled:opacity-40"
                      >
                        <Play size={16} aria-hidden="true" />
                      </button>
                    </div>
                  </td>
                </tr>
                );
              })}
              {!sources.length ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-neutral-500">
                    No federated trust sources.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <RefreshCw size={18} aria-hidden="true" />
            Trust Source Sync History
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Trigger</th>
                <th className="px-4 py-3">Mode</th>
                <th className="px-4 py-3">Result</th>
                <th className="px-4 py-3">Keys</th>
                <th className="px-4 py-3">Completed</th>
                <th className="px-4 py-3">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {syncs.map((sync) => {
                const source = sourceById.get(sync.trust_source_id);
                return (
                  <tr key={sync.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-ink">{source?.name ?? "Unknown source"}</div>
                      <div className="mt-1 font-mono text-xs text-neutral-500">
                        {sync.payload_hash?.slice(0, 16) ?? "no payload"}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={sync.trigger === "scheduled" ? "violet" : "neutral"}>
                        {sync.trigger}
                      </Badge>
                      <div className="mt-1 text-xs text-neutral-500">
                        Attempt {sync.attempt_number}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={sync.mode === "apply" ? "violet" : "neutral"}>{sync.mode}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={sync.status === "succeeded" ? "teal" : "rose"}>
                        {sync.status}
                      </Badge>
                      <div className="mt-1 text-xs text-neutral-500">
                        {sync.http_status ? `HTTP ${sync.http_status}` : "No HTTP status"}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs tabular-nums">
                      <div>{sync.key_count} observed / {sync.candidate_count} candidate</div>
                      <div className="mt-1 text-neutral-500">
                        {sync.imported_count} imported, {sync.unchanged_count} unchanged, {sync.rejected_count} rejected
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs">{formatDate(sync.completed_at)}</td>
                    <td className="max-w-[320px] px-4 py-3 text-xs">
                      <div className={sync.error_message ? "text-rose-700" : "text-neutral-500"}>
                        {sync.error_message ?? "Validated without error"}
                      </div>
                      {sync.error_code ? (
                        <div className="mt-1 font-mono text-neutral-500">{sync.error_code}</div>
                      ) : null}
                      {sync.job_id ? (
                        <div className="mt-1 font-mono text-neutral-500">
                          job {sync.job_id.slice(0, 12)}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
              {!syncs.length ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-neutral-500">
                    No trust-source synchronization attempts.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <FileKey2 size={18} aria-hidden="true" />
            Evidence Intake
          </h2>
          <div className="flex flex-wrap gap-2">
            <Badge tone={eligibleOperator ? "teal" : "amber"}>
              {eligibleOperator ? identity?.role ?? "verified operator" : "governance role required"}
            </Badge>
            <Badge tone={overview.production_eligible_root_count ? "teal" : "amber"}>
              {overview.production_eligible_root_count ? "managed trust available" : "development trust only"}
            </Badge>
          </div>
        </div>

        <div className="border-b border-line px-5 pt-4">
          <div className="inline-flex max-w-full flex-wrap rounded-md border border-line bg-neutral-50 p-1">
            <button
              type="button"
              onClick={() => setMode("source")}
              aria-pressed={mode === "source"}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                mode === "source" ? "bg-white text-ink shadow-sm" : "text-neutral-500"
              }`}
            >
              <Network size={14} aria-hidden="true" />
              Trust source
            </button>
            <button
              type="button"
              onClick={() => setMode("root")}
              aria-pressed={mode === "root"}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                mode === "root" ? "bg-white text-ink shadow-sm" : "text-neutral-500"
              }`}
            >
              <KeyRound size={14} aria-hidden="true" />
              Trust root
            </button>
            <button
              type="button"
              onClick={() => setMode("proof")}
              aria-pressed={mode === "proof"}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                mode === "proof" ? "bg-white text-ink shadow-sm" : "text-neutral-500"
              }`}
            >
              <ListTree size={14} aria-hidden="true" />
              Transparency proof
            </button>
          </div>
        </div>

        {mode === "source" ? (
          <form onSubmit={submitSource} className="grid min-w-0 gap-4 p-5">
            <div className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <TextField label="Name" value={sourceName} onChange={setSourceName} />
              <SelectField
                label="Purpose"
                value={sourcePurpose}
                onChange={(value) =>
                  setSourcePurpose(value as EvidenceTrustSource["purpose"])
                }
                options={["model_publisher", "production_collector", "transparency_log"]}
              />
              <TextField label="Issuer" value={sourceIssuer} onChange={setSourceIssuer} />
              <SelectField
                label="Trust tier"
                value={sourceTrustTier}
                onChange={(value) =>
                  setSourceTrustTier(value as EvidenceTrustSource["trust_tier"])
                }
                options={["development", "internal_ca", "external"]}
              />
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700 md:col-span-2">
                JWKS endpoint
                <input
                  type="url"
                  value={endpointUrl}
                  onChange={(event) => setEndpointUrl(event.target.value)}
                  placeholder="https://publisher.example/.well-known/jwks.json"
                  className="h-10 min-w-0 w-full rounded-md border border-line bg-white px-3 text-sm"
                />
              </label>
              <SelectField
                label="Algorithm"
                value={sourceAlgorithm}
                onChange={(value) =>
                  setSourceAlgorithm(value as EvidenceTrustRoot["algorithm"])
                }
                options={["RS256", "ES256", "EdDSA"]}
              />
              <TextField
                label="Freshness seconds"
                value={freshnessSeconds}
                onChange={setFreshnessSeconds}
                type="number"
              />
            </div>
            <label className="flex min-w-0 items-start gap-3 text-sm text-neutral-700">
              <input
                type="checkbox"
                checked={allowInsecureHttp}
                onChange={(event) => setAllowInsecureHttp(event.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-line"
              />
              <span>
                Allow HTTP for this source
                <span className="mt-1 block text-xs text-neutral-500">
                  Requires the server-side development transport override.
                </span>
              </span>
            </label>
            <SubmitRow
              disabled={
                busy ||
                !eligibleOperator ||
                !sourceName.trim() ||
                !sourceIssuer.trim() ||
                !endpointUrl.trim() ||
                Number(freshnessSeconds) < 60
              }
              notice={notice}
              label="Register trust source"
            />
          </form>
        ) : mode === "root" ? (
          <form onSubmit={submitRoot} className="grid min-w-0 gap-4 p-5">
            <div className="grid min-w-0 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <TextField label="Name" value={name} onChange={setName} />
              <SelectField
                label="Purpose"
                value={purpose}
                onChange={(value) => setPurpose(value as EvidenceTrustRoot["purpose"])}
                options={["model_publisher", "production_collector", "transparency_log"]}
              />
              <TextField label="Issuer" value={issuer} onChange={setIssuer} />
              <TextField label="Key ID" value={keyId} onChange={setKeyId} />
              <SelectField
                label="Algorithm"
                value={algorithm}
                onChange={(value) => setAlgorithm(value as EvidenceTrustRoot["algorithm"])}
                options={["RS256", "ES256", "EdDSA"]}
              />
              <SelectField
                label="Trust tier"
                value={trustTier}
                onChange={(value) => updateTrustTier(value as EvidenceTrustRoot["trust_tier"])}
                options={["development", "internal_ca", "external"]}
              />
              <SelectField
                label="Source type"
                value={sourceType}
                onChange={(value) => setSourceType(value as EvidenceTrustRoot["source_type"])}
                options={["development", "internal_ca", "external_registry", "transparency_log"]}
              />
              <TextField label="Source URI" value={sourceUri} onChange={setSourceUri} />
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
                Valid until
                <input
                  type="datetime-local"
                  value={validUntil}
                  onChange={(event) => setValidUntil(event.target.value)}
                  className="h-10 min-w-0 w-full rounded-md border border-line bg-white px-3 text-sm"
                />
              </label>
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700 xl:col-span-2">
                Supersedes
                <select
                  value={supersedesId}
                  onChange={(event) => setSupersedesId(event.target.value)}
                  className="h-10 min-w-0 w-full rounded-md border border-line bg-white px-3 text-sm"
                >
                  <option value="">No prior key</option>
                  {roots.filter((root) => root.status === "active").map((root) => (
                    <option key={root.id} value={root.id}>
                      {root.issuer} / {root.key_id}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
              Public JWK
              <textarea
                value={jwkJson}
                onChange={(event) => setJwkJson(event.target.value)}
                rows={7}
                spellCheck={false}
                className="min-w-0 w-full resize-y rounded-md border border-line bg-white p-3 font-mono text-xs"
              />
            </label>
            <SubmitRow
              disabled={
                busy || !eligibleOperator || !name.trim() || !issuer.trim() || !keyId.trim() || !jwkJson.trim()
              }
              notice={notice}
              label="Register public key"
            />
          </form>
        ) : (
          <form onSubmit={submitProof} className="grid min-w-0 gap-4 p-5">
            <div className="grid min-w-0 gap-4 md:grid-cols-[minmax(0,1fr)_160px]">
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
                Supply-chain attestation
                <select
                  value={attestationId}
                  onChange={(event) => setAttestationId(event.target.value)}
                  className="h-10 min-w-0 w-full rounded-md border border-line bg-white px-3 text-sm"
                >
                  {attestations.map((attestation) => (
                    <option key={attestation.id} value={attestation.id}>
                      {attestation.publisher} / {attestation.statement_id}
                    </option>
                  ))}
                </select>
              </label>
              <TextField label="Log index" value={logIndex} onChange={setLogIndex} type="number" />
            </div>
            <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
              Signed checkpoint JWS
              <textarea
                value={checkpointJws}
                onChange={(event) => setCheckpointJws(event.target.value)}
                rows={5}
                spellCheck={false}
                className="min-w-0 w-full resize-y rounded-md border border-line bg-white p-3 font-mono text-xs"
              />
            </label>
            <div className="grid gap-4 lg:grid-cols-2">
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
                Transparency entry
                <textarea
                  value={entryJson}
                  onChange={(event) => setEntryJson(event.target.value)}
                  rows={7}
                  spellCheck={false}
                  className="min-w-0 w-full resize-y rounded-md border border-line bg-white p-3 font-mono text-xs"
                />
              </label>
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
                Inclusion path
                <textarea
                  value={inclusionPath}
                  onChange={(event) => setInclusionPath(event.target.value)}
                  rows={7}
                  spellCheck={false}
                  className="min-w-0 w-full resize-y rounded-md border border-line bg-white p-3 font-mono text-xs"
                />
              </label>
            </div>
            <SubmitRow
              disabled={
                busy || !eligibleOperator || !attestationId || !checkpointJws.trim() || !entryJson.trim()
              }
              notice={notice}
              label="Verify inclusion proof"
            />
          </form>
        )}
      </section>

      <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <ShieldCheck size={18} aria-hidden="true" />
            Signing Trust Roots
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1240px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Purpose</th>
                <th className="px-4 py-3">Issuer / key</th>
                <th className="px-4 py-3">Tier</th>
                <th className="px-4 py-3">Trust source</th>
                <th className="px-4 py-3">Validity</th>
                <th className="px-4 py-3">Fingerprint</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {roots.map((root) => (
                <tr key={root.id}>
                  <td className="px-4 py-3 font-medium text-ink">{label(root.purpose)}</td>
                  <td className="px-4 py-3">
                    <div>{root.issuer}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">{root.key_id}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={root.production_eligible ? "teal" : "neutral"}>
                      {label(root.trust_tier)}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    {root.trust_source_id ? (
                      <>
                        <div className="text-xs font-medium text-ink">
                          {sourceById.get(root.trust_source_id)?.name ?? "Unknown source"}
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          {root.trust_source_status ? (
                            <Badge tone={sourceStatusTone(root.trust_source_status)}>
                              {root.trust_source_status}
                            </Badge>
                          ) : null}
                          <span className="text-xs text-neutral-500">
                            {root.source_key_current ? "current" : "not current"}
                          </span>
                        </div>
                      </>
                    ) : (
                      <span className="text-xs text-neutral-500">Manual registration</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <div>{formatDate(root.valid_from)}</div>
                    <div className="mt-1 text-neutral-500">
                      {root.valid_until ? formatDate(root.valid_until) : "No expiry"}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{root.key_fingerprint.slice(0, 18)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(root.status)}>{root.status}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {root.status === "active" ? (
                      <button
                        type="button"
                        onClick={() => setActionRoot(root)}
                        disabled={!governanceOperator || busy}
                        title="Change key lifecycle"
                        className="inline-grid h-9 w-9 place-items-center rounded-md border border-line text-neutral-600 disabled:opacity-40"
                      >
                        <Archive size={16} aria-hidden="true" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {!roots.length ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-neutral-500">
                    No managed trust roots.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {actionRoot ? (
        <section className="min-w-0 rounded-lg border border-amber-200 bg-panel p-5 shadow-soft">
          <form onSubmit={submitAction} className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
                <Ban size={18} className="text-amber-700" aria-hidden="true" />
                Key Lifecycle
              </h2>
              <button
                type="button"
                onClick={() => setActionRoot(null)}
                className="text-sm font-medium text-neutral-500"
              >
                Cancel
              </button>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <SelectField
                label="Action"
                value={actionType}
                onChange={(value) => setActionType(value as "retired" | "revoked")}
                options={["retired", "revoked"]}
              />
              <TextField label="Reason" value={actionReason} onChange={setActionReason} />
              <TextField label="Ticket" value={ticketReference} onChange={setTicketReference} />
            </div>
            <button
              type="submit"
              disabled={busy || !governanceOperator || !actionReason.trim()}
              className="inline-flex h-10 w-fit items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:opacity-40"
            >
              <Archive size={16} aria-hidden="true" />
              Record lifecycle action
            </button>
          </form>
        </section>
      ) : null}

      <section className="min-w-0 overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <ListTree size={18} aria-hidden="true" />
            Transparency Evidence
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Log</th>
                <th className="px-4 py-3">Entry</th>
                <th className="px-4 py-3">Tree</th>
                <th className="px-4 py-3">Integrated</th>
                <th className="px-4 py-3">Log key</th>
                <th className="px-4 py-3">Eligibility</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {proofs.map((proof) => (
                <tr key={proof.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{proof.log_id}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">{proof.proof_id}</div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{proof.leaf_hash.slice(0, 18)}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {proof.log_index} / {proof.tree_size}
                  </td>
                  <td className="px-4 py-3 text-xs">{formatDate(proof.integrated_at)}</td>
                  <td className="px-4 py-3">
                    <div className="font-mono text-xs">{proof.key_id}</div>
                    <div className="mt-1 text-xs text-neutral-500">{proof.trust_root_status}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={proof.production_eligible ? "teal" : "amber"}>
                      {proof.production_eligible ? "production eligible" : "not eligible"}
                    </Badge>
                  </td>
                </tr>
              ))}
              {!proofs.length ? (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-neutral-500">
                    No transparency proofs.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function TextField({
  label: fieldLabel,
  value,
  onChange,
  type = "text"
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: "text" | "number";
}) {
  return (
    <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
      {fieldLabel}
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 min-w-0 w-full rounded-md border border-line bg-white px-3 text-sm"
      />
    </label>
  );
}

function SelectField({
  label: fieldLabel,
  value,
  onChange,
  options
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
      {fieldLabel}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 min-w-0 w-full rounded-md border border-line bg-white px-3 text-sm"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {label(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function SubmitRow({
  disabled,
  notice,
  label: buttonLabel
}: {
  disabled: boolean;
  notice: string | null;
  label: string;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-3">
      <button
        type="submit"
        disabled={disabled}
        className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Upload size={16} aria-hidden="true" />
        {buttonLabel}
      </button>
      {notice ? <span className="text-sm text-neutral-600">{notice}</span> : null}
    </div>
  );
}

function statusTone(status: EvidenceTrustRoot["status"]): "teal" | "amber" | "rose" | "neutral" {
  if (status === "active") return "teal";
  if (status === "revoked") return "rose";
  if (status === "scheduled") return "amber";
  return "neutral";
}

function sourceStatusTone(
  status: EvidenceTrustSource["status"]
): "teal" | "amber" | "rose" | "neutral" {
  if (status === "healthy") return "teal";
  if (status === "failed") return "rose";
  if (status === "degraded" || status === "stale" || status === "unsynced") return "amber";
  return "neutral";
}

function scheduleStatusTone(
  status: EvidenceTrustSourceSchedule["status"]
): "teal" | "amber" | "rose" | "violet" | "neutral" {
  if (status === "scheduled") return "teal";
  if (status === "leased") return "violet";
  if (status === "due" || status === "retrying") return "amber";
  if (status === "failed") return "rose";
  return "neutral";
}

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(new Date(value));
}

function formatDuration(seconds: number): string {
  if (seconds % 86_400 === 0) return `${seconds / 86_400}d window`;
  if (seconds % 3_600 === 0) return `${seconds / 3_600}h window`;
  if (seconds % 60 === 0) return `${seconds / 60}m window`;
  return `${seconds}s window`;
}

function formatInterval(seconds: number): string {
  if (seconds % 86_400 === 0) return `Every ${seconds / 86_400}d`;
  if (seconds % 3_600 === 0) return `Every ${seconds / 3_600}h`;
  if (seconds % 60 === 0) return `Every ${seconds / 60}m`;
  return `Every ${seconds}s`;
}

async function responseError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string | Array<{ msg?: string }> }
    | null;
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.find((item) => item.msg)?.msg ?? "Request failed";
  }
  return `Request failed with status ${response.status}.`;
}
