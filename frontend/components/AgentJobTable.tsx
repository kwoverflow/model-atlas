"use client";

import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/Badge";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type { AgentExecutionJob, OperatorIdentity } from "@/types/api";

const maintenanceRoles = new Set([
  "release manager",
  "ml ops lead",
  "sre lead",
  "admin",
  "system worker"
]);

export function AgentJobTable({
  jobs
}: {
  jobs: AgentExecutionJob[];
}) {
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadIdentity() {
      const response = await browserApiFetch(`${API_BASE_URL}/operator-identity/me`, {
        cache: "no-store"
      }).catch(() => null);
      if (!active || !response?.ok) return;
      setIdentity((await response.json()) as OperatorIdentity);
    }
    void loadIdentity();
    return () => {
      active = false;
    };
  }, []);

  const canRequeue =
    identity?.identity_verified === true &&
    maintenanceRoles.has((identity.role ?? "").toLowerCase());

  async function requeue(job: AgentExecutionJob) {
    const reason = reasons[job.id]?.trim();
    if (!reason || !canRequeue) return;
    setBusyId(job.id);
    setNotice(null);
    const response = await browserApiFetch(`${API_BASE_URL}/agents/jobs/${job.id}/requeue`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reason })
    });
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusyId(null);
      return;
    }
    window.location.reload();
  }

  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Execution jobs</h2>
        <Badge tone={canRequeue ? "teal" : "neutral"}>
          {canRequeue ? identity?.role ?? "Verified operator" : "Read only"}
        </Badge>
      </div>
      {notice ? (
        <div className="border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {notice}
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-[1120px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Job</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Attempts</th>
              <th className="px-4 py-3">Heartbeat</th>
              <th className="px-4 py-3">Worker</th>
              <th className="px-4 py-3">Updated</th>
              <th className="px-4 py-3">Failure</th>
              <th className="px-4 py-3">Operation</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {jobs.map((job) => {
              const reason = reasons[job.id] ?? "";
              return (
                <tr key={job.id} className="align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">
                      {jobTypeLabel(job.job_type)}
                    </div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">
                      {job.id.slice(0, 8)}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(job.status)}>
                      {statusLabel(job.status)}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums text-neutral-700">
                    {job.attempt_count}/{job.max_attempts}
                    {job.requeue_count ? (
                      <div className="mt-1 text-xs text-neutral-500">
                        requeued {job.requeue_count}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 tabular-nums text-neutral-700">
                    {job.heartbeat_count}
                    <div className="mt-1 text-xs text-neutral-500">
                      {formatDate(job.last_heartbeat_at)}
                    </div>
                  </td>
                  <td className="max-w-44 break-all px-4 py-3 font-mono text-xs text-neutral-600">
                    {job.lease_owner ?? "unassigned"}
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-600">
                    {formatDate(job.updated_at)}
                  </td>
                  <td className="max-w-64 px-4 py-3 text-xs leading-5 text-rose-800">
                    {job.dead_letter_reason ?? job.last_error ?? "None"}
                  </td>
                  <td className="w-72 px-4 py-3">
                    {job.status === "failed" ? (
                      <div className="flex items-center gap-2">
                        <input
                          value={reason}
                          onChange={(event) =>
                            setReasons((current) => ({
                              ...current,
                              [job.id]: event.target.value
                            }))
                          }
                          placeholder="Requeue reason"
                          className="h-9 min-w-0 flex-1 rounded-md border border-line px-3 text-xs"
                        />
                        <button
                          type="button"
                          title="Requeue failed job"
                          aria-label="Requeue failed job"
                          disabled={!canRequeue || !reason.trim() || busyId === job.id}
                          onClick={() => void requeue(job)}
                          className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-ink text-white disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <RotateCcw size={15} aria-hidden="true" />
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-neutral-400">No action</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!jobs.length ? (
        <div className="px-4 py-10 text-center text-sm text-neutral-500">
          No execution jobs.
        </div>
      ) : null}
    </section>
  );
}

function jobTypeLabel(value: AgentExecutionJob["job_type"]): string {
  return {
    resume_checkpoint: "Checkpoint resume",
    checkpoint_reconciliation: "Reconciliation",
    traffic_evidence_import: "Traffic evidence",
    model_validation_campaign: "Model validation",
    trust_source_sync: "Trust source sync",
    oidc_session_cleanup: "Session cleanup",
    operational_observability_cycle: "Observability cycle",
    operational_alert_delivery: "Alert delivery"
  }[value];
}

function formatDate(value: string | null): string {
  if (!value) return "not recorded";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

async function responseError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string }
    | null;
  return payload?.detail ?? `Request failed with status ${response.status}.`;
}
