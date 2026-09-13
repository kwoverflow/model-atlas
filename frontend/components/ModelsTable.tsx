"use client";

import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/Badge";
import type { HardwareProfile, Model, ModelArtifact, ModelComparisonRow } from "@/types/api";

type ModelsTableProps = {
  models: Model[];
  artifacts: ModelArtifact[];
  hardware: HardwareProfile[];
  comparisons: ModelComparisonRow[];
};

export function ModelsTable({ models, artifacts, hardware, comparisons }: ModelsTableProps) {
  const [query, setQuery] = useState("");
  const modelById = useMemo(() => new Map(models.map((model) => [model.id, model])), [models]);
  const rows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return artifacts
      .map((artifact) => ({ artifact, model: modelById.get(artifact.model_id) }))
      .filter(({ artifact, model }) => {
        const text = [
          artifact.artifact_name,
          artifact.quantization,
          artifact.precision,
          artifact.format,
          model?.display_name,
          model?.provider,
          model?.family
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return !normalizedQuery || text.includes(normalizedQuery);
      });
  }, [artifacts, modelById, query]);

  return (
    <div className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex flex-col gap-3 border-b border-line p-4 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-base font-semibold text-ink">Model Artifacts</h2>
        <label className="relative block w-full sm:w-80">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
            size={16}
            aria-hidden="true"
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="h-10 w-full rounded-md border border-line bg-white pl-9 pr-3 text-sm outline-none focus:border-teal"
            placeholder="Search models or artifacts"
          />
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Artifact</th>
              <th className="px-4 py-3">Capability</th>
              <th className="px-4 py-3">Runtime</th>
              <th className="px-4 py-3">VRAM</th>
              <th className="px-4 py-3">Hardware</th>
              <th className="px-4 py-3">Benchmarks</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map(({ artifact, model }) => {
              const isCompatible = hardware.some(
                (profile) =>
                  artifact.recommended_vram_gb !== null &&
                  profile.gpu_vram_gb >= artifact.recommended_vram_gb
              );
              const artifactComparisons = comparisons.filter(
                (comparison) => comparison.model_artifact_id === artifact.id
              );
              return (
                <tr key={artifact.id} className="align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{model?.display_name ?? "Unknown"}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {model?.provider} / {model?.family}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{artifact.artifact_name}</div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <Badge tone="neutral">{artifact.format}</Badge>
                      {artifact.quantization ? <Badge tone="amber">{artifact.quantization}</Badge> : null}
                      {artifact.precision ? <Badge tone="violet">{artifact.precision}</Badge> : null}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex max-w-48 flex-wrap gap-1.5">
                      {model?.supports_text ? <Badge tone="teal">Text</Badge> : null}
                      {model?.supports_vision ? <Badge tone="violet">Vision</Badge> : null}
                      {model?.supports_tool_calling ? <Badge tone="amber">Tools</Badge> : null}
                      {model?.supports_structured_output ? <Badge tone="rose">JSON</Badge> : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {artifact.runtime_compatibility.join(", ")}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {artifact.recommended_vram_gb ?? "n/a"} GB recommended
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={isCompatible ? "teal" : "rose"}>
                      {isCompatible ? "Compatible" : "Needs larger GPU"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {artifactComparisons.length
                      ? artifactComparisons
                          .map((comparison) => comparison.benchmark_task_name)
                          .join(", ")
                      : "No benchmark summary"}
                  </td>
                </tr>
              );
            })}
            {!rows.length ? (
              <tr>
                <td className="px-4 py-6 text-neutral-500" colSpan={7}>
                  No artifacts match the current search.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
