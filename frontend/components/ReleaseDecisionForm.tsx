"use client";

import { FileCheck2, ShieldCheck } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import {
  canApproveRelease,
  canOperatorApproveRelease,
  canOperatorSignDecision,
  operatorDecisionReason,
  operatorApprovalReason,
  releaseDecisionActionLabels
} from "@/lib/releaseDecisionPresentation";
import type {
  OperatorIdentity,
  ReleaseDecisionType,
  ReleaseReadinessStatus
} from "@/types/api";

type ReleaseDecisionFormProps = {
  gateEvaluationId: string;
  readinessStatus: ReleaseReadinessStatus;
  replacesReleaseDecisionId?: string;
};

type ErrorDetail = {
  msg?: string;
};

function initialDecision(status: ReleaseReadinessStatus): ReleaseDecisionType {
  return canApproveRelease(status) ? "APPROVE_RELEASE" : "REQUEST_CHANGES";
}

function errorMessage(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "Decision failed";
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return (
      detail
        .map((item: ErrorDetail) => item.msg)
        .find((message): message is string => Boolean(message)) ?? "Decision failed"
    );
  }
  return "Decision failed";
}

export function ReleaseDecisionForm({
  gateEvaluationId,
  readinessStatus,
  replacesReleaseDecisionId
}: ReleaseDecisionFormProps) {
  const [decision, setDecision] = useState<ReleaseDecisionType>(
    initialDecision(readinessStatus)
  );
  const [decidedBy, setDecidedBy] = useState("local-ui");
  const [signerRole, setSignerRole] = useState("Release Manager");
  const [ticketReference, setTicketReference] = useState("");
  const [signatureStatement, setSignatureStatement] = useState(
    "I reviewed the frozen readiness snapshot and accept responsibility for this release decision."
  );
  const [decisionReason, setDecisionReason] = useState(
    canApproveRelease(readinessStatus)
      ? "Reviewed readiness snapshot and approved release sign-off."
      : "Readiness snapshot requires follow-up before release sign-off."
  );
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [operatorIdentity, setOperatorIdentity] = useState<OperatorIdentity | null>(null);
  const operatorCanApprove = canOperatorApproveRelease(operatorIdentity);
  const selectedDecisionAllowed = canOperatorSignDecision(operatorIdentity, decision);
  const releaseCanBeApproved = canApproveRelease(readinessStatus) && operatorCanApprove;
  const approvalBlocked = decision === "APPROVE_RELEASE" && !releaseCanBeApproved;
  const policyBlocked = !selectedDecisionAllowed;
  const submitBlocked =
    approvalBlocked ||
    policyBlocked ||
    !decidedBy.trim() ||
    !decisionReason.trim() ||
    !signatureStatement.trim() ||
    !gateEvaluationId;

  useEffect(() => {
    let active = true;
    async function loadOperatorIdentity() {
      const response = await browserApiFetch(`${API_BASE_URL}/operator-identity/me`, {
        cache: "no-store"
      }).catch(() => null);
      if (!active || !response?.ok) return;
      const payload = (await response.json()) as OperatorIdentity;
      setOperatorIdentity(payload);
      if (payload.identity_verified) {
        setDecidedBy(payload.display_name);
        setSignerRole(payload.role ?? "");
      }
      const payloadCanApprove =
        canApproveRelease(readinessStatus) &&
        payload.release_permissions.decisions.APPROVE_RELEASE.allowed;
      setDecision((current) => {
        if (payloadCanApprove && current === "REQUEST_CHANGES") {
          return "APPROVE_RELEASE";
        }
        if (
          current === "APPROVE_RELEASE" &&
          !payloadCanApprove
        ) {
          return "REQUEST_CHANGES";
        }
        if (!payload.release_permissions.decisions[current].allowed) {
          return "REQUEST_CHANGES";
        }
        return current;
      });
    }
    void loadOperatorIdentity();
    return () => {
      active = false;
    };
  }, [readinessStatus]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Signing");
    const response = await browserApiFetch(`${API_BASE_URL}/release-decisions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        gate_evaluation_id: gateEvaluationId,
        decision,
        decided_by: decidedBy,
        signer_role: signerRole.trim() || null,
        ticket_reference: ticketReference.trim() || null,
        signature_statement: signatureStatement,
        decision_reason: decisionReason,
        notes: notes.trim() || null,
        replaces_release_decision_id: replacesReleaseDecisionId ?? null
      })
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as unknown;
      setStatus(errorMessage(payload));
      return;
    }
    window.location.href = `/release-decisions?gate_evaluation_id=${gateEvaluationId}`;
  }

  return (
    <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">Signed Release Decision</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
            Freeze this readiness snapshot as an auditable release decision record.
          </p>
          {replacesReleaseDecisionId ? (
            <div className="mt-2 font-mono text-xs text-amber">
              replaces {replacesReleaseDecisionId.slice(0, 8)}
            </div>
          ) : null}
        </div>
        <div className="font-mono text-xs text-neutral-500">{gateEvaluationId.slice(0, 8)}</div>
      </div>
      <form onSubmit={submit} className="mt-4 grid gap-4 lg:grid-cols-2">
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Decision
          <select
            value={decision}
            onChange={(event) => setDecision(event.target.value as ReleaseDecisionType)}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm"
          >
            <option value="APPROVE_RELEASE" disabled={!releaseCanBeApproved}>
              {releaseDecisionActionLabels.APPROVE_RELEASE}
            </option>
            <option value="REQUEST_CHANGES">
              {releaseDecisionActionLabels.REQUEST_CHANGES}
            </option>
            <option
              value="REJECT_RELEASE"
              disabled={!canOperatorSignDecision(operatorIdentity, "REJECT_RELEASE")}
            >
              {releaseDecisionActionLabels.REJECT_RELEASE}
            </option>
          </select>
        </label>
        <div className="rounded-md border border-line bg-neutral-50 p-3 text-sm text-neutral-700 lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2">
            <ShieldCheck size={16} aria-hidden="true" />
            <span className="font-medium">
              {operatorIdentity?.display_name ?? "Checking operator"}
            </span>
            <span className="text-neutral-500">
              {operatorIdentity?.identity_verified ? "verified" : "self-attested"}
            </span>
            <span className="text-neutral-500">
              {operatorIdentity?.role ?? "role n/a"}
            </span>
          </div>
          <div className="mt-2 text-xs text-neutral-500">
            {decision === "APPROVE_RELEASE"
              ? operatorApprovalReason(operatorIdentity)
              : operatorDecisionReason(operatorIdentity, decision)}
          </div>
        </div>
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Decided by
          <input
            value={decidedBy}
            onChange={(event) => setDecidedBy(event.target.value)}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            maxLength={120}
            required
          />
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Role
          <input
            value={signerRole}
            onChange={(event) => setSignerRole(event.target.value)}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            maxLength={120}
          />
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Ticket
          <input
            value={ticketReference}
            onChange={(event) => setTicketReference(event.target.value)}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            maxLength={200}
          />
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700 lg:col-span-2">
          Signature statement
          <textarea
            value={signatureStatement}
            onChange={(event) => setSignatureStatement(event.target.value)}
            className="min-h-20 rounded-md border border-line bg-white px-3 py-2 text-sm"
            required
          />
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700 lg:col-span-2">
          Reason
          <textarea
            value={decisionReason}
            onChange={(event) => setDecisionReason(event.target.value)}
            className="min-h-24 rounded-md border border-line bg-white px-3 py-2 text-sm"
            required
          />
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700 lg:col-span-2">
          Notes
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className="min-h-20 rounded-md border border-line bg-white px-3 py-2 text-sm"
          />
        </label>
        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          <button
            type="submit"
            disabled={submitBlocked}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:opacity-50"
          >
            <FileCheck2 size={16} aria-hidden="true" />
            Sign Decision
          </button>
          {status ? <span className="text-sm text-neutral-600">{status}</span> : null}
        </div>
      </form>
    </section>
  );
}
