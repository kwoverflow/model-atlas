"use client";

import { ClipboardCheck, Send, X } from "lucide-react";
import type { FormEvent } from "react";
import { useState } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type { JudgeLabelReviewRow } from "@/types/api";

export function JudgeLabelReviewDecisionForm({ row }: { row: JudgeLabelReviewRow }) {
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState<
    "approved_candidate" | "overridden" | "rejected"
  >(row.candidate_judge_labels ? "approved_candidate" : "overridden");
  const [quality, setQuality] = useState(
    row.quality_score === null ? "" : String(row.quality_score)
  );
  const [groundedness, setGroundedness] = useState(
    row.groundedness_score === null ? "" : String(row.groundedness_score)
  );
  const [faithfulness, setFaithfulness] = useState(
    row.faithfulness_score === null ? "" : String(row.faithfulness_score)
  );
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (row.score_source === "human_reviewed") {
    return <span className="text-xs font-medium text-teal">Reviewed</span>;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await browserApiFetch(
      `${API_BASE_URL}/judge-labels/review-decisions`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          benchmark_result_id: row.benchmark_result_id,
          decision_type: decision,
          rationale,
          ...(decision === "overridden"
            ? {
                quality_score: quality === "" ? null : Number(quality),
                groundedness_score:
                  groundedness === "" ? null : Number(groundedness),
                faithfulness_score:
                  faithfulness === "" ? null : Number(faithfulness)
              }
            : {})
        })
      }
    );
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as
        | { detail?: string | Array<{ msg?: string }> }
        | null;
      const message =
        typeof payload?.detail === "string"
          ? payload.detail
          : Array.isArray(payload?.detail)
            ? payload.detail.find((item) => item.msg)?.msg
            : null;
      setError(message ?? `Review failed with status ${response.status}`);
      setBusy(false);
      return;
    }
    window.location.reload();
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Review judge label"
        aria-label="Review judge label"
        className="grid h-9 w-9 place-items-center rounded-md border border-line text-neutral-700 hover:bg-neutral-50"
      >
        <ClipboardCheck size={16} aria-hidden="true" />
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="grid min-w-64 gap-2 py-1">
      <div className="flex items-center gap-2">
        <select
          value={decision}
          onChange={(event) =>
            setDecision(
              event.target.value as "approved_candidate" | "overridden" | "rejected"
            )
          }
          className="h-9 min-w-0 flex-1 rounded-md border border-line bg-white px-2 text-xs"
        >
          {row.candidate_judge_labels ? (
            <option value="approved_candidate">Approve candidate</option>
          ) : null}
          <option value="overridden">Override</option>
          <option value="rejected">Reject candidate</option>
        </select>
        <button
          type="button"
          onClick={() => setOpen(false)}
          title="Close review"
          aria-label="Close review"
          className="grid h-9 w-9 place-items-center rounded-md border border-line"
        >
          <X size={15} aria-hidden="true" />
        </button>
      </div>
      {decision === "overridden" ? (
        <div className="grid grid-cols-3 gap-2">
          <ScoreInput label="Q" value={quality} onChange={setQuality} />
          <ScoreInput label="G" value={groundedness} onChange={setGroundedness} />
          <ScoreInput label="F" value={faithfulness} onChange={setFaithfulness} />
        </div>
      ) : null}
      <textarea
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        required
        minLength={3}
        maxLength={4000}
        rows={2}
        placeholder="Review rationale"
        className="resize-y rounded-md border border-line bg-white px-2 py-2 text-xs"
      />
      <button
        type="submit"
        disabled={busy || rationale.trim().length < 3}
        className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-ink px-3 text-xs font-medium text-white disabled:opacity-40"
      >
        <Send size={14} aria-hidden="true" />
        Submit review
      </button>
      {error ? <div className="text-xs leading-5 text-rose">{error}</div> : null}
    </form>
  );
}

function ScoreInput({
  label,
  value,
  onChange
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-xs font-medium text-neutral-600">
      {label}
      <input
        type="number"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 min-w-0 rounded-md border border-line px-2 text-xs"
      />
    </label>
  );
}
