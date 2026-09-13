"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";

type PromoteBaselineButtonProps = {
  gateId: string;
  canPromote: boolean;
  isActiveBaseline: boolean;
};

export function PromoteBaselineButton({
  gateId,
  canPromote,
  isActiveBaseline
}: PromoteBaselineButtonProps) {
  const [status, setStatus] = useState<string | null>(null);

  async function promote() {
    setStatus("Promoting");
    const response = await browserApiFetch(
      `${API_BASE_URL}/deployment-gates/evaluations/${gateId}/promote-baseline`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          promoted_by: "local-ui",
          promotion_reason: "Promoted from gate report"
        })
      }
    );
    if (!response.ok) {
      setStatus("Promotion failed");
      return;
    }
    setStatus("Promoted");
    window.location.reload();
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={promote}
        disabled={!canPromote || isActiveBaseline}
        className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:opacity-50"
      >
        <ShieldCheck size={16} aria-hidden="true" />
        {isActiveBaseline ? "Active Baseline" : "Promote Baseline"}
      </button>
      {status ? <span className="text-sm text-neutral-600">{status}</span> : null}
    </div>
  );
}
