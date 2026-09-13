"use client";

import {
  Ban,
  FileJson,
  Fingerprint,
  KeyRound,
  ReceiptText,
  Upload
} from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  ModelArtifactAttestation,
  ModelSupplyChainAttestation,
  OperatorIdentity,
  ProductionEvidenceReceipt,
  SupplyChainOverview
} from "@/types/api";

type SupplyChainConsoleProps = {
  overview: SupplyChainOverview;
  runtimeAttestations: ModelArtifactAttestation[];
  initialAttestations: ModelSupplyChainAttestation[];
  initialReceipts: ProductionEvidenceReceipt[];
};

export function SupplyChainConsole({
  overview,
  runtimeAttestations,
  initialAttestations,
  initialReceipts
}: SupplyChainConsoleProps) {
  const [mode, setMode] = useState<"attestation" | "receipt">("attestation");
  const [runtimeAttestationId, setRuntimeAttestationId] = useState(
    runtimeAttestations.find((item) => item.status === "verified")?.id ?? ""
  );
  const [signedStatement, setSignedStatement] = useState("");
  const [sbomJson, setSbomJson] = useState("");
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [revocationReason, setRevocationReason] = useState("");
  const [ticketReference, setTicketReference] = useState("");

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

  async function submitEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("Verifying signed evidence");
    let parsedSbom: Record<string, unknown> | null = null;
    if (mode === "attestation") {
      try {
        parsedSbom = JSON.parse(sbomJson) as Record<string, unknown>;
      } catch {
        setNotice("SBOM must be valid JSON");
        setBusy(false);
        return;
      }
    }
    const response = await browserApiFetch(
      `${API_BASE_URL}/supply-chain/${
        mode === "attestation" ? "model-attestations" : "production-receipts"
      }`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(
          mode === "attestation"
            ? {
                model_artifact_attestation_id: runtimeAttestationId,
                signed_statement_jws: signedStatement.trim(),
                sbom_json: parsedSbom
              }
            : { signed_statement_jws: signedStatement.trim() }
        )
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  async function revokeEvidence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!revokingId) return;
    setBusy(true);
    setNotice("Recording revocation");
    const response = await browserApiFetch(
      `${API_BASE_URL}/supply-chain/model-attestations/${revokingId}/revocations`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          reason: revocationReason.trim(),
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

  const verifiedOperator = identity?.identity_verified === true;

  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Active attestations"
          value={overview.verified_attestation_count}
          detail={`${overview.managed_attestation_count} managed / ${overview.production_eligible_attestation_count} eligible`}
          tone="teal"
        />
        <SummaryCard
          label="Revoked"
          value={overview.revoked_attestation_count}
          detail="append-only actions"
          tone={overview.revoked_attestation_count ? "rose" : "neutral"}
        />
        <SummaryCard
          label="Production receipts"
          value={overview.production_receipt_count}
          detail={`${overview.production_eligible_receipt_count} production eligible`}
          tone={overview.production_eligible_receipt_count ? "teal" : "violet"}
        />
        <SummaryCard
          label="Unverified production"
          value={overview.unverified_production_run_count}
          detail="excluded from trust"
          tone={overview.unverified_production_run_count ? "rose" : "teal"}
        />
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <KeyRound size={18} aria-hidden="true" />
            Trust Policy
          </h2>
          <div className="flex flex-wrap gap-2">
            <Badge tone={overview.publisher_trust_configured ? "teal" : "amber"}>
              publisher {overview.publisher_trust_configured ? "configured" : "unconfigured"}
            </Badge>
            <Badge
              tone={overview.production_evidence_trust_configured ? "teal" : "amber"}
            >
              collector {overview.production_evidence_trust_configured ? "configured" : "unconfigured"}
            </Badge>
            <Badge tone={verifiedOperator ? "teal" : "amber"}>
              {verifiedOperator ? identity?.role ?? "verified operator" : "operator required"}
            </Badge>
            <Badge tone={overview.transparency_proof_count ? "teal" : "amber"}>
              transparency {overview.transparency_proof_count}
            </Badge>
          </div>
        </div>

        <form onSubmit={submitEvidence} className="grid gap-4 p-5">
          <div className="inline-flex w-fit rounded-md border border-line bg-neutral-50 p-1">
            <button
              type="button"
              onClick={() => setMode("attestation")}
              aria-pressed={mode === "attestation"}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                mode === "attestation" ? "bg-white text-ink shadow-sm" : "text-neutral-500"
              }`}
            >
              <Fingerprint size={14} aria-hidden="true" />
              Model attestation
            </button>
            <button
              type="button"
              onClick={() => setMode("receipt")}
              aria-pressed={mode === "receipt"}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                mode === "receipt" ? "bg-white text-ink shadow-sm" : "text-neutral-500"
              }`}
            >
              <ReceiptText size={14} aria-hidden="true" />
              Production receipt
            </button>
          </div>

          {mode === "attestation" ? (
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Runtime attestation
              <select
                value={runtimeAttestationId}
                onChange={(event) => setRuntimeAttestationId(event.target.value)}
                className="h-10 w-full rounded-md border border-line bg-white px-3 text-sm"
              >
                {runtimeAttestations.map((attestation) => (
                  <option key={attestation.id} value={attestation.id}>
                    {attestation.runtime_model_name} / {attestation.digest_value.slice(0, 22)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Signed JWS
            <textarea
              value={signedStatement}
              onChange={(event) => setSignedStatement(event.target.value)}
              rows={5}
              spellCheck={false}
              className="w-full resize-y rounded-md border border-line bg-white p-3 font-mono text-xs"
            />
          </label>

          {mode === "attestation" ? (
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              CycloneDX SBOM
              <textarea
                value={sbomJson}
                onChange={(event) => setSbomJson(event.target.value)}
                rows={8}
                spellCheck={false}
                className="w-full resize-y rounded-md border border-line bg-white p-3 font-mono text-xs"
              />
            </label>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={
                busy ||
                !verifiedOperator ||
                !signedStatement.trim() ||
                (mode === "attestation" && (!runtimeAttestationId || !sbomJson.trim()))
              }
              className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Upload size={16} aria-hidden="true" />
              Verify and record
            </button>
            {notice ? <span className="text-sm text-neutral-600">{notice}</span> : null}
          </div>
        </form>
      </section>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-lg font-semibold text-ink">Model Supply Chain</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Publisher</th>
                <th className="px-4 py-3">Subject digest</th>
                <th className="px-4 py-3">SBOM</th>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Trust</th>
                <th className="px-4 py-3">Transparency</th>
                <th className="px-4 py-3">Verified</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {initialAttestations.map((attestation) => (
                <tr key={attestation.id}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{attestation.publisher}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">
                      {attestation.statement_id}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {attestation.subject_digest.slice(0, 26)}
                  </td>
                  <td className="px-4 py-3">
                    {attestation.sbom_format} {attestation.sbom_version}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {attestation.publisher_key_id}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={attestation.production_eligible ? "teal" : "neutral"}>
                      {attestation.publisher_trust_tier.replaceAll("_", " ")}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      tone={
                        attestation.transparency_status === "verified"
                          ? "teal"
                          : attestation.transparency_status === "invalidated"
                            ? "rose"
                            : attestation.transparency_status === "development"
                              ? "neutral"
                              : "amber"
                      }
                    >
                      {attestation.transparency_status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {formatDate(attestation.verified_at)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={attestation.status === "verified" ? "teal" : "rose"}>
                      {attestation.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {attestation.status === "verified" ? (
                      <button
                        type="button"
                        onClick={() => setRevokingId(attestation.id)}
                        disabled={!verifiedOperator || busy}
                        title="Revoke attestation"
                        className="inline-grid h-9 w-9 place-items-center rounded-md border border-line text-rose disabled:opacity-40"
                      >
                        <Ban size={16} aria-hidden="true" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {!initialAttestations.length ? (
                <tr>
                  <td colSpan={9} className="px-4 py-10 text-center text-neutral-500">
                    No supply-chain attestations.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {revokingId ? (
        <section className="rounded-lg border border-rose-200 bg-panel p-5 shadow-soft">
          <form onSubmit={revokeEvidence} className="grid gap-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
                <Ban size={18} className="text-rose" aria-hidden="true" />
                Revoke Attestation
              </h2>
              <button
                type="button"
                onClick={() => setRevokingId(null)}
                className="text-sm font-medium text-neutral-500"
              >
                Cancel
              </button>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-2 text-sm font-medium text-neutral-700">
                Reason
                <input
                  value={revocationReason}
                  onChange={(event) => setRevocationReason(event.target.value)}
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm"
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-neutral-700">
                Ticket reference
                <input
                  value={ticketReference}
                  onChange={(event) => setTicketReference(event.target.value)}
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm"
                />
              </label>
            </div>
            <button
              type="submit"
              disabled={busy || !revocationReason.trim()}
              className="inline-flex h-10 w-fit items-center gap-2 rounded-md bg-rose px-4 text-sm font-medium text-white disabled:opacity-40"
            >
              <Ban size={16} aria-hidden="true" />
              Record revocation
            </button>
          </form>
        </section>
      ) : null}

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-5 py-4">
          <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
            <FileJson size={18} aria-hidden="true" />
            Production Evidence Receipts
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Environment</th>
                <th className="px-4 py-3">Run</th>
                <th className="px-4 py-3">Results</th>
                <th className="px-4 py-3">Capture window</th>
                <th className="px-4 py-3">Issuer</th>
                <th className="px-4 py-3">Receipt</th>
                <th className="px-4 py-3">Eligibility</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {initialReceipts.map((receipt) => (
                <tr key={receipt.id}>
                  <td className="px-4 py-3 font-medium text-ink">
                    {String(receipt.source_environment_json.name ?? "unknown")}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {receipt.benchmark_run_id.slice(0, 12)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {receipt.result_count} / {receipt.metric_count} metrics
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {formatDate(receipt.capture_started_at)} - {formatDate(receipt.capture_ended_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div>{receipt.issuer}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">
                      {receipt.key_id}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {receipt.receipt_hash.slice(0, 16)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={receipt.production_eligible ? "teal" : "amber"}>
                      {receipt.production_eligible ? "production eligible" : "development only"}
                    </Badge>
                  </td>
                </tr>
              ))}
              {!initialReceipts.length ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-neutral-500">
                    No production evidence receipts.
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

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(new Date(value));
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
