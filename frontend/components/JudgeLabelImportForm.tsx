"use client";

import { CheckCircle2, FileUp, RotateCcw } from "lucide-react";
import { useState } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type { BenchmarkRun, JudgeLabelImportSummary } from "@/types/api";

type JudgeLabelImportFormProps = {
  runs: BenchmarkRun[];
  selectedBenchmarkRunId?: string;
};

function numberValue(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(3);
}

export function JudgeLabelImportForm({
  runs,
  selectedBenchmarkRunId
}: JudgeLabelImportFormProps) {
  const [benchmarkRunId, setBenchmarkRunId] = useState(selectedBenchmarkRunId ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [summary, setSummary] = useState<JudgeLabelImportSummary | null>(null);

  async function submit(applyLabels: boolean) {
    if (!benchmarkRunId || !file) {
      setStatus("Select a run and file");
      return;
    }
    setStatus(applyLabels ? "Applying labels" : "Checking labels");
    setSummary(null);
    const content = await file.text();
    const response = await browserApiFetch(`${API_BASE_URL}/judge-labels/import`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        benchmark_run_id: benchmarkRunId,
        filename: file.name,
        content,
        apply_labels: applyLabels
      })
    });
    if (!response.ok) {
      setStatus("Import failed");
      return;
    }
    const payload = (await response.json()) as JudgeLabelImportSummary;
    setSummary(payload);
    setStatus(applyLabels ? "Labels applied" : "Dry run complete");
    if (applyLabels) {
      window.location.href = `/judge-labels?benchmark_run_id=${benchmarkRunId}`;
    }
  }

  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
      <div className="mb-3 text-sm font-semibold text-ink">Judge Label Import</div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(220px,320px)_auto]">
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Benchmark run
          <select
            value={benchmarkRunId}
            onChange={(event) => setBenchmarkRunId(event.target.value)}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm"
          >
            <option value="">Select benchmark run</option>
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.runtime_name} - {run.data_source} - {run.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Label file
          <input
            type="file"
            accept=".jsonl,.json,.csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="h-10 rounded-md border border-line bg-white px-3 py-2 text-sm"
          />
        </label>
        <div className="flex flex-wrap items-end gap-2">
          <button
            type="button"
            onClick={() => void submit(false)}
            disabled={!benchmarkRunId || !file}
            className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium disabled:opacity-50"
          >
            <RotateCcw size={16} aria-hidden="true" />
            Dry Run
          </button>
          <button
            type="button"
            onClick={() => void submit(true)}
            disabled={!benchmarkRunId || !file}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-3 text-sm font-medium text-white disabled:opacity-50"
          >
            <FileUp size={16} aria-hidden="true" />
            Apply
          </button>
        </div>
      </div>
      {status ? <div className="mt-3 text-sm text-neutral-600">{status}</div> : null}
      {summary ? (
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
          <div className="rounded-md bg-neutral-50 p-3">
            <div className="text-xs uppercase text-neutral-500">Matched</div>
            <div className="mt-1 font-semibold text-ink">
              {summary.matched_label_count}/{summary.label_count}
            </div>
          </div>
          <div className="rounded-md bg-neutral-50 p-3">
            <div className="text-xs uppercase text-neutral-500">Missing</div>
            <div className="mt-1 font-semibold text-ink">{summary.missing_result_count}</div>
          </div>
          <div className="rounded-md bg-neutral-50 p-3">
            <div className="text-xs uppercase text-neutral-500">Quality labels</div>
            <div className="mt-1 font-semibold text-ink">{summary.quality_label_count}</div>
          </div>
          <div className="rounded-md bg-neutral-50 p-3">
            <div className="flex items-center gap-2 text-xs uppercase text-neutral-500">
              <CheckCircle2 size={14} aria-hidden="true" />
              Delta
            </div>
            <div className="mt-1 font-semibold text-ink">
              {numberValue(summary.average_abs_quality_delta)}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
