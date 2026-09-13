export type StatusTone = "neutral" | "teal" | "amber" | "rose" | "violet";

export function statusTone(value: string | null | undefined): StatusTone {
  const status = (value ?? "").toLowerCase();
  if (
    status.includes("blocked") ||
    status.includes("fail") ||
    status.includes("invalid") ||
    status.includes("unverified") ||
    status.includes("error") ||
    status.includes("denied") ||
    status.includes("revoked") ||
    status.includes("expired") ||
    status.includes("offline") ||
    status.includes("stale") ||
    status === "not_production_ready"
  ) {
    return "rose";
  }
  if (
    status.includes("review") ||
    status.includes("conditional") ||
    status.includes("attention") ||
    status.includes("pending") ||
    status.includes("waiting") ||
    status.includes("queued") ||
    status.includes("leased") ||
    status.includes("running")
  ) {
    return "amber";
  }
  if (
    status.includes("approved") ||
    status.includes("ready") ||
    status.includes("complete") ||
    status.includes("active") ||
    status.includes("success") ||
    status.includes("pass") ||
    status.includes("recovered") ||
    status.includes("acknowledged") ||
    status.includes("online")
  ) {
    return "teal";
  }
  if (
    status.includes("synthetic") ||
    status.includes("insufficient") ||
    status.includes("replaced")
  ) {
    return "violet";
  }
  return "neutral";
}

export function statusLabel(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/(^|\s)\S/g, (letter) => letter.toUpperCase());
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
