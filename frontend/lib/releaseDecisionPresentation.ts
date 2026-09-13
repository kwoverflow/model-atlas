import type {
  ReleaseDecision,
  OperatorIdentity,
  ReleaseDecisionType,
  ReleaseReadinessStatus
} from "@/types/api";

export type Tone = "teal" | "amber" | "rose" | "violet";

export const releaseDecisionLabels: Record<ReleaseDecisionType, string> = {
  APPROVE_RELEASE: "Approved",
  REJECT_RELEASE: "Rejected",
  REQUEST_CHANGES: "Changes Requested"
};

export const releaseDecisionActionLabels: Record<ReleaseDecisionType, string> = {
  APPROVE_RELEASE: "Approve release",
  REJECT_RELEASE: "Reject release",
  REQUEST_CHANGES: "Request changes"
};

export function canApproveRelease(status: ReleaseReadinessStatus): boolean {
  return status === "READY" || status === "READY_TO_PROMOTE";
}

export function canOperatorApproveRelease(
  operatorIdentity: OperatorIdentity | null
): boolean {
  return canOperatorSignDecision(operatorIdentity, "APPROVE_RELEASE");
}

export function canOperatorSignDecision(
  operatorIdentity: OperatorIdentity | null,
  decision: ReleaseDecisionType
): boolean {
  if (!operatorIdentity) {
    return decision === "REQUEST_CHANGES";
  }
  return operatorIdentity.release_permissions.decisions[decision].allowed;
}

export function operatorApprovalReason(
  operatorIdentity: OperatorIdentity | null
): string {
  return operatorDecisionReason(operatorIdentity, "APPROVE_RELEASE");
}

export function operatorDecisionReason(
  operatorIdentity: OperatorIdentity | null,
  decision: ReleaseDecisionType
): string {
  const policy = operatorIdentity?.release_permissions.decisions[decision];
  if (!policy) return "Checking operator policy";
  if (policy.allowed) return "Operator can sign this decision";
  return policy.reasons[0] ?? "Operator cannot sign this decision";
}

export function releaseDecisionTone(
  decision: ReleaseDecision | ReleaseDecisionType
): Tone {
  const value = typeof decision === "string" ? decision : decision.decision;
  if (value === "APPROVE_RELEASE") return "teal";
  if (value === "REQUEST_CHANGES") return "amber";
  return "rose";
}

export function releaseReadinessTone(status: ReleaseReadinessStatus): Tone {
  if (status === "READY") return "teal";
  if (status === "READY_TO_PROMOTE") return "violet";
  if (status === "NEEDS_REVIEW") return "amber";
  return "rose";
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "none";
}
