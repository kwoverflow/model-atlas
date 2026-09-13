import { ArrowRight, Gauge, RotateCcw } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { api } from "@/lib/api";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type {
  BenchmarkRun,
  RuntimeReliabilityComparison,
  RuntimeReliabilitySummary
} from "@/types/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  left_run_id?: string;
  right_run_id?: string;
}>;

export default async function RuntimeReliabilityPage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const runs = (await api.benchmarkRuns()).filter(isReliabilityRun);
  const comparison =
    params.left_run_id && params.right_run_id
      ? await api.runtimeReliabilityComparison(params.left_run_id, params.right_run_id)
      : null;

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Validate</div>
            <h1 className="mt-1 text-2xl font-semibold text-ink">Runtime Reliability</h1>
          </div>
          <Badge tone={comparison ? statusTone(comparison.winner) : "neutral"}>
            {comparison ? winnerLabel(comparison) : `${runs.length} runs`}
          </Badge>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <form action="/runtime-reliability" className="grid gap-3 lg:grid-cols-[1fr_40px_1fr_auto]">
          <RunSelect
            label="Left run"
            name="left_run_id"
            runs={runs}
            selected={params.left_run_id}
          />
          <div className="hidden items-end justify-center pb-3 lg:flex">
            <ArrowRight size={18} className="text-neutral-400" aria-hidden="true" />
          </div>
          <RunSelect
            label="Right run"
            name="right_run_id"
            runs={runs}
            selected={params.right_run_id}
          />
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white"
            >
              <Gauge size={16} aria-hidden="true" />
              Compare
            </button>
            <Link
              href="/runtime-reliability"
              aria-label="Reset comparison"
              title="Reset comparison"
              className="grid h-10 w-10 place-items-center rounded-md border border-line text-neutral-600"
            >
              <RotateCcw size={16} aria-hidden="true" />
            </Link>
          </div>
        </form>
      </section>

      {comparison ? <ComparisonResult comparison={comparison} /> : <EmptyComparison />}
    </>
  );
}

function RunSelect({
  label,
  name,
  runs,
  selected
}: {
  label: string;
  name: string;
  runs: BenchmarkRun[];
  selected?: string;
}) {
  return (
    <label className="grid gap-2 text-sm font-medium text-neutral-700">
      {label}
      <select
        name={name}
        defaultValue={selected ?? ""}
        required
        className="h-10 min-w-0 rounded-md border border-line bg-white px-3 text-sm"
      >
        <option value="">Select a reliability run</option>
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            {run.runtime_name} / {run.id.slice(0, 8)} / {formatTimestamp(run.started_at)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ComparisonResult({ comparison }: { comparison: RuntimeReliabilityComparison }) {
  const rows: Array<{
    key: keyof RuntimeReliabilitySummary;
    label: string;
    format: "rate" | "latency" | "decimal" | "throughput";
  }> = [
    { key: "success_rate", label: "Success rate", format: "rate" },
    { key: "timeout_rate", label: "Timeout rate", format: "rate" },
    { key: "oom_rate", label: "OOM rate", format: "rate" },
    { key: "p99_end_to_end_latency_ms", label: "P99 latency", format: "latency" },
    {
      key: "latency_variation_coefficient",
      label: "Latency variation",
      format: "decimal"
    },
    { key: "mean_tokens_per_second", label: "Mean throughput", format: "throughput" },
    { key: "trial_coverage_rate", label: "Trial coverage", format: "rate" },
    { key: "context_stress_success_rate", label: "Context stress success", format: "rate" }
  ];

  return (
    <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-ink">Runtime comparison</h2>
          <p className="mt-1 text-sm text-neutral-600">{comparison.reason}</p>
        </div>
        <Badge tone={statusTone(comparison.winner)}>{winnerLabel(comparison)}</Badge>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[780px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Metric</th>
              <th className="px-4 py-3">Left</th>
              <th className="px-4 py-3">Right</th>
              <th className="px-4 py-3">Right - left</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            <tr className="bg-neutral-50/50 align-top">
              <td className="px-4 py-3 font-medium text-ink">Run</td>
              <RunCell run={comparison.left} winner={comparison.winner === "left"} />
              <RunCell run={comparison.right} winner={comparison.winner === "right"} />
              <td className="px-4 py-3 text-neutral-500">same suite</td>
            </tr>
            {rows.map((row) => {
              const leftValue = numericValue(comparison.left.summary[row.key]);
              const rightValue = numericValue(comparison.right.summary[row.key]);
              const delta = comparison.right_minus_left[String(row.key)] ?? null;
              return (
                <tr key={String(row.key)}>
                  <td className="px-4 py-3 font-medium text-neutral-700">{row.label}</td>
                  <td className="px-4 py-3">{formatMetric(leftValue, row.format)}</td>
                  <td className="px-4 py-3">{formatMetric(rightValue, row.format)}</td>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                    {formatDelta(delta, row.format)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RunCell({
  run,
  winner
}: {
  run: RuntimeReliabilityComparison["left"];
  winner: boolean;
}) {
  return (
    <td className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/benchmark-executions/${run.benchmark_run_id}`}
          className="font-medium text-teal hover:underline"
        >
          {run.runtime_name}
        </Link>
        {winner ? <Badge tone="teal">recommended</Badge> : null}
      </div>
      <div className="mt-1 font-mono text-xs text-neutral-500">
        {run.benchmark_run_id.slice(0, 8)} / {run.summary.trial_count} trials
      </div>
    </td>
  );
}

function EmptyComparison() {
  return (
    <section className="border-y border-line py-12 text-center">
      <Gauge size={24} className="mx-auto text-neutral-400" aria-hidden="true" />
      <div className="mt-3 text-sm font-medium text-ink">Select two reliability runs</div>
      <div className="mt-1 text-sm text-neutral-500">No comparison is active.</div>
    </section>
  );
}

function isReliabilityRun(run: BenchmarkRun): boolean {
  return typeof run.runtime_config_json.runtime_reliability_schema_version === "string";
}

function numericValue(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function formatMetric(
  value: number | null,
  format: "rate" | "latency" | "decimal" | "throughput"
): string {
  if (value === null) return "N/A";
  if (format === "rate") return percent(value);
  if (format === "latency") return value >= 1_000 ? `${(value / 1_000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
  if (format === "throughput") return `${value.toFixed(1)} tok/s`;
  return value.toFixed(4);
}

function formatDelta(
  value: number | null,
  format: "rate" | "latency" | "decimal" | "throughput"
): string {
  if (value === null) return "N/A";
  const prefix = value > 0 ? "+" : "";
  if (format === "rate") return `${prefix}${(value * 100).toFixed(1)} pp`;
  if (format === "latency") return `${prefix}${value.toFixed(0)} ms`;
  if (format === "throughput") return `${prefix}${value.toFixed(1)} tok/s`;
  return `${prefix}${value.toFixed(4)}`;
}

function winnerLabel(comparison: RuntimeReliabilityComparison): string {
  if (comparison.winner === "left") return "Left recommended";
  if (comparison.winner === "right") return "Right recommended";
  return statusLabel(comparison.winner);
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}
