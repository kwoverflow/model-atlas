"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { ReferenceMetricComparisonRow } from "@/types/api";

export function ConfigurationCharts({ rows }: { rows: ReferenceMetricComparisonRow[] }) {
  const data = rows.map((row) => ({
    name: row.entry_name,
    quality: toPercent(row.metrics.mean_quality_score),
    groundedness: toPercent(row.metrics.rag_groundedness_score),
    toolSuccess: toPercent(row.metrics.tool_execution_success_rate),
    taskCompletion: toPercent(row.metrics.task_completion_rate),
    latency: row.metrics.p95_end_to_end_latency_ms
  }));

  if (!rows.length) {
    return (
      <div className="border-y border-line py-8 text-sm text-neutral-500">
        No stored runtime comparison is available yet.
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <figure className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <figcaption className="text-sm font-semibold text-ink">Quality and completion rates</figcaption>
        <div className="mt-3 h-72 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 36, left: 0 }}>
              <CartesianGrid stroke="#e5e7eb" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#525252" }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#525252" }} unit="%" />
              <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="quality" name="Quality" fill="#0f766e" />
              <Bar dataKey="groundedness" name="Groundedness" fill="#2563eb" />
              <Bar dataKey="toolSuccess" name="Tool success" fill="#b45309" />
              <Bar dataKey="taskCompletion" name="Task completion" fill="#6d28d9" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </figure>

      <figure className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <figcaption className="text-sm font-semibold text-ink">P95 end-to-end latency</figcaption>
        <div className="mt-3 h-72 min-w-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 36, left: 8 }}>
              <CartesianGrid stroke="#e5e7eb" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#525252" }} />
              <YAxis tick={{ fontSize: 11, fill: "#525252" }} unit=" ms" width={72} />
              <Tooltip formatter={(value) => [`${Number(value).toFixed(0)} ms`, "P95 latency"]} />
              <Bar dataKey="latency" name="P95 latency" fill="#be123c" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </figure>
    </div>
  );
}

function toPercent(value: number | null): number | null {
  return value === null ? null : value * 100;
}
