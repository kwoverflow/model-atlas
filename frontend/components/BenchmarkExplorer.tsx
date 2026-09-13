"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/Badge";
import { MetricCharts } from "@/components/MetricCharts";
import type {
  BenchmarkRun,
  BenchmarkTask,
  HardwareProfile,
  ModelArtifact,
  ModelComparisonRow
} from "@/types/api";

type BenchmarkExplorerProps = {
  runs: BenchmarkRun[];
  artifacts: ModelArtifact[];
  tasks: BenchmarkTask[];
  hardware: HardwareProfile[];
  comparisons: ModelComparisonRow[];
};

function pct(value: number | null): number | null {
  return value === null ? null : value * 100;
}

export function BenchmarkExplorer({
  runs,
  artifacts,
  tasks,
  hardware,
  comparisons
}: BenchmarkExplorerProps) {
  const [artifactId, setArtifactId] = useState("all");
  const [taskId, setTaskId] = useState("all");
  const [hardwareId, setHardwareId] = useState("all");

  const artifactById = useMemo(
    () => new Map(artifacts.map((artifact) => [artifact.id, artifact])),
    [artifacts]
  );
  const taskById = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks]);
  const hardwareById = useMemo(
    () => new Map(hardware.map((profile) => [profile.id, profile])),
    [hardware]
  );

  const filteredRuns = runs.filter(
    (run) =>
      (artifactId === "all" || run.model_artifact_id === artifactId) &&
      (taskId === "all" || run.benchmark_task_id === taskId) &&
      (hardwareId === "all" || run.hardware_profile_id === hardwareId)
  );
  const filteredComparisons = comparisons.filter(
    (row) =>
      (artifactId === "all" || row.model_artifact_id === artifactId) &&
      (taskId === "all" || row.benchmark_task_id === taskId)
  );
  const chartData = filteredComparisons.map((row) => ({
    label: `${row.artifact_name.replace("-instruct", "")} / ${row.benchmark_task_name}`,
    quality: row.average_quality_score,
    ttft: row.average_ttft_ms,
    latency: row.average_end_to_end_latency_ms,
    tps: row.average_tokens_per_second,
    vram: row.average_vram_usage_mb,
    jsonRate: pct(row.json_validity_rate),
    toolRate: pct(row.tool_call_validity_rate)
  }));

  return (
    <div className="grid gap-4">
      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="grid gap-1.5 text-sm font-medium text-ink">
            Model artifact
            <select
              value={artifactId}
              onChange={(event) => setArtifactId(event.target.value)}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
            >
              <option value="all">All artifacts</option>
              {artifacts.map((artifact) => (
                <option key={artifact.id} value={artifact.id}>
                  {artifact.artifact_name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-ink">
            Task
            <select
              value={taskId}
              onChange={(event) => setTaskId(event.target.value)}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
            >
              <option value="all">All tasks</option>
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-medium text-ink">
            Hardware
            <select
              value={hardwareId}
              onChange={(event) => setHardwareId(event.target.value)}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
            >
              <option value="all">All hardware</option>
              {hardware.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex items-center justify-between border-b border-line p-4">
          <h2 className="text-base font-semibold text-ink">Benchmark Runs</h2>
          <Badge tone="teal">{filteredRuns.length} shown</Badge>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Artifact</th>
                <th className="px-4 py-3">Task</th>
                <th className="px-4 py-3">Hardware</th>
                <th className="px-4 py-3">Runtime</th>
                <th className="px-4 py-3">Dataset</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filteredRuns.map((run) => (
                <tr key={run.id}>
                  <td className="px-4 py-3 font-medium text-ink">
                    {artifactById.get(run.model_artifact_id)?.artifact_name ?? "Unknown"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {taskById.get(run.benchmark_task_id)?.name ?? "Unknown"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {hardwareById.get(run.hardware_profile_id)?.gpu_name ?? "Unknown"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">{run.runtime_name}</td>
                  <td className="px-4 py-3 text-neutral-700">{run.dataset_version}</td>
                  <td className="px-4 py-3">
                    <Badge tone={run.status === "completed" ? "teal" : "rose"}>{run.status}</Badge>
                  </td>
                </tr>
              ))}
              {!filteredRuns.length ? (
                <tr>
                  <td className="px-4 py-6 text-neutral-500" colSpan={6}>
                    No benchmark runs match the current filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line p-4">
          <h2 className="text-base font-semibold text-ink">Quality And Latency Comparison</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Artifact</th>
                <th className="px-4 py-3">Task</th>
                <th className="px-4 py-3">Quality</th>
                <th className="px-4 py-3">TTFT</th>
                <th className="px-4 py-3">Latency</th>
                <th className="px-4 py-3">Tokens/sec</th>
                <th className="px-4 py-3">VRAM</th>
                <th className="px-4 py-3">JSON</th>
                <th className="px-4 py-3">Tools</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filteredComparisons.map((row) => (
                <tr key={`${row.model_artifact_id}-${row.benchmark_task_id}`}>
                  <td className="px-4 py-3 font-medium text-ink">{row.artifact_name}</td>
                  <td className="px-4 py-3 text-neutral-700">{row.benchmark_task_name}</td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_quality_score?.toFixed(2) ?? "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_ttft_ms ? `${Math.round(row.average_ttft_ms)} ms` : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_end_to_end_latency_ms
                      ? `${Math.round(row.average_end_to_end_latency_ms)} ms`
                      : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_tokens_per_second?.toFixed(1) ?? "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_vram_usage_mb
                      ? `${Math.round(row.average_vram_usage_mb)} MB`
                      : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.json_validity_rate !== null
                      ? `${Math.round(row.json_validity_rate * 100)}%`
                      : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.tool_call_validity_rate !== null
                      ? `${Math.round(row.tool_call_validity_rate * 100)}%`
                      : "n/a"}
                  </td>
                </tr>
              ))}
              {!filteredComparisons.length ? (
                <tr>
                  <td className="px-4 py-6 text-neutral-500" colSpan={9}>
                    No comparison rows match the current filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <MetricCharts data={chartData} />
    </div>
  );
}
