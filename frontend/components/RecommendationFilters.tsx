"use client";

import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import {
  checked,
  DEFAULT_RECOMMENDATION_WEIGHTS,
  first,
  numericParam,
  type SearchParamRecord
} from "@/lib/recommendationParams";
import type { BenchmarkTask, HardwareProfile } from "@/types/api";

type RecommendationFiltersProps = {
  hardware: HardwareProfile[];
  tasks: BenchmarkTask[];
  searchParams: SearchParamRecord;
};

const weightFields = [
  { key: "quality", queryKey: "quality_weight", label: "Quality" },
  { key: "latency", queryKey: "latency_weight", label: "Latency" },
  { key: "throughput", queryKey: "throughput_weight", label: "Throughput" },
  { key: "vram_efficiency", queryKey: "vram_efficiency_weight", label: "VRAM efficiency" }
] as const;

export function RecommendationFilters({
  hardware,
  tasks,
  searchParams
}: RecommendationFiltersProps) {
  const selectedHardwareId = first(searchParams.hardware_profile_id) ?? "";
  const selectedTaskId = first(searchParams.benchmark_task_id) ?? "";
  const minContextLength = first(searchParams.min_context_length) ?? "";
  const topK = first(searchParams.top_k) ?? "5";
  const [weights, setWeights] = useState(() => ({
    quality: numericParam(
      searchParams.quality_weight,
      DEFAULT_RECOMMENDATION_WEIGHTS.quality
    ),
    latency: numericParam(
      searchParams.latency_weight,
      DEFAULT_RECOMMENDATION_WEIGHTS.latency
    ),
    throughput: numericParam(
      searchParams.throughput_weight,
      DEFAULT_RECOMMENDATION_WEIGHTS.throughput
    ),
    vram_efficiency: numericParam(
      searchParams.vram_efficiency_weight,
      DEFAULT_RECOMMENDATION_WEIGHTS.vram_efficiency
    )
  }));

  return (
    <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
      <form className="grid gap-3 lg:grid-cols-6" method="get" action="/recommendations">
        <label className="grid gap-1.5 text-sm font-medium text-ink lg:col-span-2">
          Hardware
          <select
            name="hardware_profile_id"
            defaultValue={selectedHardwareId}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
          >
            <option value="">Default hardware</option>
            {hardware.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-ink lg:col-span-2">
          Benchmark task
          <select
            name="benchmark_task_id"
            defaultValue={selectedTaskId}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
          >
            <option value="">All benchmark evidence</option>
            {tasks.map((task) => (
              <option key={task.id} value={task.id}>
                {task.name}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-ink">
          Min context
          <input
            name="min_context_length"
            defaultValue={minContextLength}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
            min={1}
            type="number"
          />
        </label>
        <label className="grid gap-1.5 text-sm font-medium text-ink">
          Top K
          <input
            name="top_k"
            defaultValue={topK}
            className="h-10 rounded-md border border-line bg-white px-3 text-sm outline-none focus:border-teal"
            max={20}
            min={1}
            type="number"
          />
        </label>
        <div className="flex flex-wrap items-center gap-4 lg:col-span-5">
          <label className="flex items-center gap-2 text-sm text-neutral-700">
            <input
              name="require_tool_calling"
              type="checkbox"
              defaultChecked={checked(first(searchParams.require_tool_calling))}
            />
            Tool calling
          </label>
          <label className="flex items-center gap-2 text-sm text-neutral-700">
            <input
              name="require_structured_output"
              type="checkbox"
              defaultChecked={checked(first(searchParams.require_structured_output))}
            />
            Structured output
          </label>
          <label className="flex items-center gap-2 text-sm text-neutral-700">
            <input
              name="commercial_use_required"
              type="checkbox"
              defaultChecked={checked(first(searchParams.commercial_use_required))}
            />
            Commercial use
          </label>
        </div>
        <div className="grid gap-3 border-t border-line pt-3 lg:col-span-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {weightFields.map((field) => (
              <label
                className="grid gap-2 text-sm font-medium text-ink"
                key={field.queryKey}
              >
                <span className="flex items-center justify-between gap-3">
                  {field.label}
                  <span className="font-mono text-xs text-neutral-500">
                    {weights[field.key].toFixed(2)}
                  </span>
                </span>
                <input
                  aria-label={`${field.label} weight`}
                  className="accent-teal"
                  max={1}
                  min={0}
                  onChange={(event) =>
                    setWeights((current) => ({
                      ...current,
                      [field.key]: Number(event.target.value)
                    }))
                  }
                  step={0.05}
                  type="range"
                  value={weights[field.key]}
                />
                <input
                  name={field.queryKey}
                  type="hidden"
                  value={weights[field.key].toFixed(2)}
                />
              </label>
            ))}
          </div>
        </div>
        <div className="flex justify-end lg:col-span-6">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-white hover:bg-neutral-700"
            type="submit"
          >
            <SlidersHorizontal size={16} />
            Rank
          </button>
        </div>
      </form>
    </section>
  );
}
