"use client";

import {
  Activity,
  BellRing,
  CheckCircle2,
  Flame,
  History,
  KeyRound,
  LoaderCircle,
  MessageSquareText,
  Play,
  RefreshCw,
  ReceiptText,
  Send,
  ShieldCheck,
  Siren,
  UserCheck,
  UserRoundPlus,
  X
} from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  OperationalAlertDelivery,
  OperationalAlertIncident,
  OperationalAlertIncidentAction,
  OperationalMetrics,
  OperationalReliabilityOverview,
  OperationalSLOEvaluation,
  OperationalSnapshotSummary,
  OperationalStagingReadiness
} from "@/types/api";

type ConsoleTab = "slo" | "incidents" | "deliveries";
type IncidentActionType = "acknowledged" | "assigned" | "note";

export function OperationalReliabilityConsole() {
  const [metrics, setMetrics] = useState<OperationalMetrics | null>(null);
  const [overview, setOverview] = useState<OperationalReliabilityOverview | null>(null);
  const [tab, setTab] = useState<ConsoleTab>("slo");
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<"capture" | "test" | "incident" | null>(null);
  const [showTestPage, setShowTestPage] = useState(false);
  const [testSeverity, setTestSeverity] = useState<"warning" | "critical">("warning");
  const [testReason, setTestReason] = useState("Verify owned paging delivery");
  const [incidentActionTarget, setIncidentActionTarget] = useState<
    OperationalAlertIncident | null
  >(null);
  const [incidentActionType, setIncidentActionType] =
    useState<IncidentActionType>("acknowledged");
  const [incidentReason, setIncidentReason] = useState("");
  const [incidentAssignee, setIncidentAssignee] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [metricsResponse, reliabilityResponse] = await Promise.all([
        browserApiFetch(`${API_BASE_URL}/operations/metrics`, { cache: "no-store" }),
        browserApiFetch(
          `${API_BASE_URL}/operations/reliability?snapshot_limit=60&incident_limit=100&delivery_limit=100`,
          { cache: "no-store" }
        )
      ]);
      if (!metricsResponse.ok || !reliabilityResponse.ok) {
        throw new Error("Operational reliability data is unavailable.");
      }
      setMetrics((await metricsResponse.json()) as OperationalMetrics);
      setOverview((await reliabilityResponse.json()) as OperationalReliabilityOverview);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Operations data is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  async function queueCapture() {
    setAction("capture");
    setError(null);
    setNotice(null);
    try {
      const response = await browserApiFetch(
        `${API_BASE_URL}/operations/reliability/cycles`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            reason: "Operator requested immediate operational capture"
          })
        }
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      const job = (await response.json()) as { id: string };
      setNotice(`Capture job ${job.id.slice(0, 8)} queued.`);
      window.setTimeout(() => void load(), 1200);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Capture could not be queued.");
    } finally {
      setAction(null);
    }
  }

  async function sendTestPage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (testReason.trim().length < 8) return;
    setAction("test");
    setError(null);
    setNotice(null);
    try {
      const response = await browserApiFetch(
        `${API_BASE_URL}/operations/reliability/test-pages`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            severity: testSeverity,
            reason: testReason.trim()
          })
        }
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      const job = (await response.json()) as { id: string };
      setNotice(`Test page job ${job.id.slice(0, 8)} queued.`);
      setShowTestPage(false);
      window.setTimeout(() => void load(), 1200);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Test page could not be queued.");
    } finally {
      setAction(null);
    }
  }

  function openIncidentAction(
    incident: OperationalAlertIncident,
    actionType: IncidentActionType
  ) {
    setIncidentActionTarget(incident);
    setIncidentActionType(actionType);
    setIncidentReason(defaultIncidentReason(actionType));
    setIncidentAssignee(incident.assigned_to ?? "");
  }

  async function submitIncidentAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!incidentActionTarget || incidentReason.trim().length < 8) return;
    if (incidentActionType === "assigned" && !incidentAssignee.trim()) return;
    setAction("incident");
    setError(null);
    setNotice(null);
    try {
      const response = await browserApiFetch(
        `${API_BASE_URL}/operations/reliability/incidents/${incidentActionTarget.id}/actions`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            action_type: incidentActionType,
            reason: incidentReason.trim(),
            assignee:
              incidentActionType === "assigned" ? incidentAssignee.trim() : undefined
          })
        }
      );
      if (!response.ok) throw new Error(await responseMessage(response));
      setNotice(`${incidentActionLabel(incidentActionType)} recorded.`);
      setIncidentActionTarget(null);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Incident action could not be recorded.");
    } finally {
      setAction(null);
    }
  }

  if (loading && !overview) {
    return (
      <div className="flex min-h-48 items-center justify-center text-sm text-neutral-500">
        <LoaderCircle className="mr-2 animate-spin" size={17} aria-hidden="true" />
        Loading operational reliability
      </div>
    );
  }

  if (!overview || !metrics) {
    return (
      <section className="border-y border-line py-8">
        <div className="flex items-start gap-3">
          <Siren className="mt-0.5 text-rose-600" size={20} aria-hidden="true" />
          <div>
            <h2 className="text-sm font-semibold text-ink">Operations data unavailable</h2>
            <p className="mt-1 text-sm text-neutral-600">{error}</p>
          </div>
        </div>
      </section>
    );
  }

  const breachedCount = overview.latest_slo_evaluations.filter(
    (item) => item.status === "breached"
  ).length;
  const deliveredCount = overview.delivery_status_counts.delivered ?? 0;
  const canAdminister = overview.permissions.can_administer;

  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Reliability summary">
        <SummaryCard
          label="Retained snapshots"
          value={overview.snapshot_count}
          detail={`${overview.policy.snapshot_retention_days}-day retention`}
          tone="teal"
        />
        <SummaryCard
          label="SLO breaches"
          value={breachedCount}
          detail={`${formatDuration(overview.policy.slo_window_seconds)} window`}
          tone={breachedCount ? "rose" : "teal"}
        />
        <SummaryCard
          label="Open incidents"
          value={overview.open_incident_count}
          detail="transition tracked"
          tone={overview.open_incident_count ? "amber" : "teal"}
        />
        <SummaryCard
          label="Delivered pages"
          value={deliveredCount}
          detail="durable receipts"
          tone="violet"
        />
      </section>

      <section className="border-y border-line py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
            <Badge tone={healthTone(overview.health)}>{overview.health}</Badge>
            <span>{overview.policy.snapshot_interval_seconds}s capture</span>
            <span>{formatPercent(overview.policy.identity_slo_target)} identity objective</span>
            <span>{formatPercent(overview.policy.worker_slo_target)} worker objective</span>
            <Badge tone={overview.policy.paging_enabled ? "teal" : "amber"}>
              paging {overview.policy.paging_enabled ? "enabled" : "disabled"}
            </Badge>
            <Badge tone={overview.policy.paging_tls_verified ? "teal" : "amber"}>
              TLS {overview.policy.paging_tls_verified ? "verified" : "inactive"}
            </Badge>
            <Badge
              tone={
                overview.policy.paging_secret_source === "projected_file"
                  ? "teal"
                  : "amber"
              }
            >
              {overview.policy.paging_secret_source.replaceAll("_", " ")}
            </Badge>
            <span>{overview.policy.paging_key_count} signing keys</span>
            <span className="font-mono">{overview.policy.paging_provider}</span>
            {overview.policy.paging_active_key_id ? (
              <span className="font-mono">key {overview.policy.paging_active_key_id}</span>
            ) : null}
            {overview.policy.paging_destination ? (
              <span className="font-mono">{overview.policy.paging_destination}</span>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded border border-line bg-white text-neutral-600 hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
              onClick={() => void load()}
              disabled={loading}
              title="Refresh operational state"
              aria-label="Refresh operational state"
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="inline-flex h-9 items-center gap-2 rounded border border-line bg-white px-3 text-xs font-medium text-ink disabled:cursor-not-allowed disabled:opacity-40"
              onClick={() => void queueCapture()}
              disabled={!canAdminister || action !== null}
              title="Queue an immediate metric and SLO capture"
            >
              {action === "capture" ? (
                <LoaderCircle size={15} className="animate-spin" aria-hidden="true" />
              ) : (
                <Play size={15} aria-hidden="true" />
              )}
              Run capture
            </button>
            <button
              type="button"
              className="inline-flex h-9 items-center gap-2 rounded bg-neutral-900 px-3 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
              onClick={() => setShowTestPage(true)}
              disabled={!canAdminister || !overview.policy.paging_enabled || action !== null}
              title="Queue a signed paging delivery test"
            >
              <Send size={15} aria-hidden="true" />
              Test page
            </button>
          </div>
        </div>
        {notice ? (
          <div className="mt-3 flex items-center gap-2 text-xs text-teal-700">
            <CheckCircle2 size={15} aria-hidden="true" />
            {notice}
          </div>
        ) : null}
        {error ? <p className="mt-3 text-xs text-rose-700">{error}</p> : null}
      </section>

      <StagingReadinessBand readiness={overview.staging_readiness} />

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
          <div className="inline-flex rounded border border-line bg-neutral-50 p-1">
            <TabButton
              active={tab === "slo"}
              icon={<Activity size={15} aria-hidden="true" />}
              label="SLO & history"
              onClick={() => setTab("slo")}
            />
            <TabButton
              active={tab === "incidents"}
              icon={<Siren size={15} aria-hidden="true" />}
              label="Incidents"
              onClick={() => setTab("incidents")}
            />
            <TabButton
              active={tab === "deliveries"}
              icon={<BellRing size={15} aria-hidden="true" />}
              label="Deliveries"
              onClick={() => setTab("deliveries")}
            />
          </div>
          <span className="text-xs text-neutral-500">
            Updated {formatDate(overview.generated_at)}
          </span>
        </div>

        {tab === "slo" ? (
          <SLOHistory
            evaluations={overview.latest_slo_evaluations}
            snapshots={overview.snapshots}
            minimumSamples={overview.policy.slo_min_samples}
          />
        ) : null}
        {tab === "incidents" ? (
          <IncidentTable
            incidents={overview.incidents}
            actions={overview.incident_actions}
            canAdminister={canAdminister}
            onAction={openIncidentAction}
          />
        ) : null}
        {tab === "deliveries" ? <DeliveryTable deliveries={overview.deliveries} /> : null}
      </section>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Active Derived Alerts
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Alert</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Signal</th>
                <th className="px-4 py-3">Route</th>
              </tr>
            </thead>
            <tbody>
              {metrics.alerts.map((alert) => (
                <tr key={alert.key} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{alert.key}</div>
                    <div className="mt-1 text-xs text-neutral-500">{alert.summary}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={alert.severity === "critical" ? "rose" : "amber"}>
                      {alert.severity}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {alert.metric_name} = {alert.current_value}
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-600">{alert.route}</td>
                </tr>
              ))}
              {!metrics.alerts.length ? (
                <tr className="border-t border-line">
                  <td className="px-4 py-6 text-neutral-600" colSpan={4}>
                    No active derived alerts.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {showTestPage ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
          <form
            className="w-full max-w-md rounded-lg border border-line bg-white p-5 shadow-xl"
            onSubmit={sendTestPage}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-ink">Send test page</h2>
                <p className="mt-1 text-xs text-neutral-500">
                  Signed delivery through the configured durable route.
                </p>
              </div>
              <button
                type="button"
                className="inline-flex h-8 w-8 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100"
                onClick={() => setShowTestPage(false)}
                aria-label="Close test page dialog"
              >
                <X size={17} aria-hidden="true" />
              </button>
            </div>
            <div className="mt-5">
              <span className="text-xs font-medium text-neutral-700">Severity</span>
              <div className="mt-2 inline-flex rounded border border-line bg-neutral-50 p-1">
                {(["warning", "critical"] as const).map((severity) => (
                  <button
                    key={severity}
                    type="button"
                    className={`h-8 rounded px-3 text-xs font-medium ${
                      testSeverity === severity
                        ? "bg-white text-ink shadow-sm"
                        : "text-neutral-500"
                    }`}
                    onClick={() => setTestSeverity(severity)}
                  >
                    {severity}
                  </button>
                ))}
              </div>
            </div>
            <label className="mt-4 block text-xs font-medium text-neutral-700">
              Reason
              <input
                value={testReason}
                onChange={(event) => setTestReason(event.target.value)}
                maxLength={160}
                className="mt-2 h-10 w-full rounded border border-line bg-white px-3 text-sm text-ink outline-none focus:border-teal-600"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="h-9 rounded border border-line px-3 text-xs font-medium text-neutral-700"
                onClick={() => setShowTestPage(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="inline-flex h-9 items-center gap-2 rounded bg-neutral-900 px-3 text-xs font-medium text-white disabled:opacity-40"
                disabled={action === "test" || testReason.trim().length < 8}
              >
                {action === "test" ? (
                  <LoaderCircle size={15} className="animate-spin" aria-hidden="true" />
                ) : (
                  <Send size={15} aria-hidden="true" />
                )}
                Send
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {incidentActionTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
          <form
            className="w-full max-w-lg rounded-lg border border-line bg-white p-5 shadow-xl"
            onSubmit={submitIncidentAction}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-ink">Incident response</h2>
                <p className="mt-1 truncate font-mono text-xs text-neutral-500">
                  {incidentActionTarget.alert_key}
                </p>
              </div>
              <button
                type="button"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100"
                onClick={() => setIncidentActionTarget(null)}
                aria-label="Close incident response dialog"
              >
                <X size={17} aria-hidden="true" />
              </button>
            </div>
            <div className="mt-5 inline-flex rounded border border-line bg-neutral-50 p-1">
              {(["acknowledged", "assigned", "note"] as const).map((actionType) => (
                <button
                  key={actionType}
                  type="button"
                  className={`h-8 rounded px-3 text-xs font-medium ${
                    incidentActionType === actionType
                      ? "bg-white text-ink shadow-sm"
                      : "text-neutral-500"
                  }`}
                  onClick={() => {
                    setIncidentActionType(actionType);
                    setIncidentReason(defaultIncidentReason(actionType));
                  }}
                  disabled={
                    actionType === "acknowledged" &&
                    incidentActionTarget.acknowledged_at !== null
                  }
                >
                  {incidentActionLabel(actionType)}
                </button>
              ))}
            </div>
            {incidentActionType === "assigned" ? (
              <label className="mt-4 block text-xs font-medium text-neutral-700">
                Assignee
                <input
                  value={incidentAssignee}
                  onChange={(event) => setIncidentAssignee(event.target.value)}
                  maxLength={160}
                  className="mt-2 h-10 w-full rounded border border-line bg-white px-3 text-sm text-ink outline-none focus:border-teal-600"
                />
              </label>
            ) : null}
            <label className="mt-4 block text-xs font-medium text-neutral-700">
              Reason
              <textarea
                value={incidentReason}
                onChange={(event) => setIncidentReason(event.target.value)}
                maxLength={500}
                rows={4}
                className="mt-2 w-full resize-none rounded border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-teal-600"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                className="h-9 rounded border border-line px-3 text-xs font-medium text-neutral-700"
                onClick={() => setIncidentActionTarget(null)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="inline-flex h-9 items-center gap-2 rounded bg-neutral-900 px-3 text-xs font-medium text-white disabled:opacity-40"
                disabled={
                  action === "incident" ||
                  incidentReason.trim().length < 8 ||
                  (incidentActionType === "assigned" && !incidentAssignee.trim())
                }
              >
                {action === "incident" ? (
                  <LoaderCircle size={15} className="animate-spin" aria-hidden="true" />
                ) : (
                  <ShieldCheck size={15} aria-hidden="true" />
                )}
                Record action
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}

function SLOHistory({
  evaluations,
  snapshots,
  minimumSamples
}: {
  evaluations: OperationalSLOEvaluation[];
  snapshots: OperationalSnapshotSummary[];
  minimumSamples: number;
}) {
  return (
    <div className="space-y-6 pt-5">
      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Objective</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Long window</th>
                <th className="px-4 py-3">Short window</th>
                <th className="px-4 py-3">Burn</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Error budget</th>
                <th className="px-4 py-3">Samples</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.map((evaluation) => (
                <tr key={evaluation.id} className="border-t border-line align-top">
                  <td className="px-4 py-4">
                    <div className="font-medium text-ink">{sloLabel(evaluation.slo_key)}</div>
                    <div className="mt-1 text-xs text-neutral-500">{evaluation.scope}</div>
                  </td>
                  <td className="px-4 py-4">
                    <Badge tone={sloTone(evaluation.status)}>{evaluation.status}</Badge>
                  </td>
                  <td className="px-4 py-4 font-semibold text-ink">
                    {formatOptionalPercent(evaluation.observed_ratio)}
                    <div className="mt-1 text-xs font-normal text-neutral-500">
                      {formatDuration(evaluation.window_seconds)}
                    </div>
                  </td>
                  <td className="px-4 py-4 font-semibold text-ink">
                    {formatOptionalPercent(evaluation.short_observed_ratio)}
                    <div className="mt-1 text-xs font-normal text-neutral-500">
                      {formatDuration(evaluation.short_window_seconds)}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2">
                      <Flame size={15} className="text-neutral-400" aria-hidden="true" />
                      <Badge tone={burnTone(evaluation.burn_alert_level)}>
                        {evaluation.burn_alert_level}
                      </Badge>
                    </div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">
                      {formatBurnRate(evaluation.burn_rate)} /{" "}
                      {formatBurnRate(evaluation.short_burn_rate)}
                    </div>
                  </td>
                  <td className="px-4 py-4">{formatPercent(evaluation.target_ratio)}</td>
                  <td className="w-48 px-4 py-4">
                    <div className="h-2 overflow-hidden rounded bg-neutral-100">
                      <div
                        className={`h-full ${
                          (evaluation.error_budget_remaining_ratio ?? 0) > 0.25
                            ? "bg-teal-600"
                            : "bg-rose-600"
                        }`}
                        style={{
                          width: `${Math.round(
                            (evaluation.error_budget_remaining_ratio ?? 0) * 100
                          )}%`
                        }}
                      />
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {formatOptionalPercent(evaluation.error_budget_remaining_ratio)}
                    </div>
                  </td>
                  <td className="px-4 py-4 text-xs text-neutral-600">
                    {evaluation.good_sample_count}/{evaluation.sample_count}
                    <div className="mt-1">minimum {minimumSamples}</div>
                  </td>
                </tr>
              ))}
              {!evaluations.length ? (
                <tr className="border-t border-line">
                  <td className="px-4 py-6 text-neutral-600" colSpan={8}>
                    No SLO evaluations captured yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Snapshot continuity</h2>
          <span className="text-xs text-neutral-500">oldest to newest</span>
        </div>
        <div className="flex h-10 items-end gap-1" aria-label="Snapshot health history">
          {[...snapshots]
            .slice(0, 40)
            .reverse()
            .map((snapshot) => (
              <div
                key={snapshot.id}
                className={`min-w-1 flex-1 rounded-t ${snapshotBarTone(snapshot.health)}`}
                style={{
                  height: `${Math.max(25, 100 - snapshot.alert_count * 14)}%`
                }}
                title={`${formatDate(snapshot.generated_at)} | ${snapshot.health} | ${snapshot.alert_count} alerts`}
              />
            ))}
          {!snapshots.length ? (
            <div className="text-xs text-neutral-500">No retained snapshots.</div>
          ) : null}
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Recent Snapshots
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Captured</th>
                <th className="px-4 py-3">Health</th>
                <th className="px-4 py-3">Workers</th>
                <th className="px-4 py-3">Queue</th>
                <th className="px-4 py-3">Identity hygiene</th>
                <th className="px-4 py-3">Hash</th>
              </tr>
            </thead>
            <tbody>
              {snapshots.slice(0, 15).map((snapshot) => (
                <tr key={snapshot.id} className="border-t border-line">
                  <td className="px-4 py-3 text-xs">{formatDate(snapshot.generated_at)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={healthTone(snapshot.health)}>{snapshot.health}</Badge>
                  </td>
                  <td className="px-4 py-3 font-semibold">{snapshot.worker_online}</td>
                  <td className="px-4 py-3">{snapshot.queue_depth}</td>
                  <td className="px-4 py-3 text-xs text-neutral-600">
                    due {snapshot.identity_retention_due} | tokens{" "}
                    {snapshot.identity_inactive_provider_token}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-500">
                    {snapshot.content_hash.slice(0, 12)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function IncidentTable({
  incidents,
  actions,
  canAdminister,
  onAction
}: {
  incidents: OperationalAlertIncident[];
  actions: OperationalAlertIncidentAction[];
  canAdminister: boolean;
  onAction: (incident: OperationalAlertIncident, actionType: IncidentActionType) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft mt-5">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1120px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Incident</th>
              <th className="px-4 py-3">State</th>
              <th className="px-4 py-3">Severity</th>
              <th className="px-4 py-3">Response</th>
              <th className="px-4 py-3">Owner</th>
              <th className="px-4 py-3">Occurrences</th>
              <th className="px-4 py-3">Last seen</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.id} className="border-t border-line align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{incident.alert_key}</div>
                  <div className="mt-1 max-w-md text-xs text-neutral-500">
                    {incident.summary}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={incident.status === "open" ? "amber" : "teal"}>
                    {incident.status}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={incident.severity === "critical" ? "rose" : "amber"}>
                    {incident.severity}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={incident.acknowledged_at ? "teal" : "amber"}>
                    {incident.acknowledged_at ? "acknowledged" : "unacknowledged"}
                  </Badge>
                  <div className="mt-1 text-xs text-neutral-500">
                    escalation L{incident.escalation_level}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-600">
                  {incident.assigned_to ?? "Unassigned"}
                </td>
                <td className="px-4 py-3">{incident.occurrence_count}</td>
                <td className="px-4 py-3 text-xs">{formatDate(incident.last_seen_at)}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                      onClick={() => onAction(incident, "acknowledged")}
                      disabled={
                        !canAdminister ||
                        incident.status !== "open" ||
                        incident.acknowledged_at !== null
                      }
                      title="Acknowledge incident"
                      aria-label="Acknowledge incident"
                    >
                      <UserCheck size={16} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                      onClick={() => onAction(incident, "assigned")}
                      disabled={!canAdminister || incident.status !== "open"}
                      title="Assign incident"
                      aria-label="Assign incident"
                    >
                      <UserRoundPlus size={16} aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                      onClick={() => onAction(incident, "note")}
                      disabled={!canAdminister}
                      title="Add incident note"
                      aria-label="Add incident note"
                    >
                      <MessageSquareText size={16} aria-hidden="true" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!incidents.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-neutral-600" colSpan={8}>
                  No operational incidents.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="border-t border-line">
        <div className="flex items-center gap-2 px-4 py-3 text-sm font-semibold text-ink">
          <History size={16} className="text-neutral-500" aria-hidden="true" />
          Response history
        </div>
        <div className="divide-y divide-line">
          {actions.slice(0, 12).map((incidentAction) => (
            <div
              key={incidentAction.id}
              className="grid gap-2 px-4 py-3 text-xs sm:grid-cols-[140px_1fr_180px]"
            >
              <div>
                <Badge tone={incidentActionTone(incidentAction.action_type)}>
                  {incidentAction.action_type}
                </Badge>
              </div>
              <div className="min-w-0">
                <div className="text-neutral-700">{incidentAction.reason}</div>
                <div className="mt-1 truncate font-mono text-neutral-400">
                  {incidentAction.action_hash.slice(0, 16)}
                </div>
              </div>
              <div className="text-neutral-500 sm:text-right">
                <div>{incidentActor(incidentAction)}</div>
                <div className="mt-1">{formatDate(incidentAction.occurred_at)}</div>
              </div>
            </div>
          ))}
          {!actions.length ? (
            <div className="px-4 py-5 text-xs text-neutral-500">
              No incident response actions recorded.
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function DeliveryTable({ deliveries }: { deliveries: OperationalAlertDelivery[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft mt-5">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1160px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Delivery</th>
              <th className="px-4 py-3">Transition</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Attempts</th>
              <th className="px-4 py-3">Response</th>
              <th className="px-4 py-3">Provider receipt</th>
              <th className="px-4 py-3">Delivered</th>
              <th className="px-4 py-3">Signing key</th>
              <th className="px-4 py-3">Destination</th>
            </tr>
          </thead>
          <tbody>
            {deliveries.map((delivery) => (
              <tr key={delivery.id} className="border-t border-line">
                <td className="px-4 py-3 font-mono text-xs">{delivery.id.slice(0, 12)}</td>
                <td className="px-4 py-3">{delivery.transition_type}</td>
                <td className="px-4 py-3">
                  <Badge tone={deliveryTone(delivery.status)}>{delivery.status}</Badge>
                </td>
                <td className="px-4 py-3">{delivery.attempt_count}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {delivery.response_status ?? "pending"}
                </td>
                <td className="px-4 py-3 text-xs">
                  <div className="font-medium text-neutral-700">
                    {delivery.provider_name ?? "-"}
                  </div>
                  <div
                    className="mt-1 max-w-52 truncate font-mono text-neutral-500"
                    title={delivery.provider_receipt_id ?? undefined}
                  >
                    {delivery.provider_receipt_id ?? "pending"}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs">
                  {delivery.delivered_at ? formatDate(delivery.delivered_at) : "-"}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                  {delivery.signing_key_id}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-500">
                  {delivery.destination_fingerprint}
                </td>
              </tr>
            ))}
            {!deliveries.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-neutral-600" colSpan={9}>
                  No paging delivery receipts.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StagingReadinessBand({
  readiness
}: {
  readiness: OperationalStagingReadiness;
}) {
  return (
    <section className="border-b border-line pb-5" aria-label="Staging readiness">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={17} className="text-neutral-500" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-ink">Staging readiness</h2>
          <Badge tone={readiness.ready ? "teal" : "amber"}>
            {readiness.ready ? "ready" : `${readiness.failed_count} blocked`}
          </Badge>
        </div>
        {readiness.latest_receipt_delivery_id ? (
          <span className="font-mono text-xs text-neutral-500">
            receipt {readiness.latest_receipt_delivery_id.slice(0, 12)}
          </span>
        ) : null}
      </div>
      <div className="grid border-y border-line sm:grid-cols-2 xl:grid-cols-4">
        {readiness.checks.map((check) => (
          <div
            key={check.key}
            className="min-w-0 border-b border-line px-3 py-3 last:border-b-0 sm:border-r xl:[&:nth-child(4n)]:border-r-0"
          >
            <div className="flex items-center gap-2">
              {check.key.includes("key") || check.key.includes("rotation") ? (
                <KeyRound
                  size={14}
                  className={check.status === "passed" ? "text-teal-600" : "text-amber-600"}
                  aria-hidden="true"
                />
              ) : (
                <ReceiptText
                  size={14}
                  className={check.status === "passed" ? "text-teal-600" : "text-amber-600"}
                  aria-hidden="true"
                />
              )}
              <span className="truncate text-xs font-semibold text-ink">
                {readinessLabel(check.key)}
              </span>
            </div>
            <p className="mt-1 text-xs leading-5 text-neutral-600">{check.summary}</p>
            {check.evidence ? (
              <p className="mt-1 truncate font-mono text-[11px] text-neutral-400">
                {check.evidence}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function TabButton({
  active,
  icon,
  label,
  onClick
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
        active ? "bg-white text-ink shadow-sm" : "text-neutral-600"
      }`}
      onClick={onClick}
    >
      {icon}
      {label}
    </button>
  );
}

function healthTone(health: "healthy" | "degraded" | "critical") {
  if (health === "healthy") return "teal" as const;
  if (health === "degraded") return "amber" as const;
  return "rose" as const;
}

function sloTone(status: OperationalSLOEvaluation["status"]) {
  if (status === "met") return "teal" as const;
  if (status === "insufficient") return "amber" as const;
  return "rose" as const;
}

function deliveryTone(status: OperationalAlertDelivery["status"]) {
  if (status === "delivered") return "teal" as const;
  if (status === "queued") return "amber" as const;
  return "rose" as const;
}

function burnTone(level: OperationalSLOEvaluation["burn_alert_level"]) {
  if (level === "critical") return "rose" as const;
  if (level === "warning") return "amber" as const;
  return "teal" as const;
}

function incidentActionTone(actionType: OperationalAlertIncidentAction["action_type"]) {
  if (actionType === "escalated") return "rose" as const;
  if (actionType === "acknowledged") return "teal" as const;
  if (actionType === "assigned") return "violet" as const;
  return "neutral" as const;
}

function incidentActor(action: OperationalAlertIncidentAction) {
  const displayName = action.actor_identity_json.display_name;
  const subjectId = action.actor_identity_json.subject_id;
  if (typeof displayName === "string" && displayName) return displayName;
  if (typeof subjectId === "string" && subjectId) return subjectId;
  return "Unknown actor";
}

function incidentActionLabel(actionType: IncidentActionType) {
  if (actionType === "acknowledged") return "Acknowledgement";
  if (actionType === "assigned") return "Assignment";
  return "Note";
}

function readinessLabel(key: string) {
  const labels: Record<string, string> = {
    paging_enabled: "Paging control",
    secure_destination: "HTTPS destination",
    ca_verification: "CA verification",
    projected_keyring: "Secret projection",
    rolling_key_rotation: "Rolling rotation",
    provider_receipt_contract: "Receipt contract",
    recent_provider_receipt: "End-to-end receipt"
  };
  return labels[key] ?? key.replaceAll("_", " ");
}

function defaultIncidentReason(actionType: IncidentActionType) {
  if (actionType === "acknowledged") {
    return "Acknowledge the active incident and begin investigation";
  }
  if (actionType === "assigned") return "Assign incident response ownership";
  return "Record an incident investigation update";
}

function snapshotBarTone(health: OperationalSnapshotSummary["health"]) {
  if (health === "healthy") return "bg-teal-500";
  if (health === "degraded") return "bg-amber-500";
  return "bg-rose-500";
}

function sloLabel(key: string) {
  if (key === "identity_session_hygiene") return "Identity session hygiene";
  if (key === "worker_control_plane_availability") return "Worker control-plane availability";
  return key.replaceAll("_", " ");
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function formatOptionalPercent(value: number | null) {
  return value === null ? "collecting" : formatPercent(value);
}

function formatBurnRate(value: number | null) {
  return value === null ? "collecting" : `${value.toFixed(2)}x`;
}

function formatDuration(seconds: number) {
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

async function responseMessage(response: Response) {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string | Array<{ msg?: string }> }
    | null;
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item.msg).filter(Boolean).join(", ");
  }
  return `Request failed with HTTP ${response.status}.`;
}
