"use client";

import { Check, ClipboardCheck, ShieldX } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/Badge";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type {
  OperatorIdentity,
  ReleaseDecision,
  ReleaseDecisionAction
} from "@/types/api";

type ManualAction = "review_requested" | "acknowledged" | "revoked";

const reviewRoles = new Set([
  "release manager",
  "ml ops lead",
  "model governance",
  "admin",
  "qa lead",
  "sre lead"
]);
const revokeRoles = new Set([
  "release manager",
  "ml ops lead",
  "model governance",
  "admin"
]);

export function ReleaseDecisionOperations({
  decision,
  actions
}: {
  decision: ReleaseDecision;
  actions: ReleaseDecisionAction[];
}) {
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [reason, setReason] = useState("");
  const [busyAction, setBusyAction] = useState<ManualAction | null>(null);
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

  const role = (identity?.role ?? "").toLowerCase();
  const canReview = identity?.identity_verified === true && reviewRoles.has(role);
  const canRevoke = identity?.identity_verified === true && revokeRoles.has(role);
  const terminal =
    decision.operational_status === "revoked" ||
    decision.operational_status === "replaced";

  async function submit(actionType: ManualAction) {
    if (!reason.trim()) return;
    setBusyAction(actionType);
    setNotice(null);
    const response = await browserApiFetch(
      `${API_BASE_URL}/release-decisions/${decision.id}/actions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action_type: actionType,
          reason: reason.trim()
        })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusyAction(null);
      return;
    }
    window.location.reload();
  }

  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <h2 className="text-lg font-semibold text-ink">Release Operations</h2>
        <Badge tone={statusTone(decision.operational_status)}>
          {statusLabel(decision.operational_status)}
        </Badge>
      </div>
      {decision.stale_warning ? (
        <div className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900">
          The signed Gate evidence is stale and requires an operational review.
        </div>
      ) : null}
      <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
        <div>
          <div className="text-xs font-semibold uppercase text-neutral-500">
            Action history
          </div>
          <div className="mt-3 divide-y divide-line border-y border-line">
            {actions.map((action) => (
              <div key={action.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge tone={statusTone(action.action_type)}>
                    {statusLabel(action.action_type)}
                  </Badge>
                  <span className="text-xs text-neutral-500">
                    {formatDate(action.occurred_at)}
                  </span>
                </div>
                <div className="mt-2 text-sm leading-6 text-neutral-700">
                  {action.reason}
                </div>
                <div className="mt-1 text-xs text-neutral-500">
                  {String(
                    action.actor_identity_json.display_name ??
                      action.actor_identity_json.subject_id ??
                      "system"
                  )}
                </div>
              </div>
            ))}
            {!actions.length ? (
              <div className="py-8 text-center text-sm text-neutral-500">
                No operational actions.
              </div>
            ) : null}
          </div>
        </div>

        <div>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Reason
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="min-h-24 rounded-md border border-line px-3 py-2 text-sm"
              maxLength={2000}
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!canReview || terminal || !reason.trim() || busyAction !== null}
              onClick={() => void submit("review_requested")}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium disabled:opacity-40"
            >
              <ClipboardCheck size={16} aria-hidden="true" />
              Request Review
            </button>
            <button
              type="button"
              disabled={
                !canReview ||
                decision.operational_status !== "needs_review" ||
                !reason.trim() ||
                busyAction !== null
              }
              onClick={() => void submit("acknowledged")}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium disabled:opacity-40"
            >
              <Check size={16} aria-hidden="true" />
              Acknowledge
            </button>
            <button
              type="button"
              disabled={
                !canRevoke ||
                terminal ||
                decision.decision !== "APPROVE_RELEASE" ||
                !reason.trim() ||
                busyAction !== null
              }
              onClick={() => void submit("revoked")}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-rose px-3 text-sm font-medium text-white disabled:opacity-40"
            >
              <ShieldX size={16} aria-hidden="true" />
              Revoke
            </button>
          </div>
          <div className="mt-3 text-xs text-neutral-500">
            {identity?.identity_verified
              ? `${identity.display_name} · ${identity.role ?? "role n/a"}`
              : "Verified release operations identity required"}
          </div>
          {notice ? (
            <div className="mt-3 text-sm text-rose-800">{notice}</div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function formatDate(value: string): string {
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
