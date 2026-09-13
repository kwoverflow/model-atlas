"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/Badge";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type { AgentReplay } from "@/types/api";

export function AgentReplayButton({ benchmarkResultId }: { benchmarkResultId: string }) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<AgentReplay | null>(null);
  const [failed, setFailed] = useState(false);

  async function replay() {
    setPending(true);
    setFailed(false);
    const response = await browserApiFetch(
      `${API_BASE_URL}/agents/replay/${benchmarkResultId}`,
      { method: "POST" }
    );
    if (!response.ok) {
      setFailed(true);
      setPending(false);
      return;
    }
    setResult((await response.json()) as AgentReplay);
    setPending(false);
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <button
        type="button"
        onClick={replay}
        disabled={pending}
        className="inline-flex h-9 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium text-neutral-700 disabled:opacity-60"
      >
        <RefreshCw size={15} className={pending ? "animate-spin" : ""} aria-hidden="true" />
        {pending ? "Replaying" : "Replay Trace"}
      </button>
      {result ? (
        <Badge tone={result.deterministic_match ? "teal" : "rose"}>
          {result.deterministic_match ? "Semantic match" : "Trace changed"}
        </Badge>
      ) : null}
      {failed ? <Badge tone="rose">Replay failed</Badge> : null}
      {result && !result.deterministic_match ? (
        <details className="w-full text-right">
          <summary className="cursor-pointer text-xs font-medium text-rose">
            {result.changed_paths.length} changed paths
          </summary>
          <div className="mt-2 break-all font-mono text-xs text-neutral-500">
            {result.changed_paths.join(", ") || "Version mismatch"}
          </div>
        </details>
      ) : null}
    </div>
  );
}
