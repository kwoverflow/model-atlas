"use client";

import {
  Ban,
  Clock3,
  ExternalLink,
  Play,
  ShieldCheck,
  ShieldX,
  UserRoundCheck
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/Badge";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type {
  AgentApprovalCheckpoint,
  AgentExecutionJob,
  OperatorIdentity
} from "@/types/api";

type Operation = "decide" | "revoke" | "resume";

export function AgentApprovalControlPanel({
  checkpoints
}: {
  checkpoints: AgentApprovalCheckpoint[];
}) {
  const [records, setRecords] = useState(checkpoints);
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Record<string, AgentExecutionJob>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const pendingCount = useMemo(
    () => records.filter((record) => record.status === "pending").length,
    [records]
  );

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

  function replaceRecord(record: AgentApprovalCheckpoint) {
    setRecords((current) =>
      current.map((item) => (item.id === record.id ? record : item))
    );
  }

  async function decide(
    record: AgentApprovalCheckpoint,
    decision: "approved" | "denied"
  ) {
    const reason = reasons[record.id]?.trim();
    if (!reason) return;
    setBusyId(record.id);
    setNotice(null);
    const response = await browserApiFetch(
      `${API_BASE_URL}/agents/checkpoints/${record.id}/decision`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          decision,
          reason,
          expected_version: record.version
        })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusyId(null);
      return;
    }
    replaceRecord((await response.json()) as AgentApprovalCheckpoint);
    setBusyId(null);
    if (decision === "denied") {
      window.location.reload();
    }
  }

  async function revoke(record: AgentApprovalCheckpoint) {
    const reason = reasons[record.id]?.trim();
    if (!reason) return;
    setBusyId(record.id);
    setNotice(null);
    const response = await browserApiFetch(
      `${API_BASE_URL}/agents/checkpoints/${record.id}/revoke`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason, expected_version: record.version })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusyId(null);
      return;
    }
    replaceRecord((await response.json()) as AgentApprovalCheckpoint);
    setBusyId(null);
  }

  async function resume(record: AgentApprovalCheckpoint) {
    setBusyId(record.id);
    setNotice(null);
    const response = await browserApiFetch(
      `${API_BASE_URL}/agents/checkpoints/${record.id}/resume-jobs`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_version: record.version })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusyId(null);
      return;
    }
    const queuedJob = (await response.json()) as AgentExecutionJob;
    setJobs((current) => ({ ...current, [record.id]: queuedJob }));
    const job = await pollAgentJob(queuedJob, (polledJob) =>
      setJobs((current) => ({ ...current, [record.id]: polledJob }))
    );
    setBusyId(null);
    if (job.status === "completed" && job.result_json?.benchmark_run_id) {
      window.location.assign(`/benchmark-executions/${job.result_json.benchmark_run_id}`);
      return;
    }
    if (job.status === "failed" || job.status === "cancelled") {
      setNotice(job.last_error ?? `Resume job ${job.status}.`);
      return;
    }
    setNotice("Resume job remains queued. The durable worker will continue processing it.");
  }

  return (
    <div className="border-b border-line">
      <div className="flex flex-wrap items-start justify-between gap-3 bg-neutral-50 px-5 py-4">
        <div>
          <div className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <ShieldCheck size={16} aria-hidden="true" /> Agent approval control
          </div>
          <div className="mt-1 text-xs text-neutral-500">
            {records.length} checkpoints / {pendingCount} pending
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
          <UserRoundCheck size={15} aria-hidden="true" />
          <span className="font-medium">{identity?.display_name ?? "Checking operator"}</span>
          <span>{identity?.role ?? "role unavailable"}</span>
          <Badge tone={identity?.identity_verified ? "teal" : "amber"}>
            {identity?.identity_verified ? "Verified" : "Unverified"}
          </Badge>
        </div>
      </div>

      {notice ? (
        <div className="border-t border-rose bg-rose/5 px-5 py-3 text-sm text-rose">
          {notice}
        </div>
      ) : null}

      <div className="divide-y divide-line">
        {records.map((record) => {
          const decisionAllowed = operationAllowed(record, identity, "decide");
          const revokeAllowed = operationAllowed(record, identity, "revoke");
          const resumeAllowed = operationAllowed(record, identity, "resume");
          const reason = reasons[record.id] ?? "";
          const busy = busyId === record.id;
          const job = jobs[record.id];
          return (
            <section key={record.id} className="px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-neutral-500">
                    {String(record.request_snapshot_json.sample_id ?? "agent case")}
                  </div>
                  <h4 className="mt-1 break-words text-sm font-semibold text-ink">
                    {record.checkpoint_id}
                  </h4>
                </div>
                <div className="flex items-center gap-2">
                  {job ? (
                    <Badge tone={jobTone(job.status)}>{statusLabel(job.status)}</Badge>
                  ) : null}
                  <Badge tone={statusTone(record.status)}>{statusLabel(record.status)}</Badge>
                </div>
              </div>

              <div className="mt-3 grid gap-3 text-xs text-neutral-600 md:grid-cols-2 xl:grid-cols-4">
                <Evidence label="Requester" value={record.requested_by_subject_id} />
                <Evidence
                  label="Expires"
                  value={formatTimestamp(record.expires_at)}
                  icon={Clock3}
                />
                <Evidence
                  label="Policy"
                  value={record.approval_policy_json.policy_version}
                />
                <Evidence label="Request hash" value={record.request_hash} mono />
              </div>

              <div className="mt-3 text-xs leading-5 text-neutral-500">
                Approvers: {record.approval_policy_json.allowed_roles.join(", ")} / Resume: {" "}
                {record.approval_policy_json.resume_roles.join(", ")}
                {record.approval_policy_json.separation_of_duties
                  ? " / separation of duties"
                  : ""}
              </div>

              {record.status === "pending" || record.status === "approved" ? (
                <div className="mt-4 flex flex-wrap items-end gap-3">
                  {record.status === "pending" || revokeAllowed ? (
                    <label className="grid min-w-[260px] flex-1 gap-1.5 text-xs font-medium text-neutral-600">
                      Decision reason
                      <input
                        value={reason}
                        onChange={(event) =>
                          setReasons((current) => ({
                            ...current,
                            [record.id]: event.target.value
                          }))
                        }
                        maxLength={1000}
                        className="h-9 rounded-md border border-line bg-white px-3 text-sm"
                      />
                    </label>
                  ) : null}
                  {record.status === "pending" ? (
                    <>
                      <button
                        type="button"
                        onClick={() => void decide(record, "approved")}
                        disabled={!decisionAllowed || !reason.trim() || busy}
                        className="inline-flex h-9 items-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white disabled:opacity-50"
                      >
                        <ShieldCheck size={15} aria-hidden="true" /> Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => void decide(record, "denied")}
                        disabled={!decisionAllowed || !reason.trim() || busy}
                        className="inline-flex h-9 items-center gap-2 rounded-md border border-rose px-3 text-sm font-medium text-rose disabled:opacity-50"
                      >
                        <ShieldX size={15} aria-hidden="true" /> Deny
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => void resume(record)}
                        disabled={!resumeAllowed || busy}
                        className="inline-flex h-9 items-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white disabled:opacity-50"
                      >
                        <Play size={15} aria-hidden="true" /> Queue resume
                      </button>
                      <button
                        type="button"
                        onClick={() => void revoke(record)}
                        disabled={!revokeAllowed || !reason.trim() || busy}
                        className="inline-flex h-9 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium text-neutral-700 disabled:opacity-50"
                      >
                        <Ban size={15} aria-hidden="true" /> Revoke
                      </button>
                    </>
                  )}
                </div>
              ) : null}

              {!operationAllowed(record, identity, record.status === "approved" ? "resume" : "decide") &&
              ["pending", "approved"].includes(record.status) ? (
                <div className="mt-2 text-xs text-amber">
                  Verified policy role or separation-of-duties requirement is not satisfied.
                </div>
              ) : null}

              {record.decision_hash || record.revocation_hash || record.resume_hash ? (
                <details className="mt-3 text-xs text-neutral-500">
                  <summary className="cursor-pointer font-medium">Transition evidence</summary>
                  <div className="mt-2 grid gap-1 break-all font-mono">
                    {record.decision_hash ? <span>decision {record.decision_hash}</span> : null}
                    {record.revocation_hash ? <span>revoke {record.revocation_hash}</span> : null}
                    {record.resume_hash ? <span>resume {record.resume_hash}</span> : null}
                  </div>
                </details>
              ) : null}

              {record.transition_benchmark_run_id ? (
                <a
                  href={`/benchmark-executions/${record.transition_benchmark_run_id}`}
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-teal"
                >
                  Open result revision <ExternalLink size={13} aria-hidden="true" />
                </a>
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function pollAgentJob(
  initialJob: AgentExecutionJob,
  onPoll: (job: AgentExecutionJob) => void
): Promise<AgentExecutionJob> {
  let currentJob = initialJob;
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if (["completed", "failed", "cancelled"].includes(currentJob.status)) break;
    await delay(1000);
    const response = await browserApiFetch(`${API_BASE_URL}/agents/jobs/${currentJob.id}`, {
      cache: "no-store"
    }).catch(() => null);
    if (!response?.ok) continue;
    currentJob = (await response.json()) as AgentExecutionJob;
    onPoll(currentJob);
  }
  return currentJob;
}

function jobTone(status: AgentExecutionJob["status"]): "amber" | "teal" | "rose" {
  if (status === "completed") return "teal";
  if (status === "failed" || status === "cancelled") return "rose";
  return "amber";
}

function operationAllowed(
  record: AgentApprovalCheckpoint,
  identity: OperatorIdentity | null,
  operation: Operation
): boolean {
  if (!identity) return false;
  const policy = record.approval_policy_json;
  if (policy.requires_verified_identity && !identity.identity_verified) return false;
  const allowedRoles = operation === "resume" ? policy.resume_roles : policy.allowed_roles;
  const role = identity.role?.trim().toLowerCase();
  if (!role || !allowedRoles.some((allowed) => allowed.trim().toLowerCase() === role)) {
    return false;
  }
  return !(
    operation === "decide" &&
    policy.separation_of_duties &&
    identity.subject_id === record.requested_by_subject_id
  );
}

function Evidence({
  label,
  value,
  mono = false,
  icon: Icon
}: {
  label: string;
  value: string;
  mono?: boolean;
  icon?: typeof Clock3;
}) {
  return (
    <div className="min-w-0 border-b border-line pb-2">
      <div className="inline-flex items-center gap-1 font-semibold uppercase text-neutral-400">
        {Icon ? <Icon size={12} aria-hidden="true" /> : null}
        {label}
      </div>
      <div className={`mt-1 truncate ${mono ? "font-mono" : ""}`} title={value}>
        {value}
      </div>
    </div>
  );
}

async function responseError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string | Array<{ msg?: string }>;
  } | null;
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item.msg).find(Boolean) ?? "Checkpoint action failed";
  }
  return "Checkpoint action failed";
}

function formatTimestamp(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}
