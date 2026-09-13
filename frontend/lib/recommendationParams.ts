import type { RecommendationRequest } from "@/types/api";

export type SearchParamRecord = Record<string, string | string[] | undefined>;

export const DEFAULT_RECOMMENDATION_WEIGHTS = {
  quality: 0.45,
  latency: 0.2,
  throughput: 0.2,
  vram_efficiency: 0.15
} as const;

const WEIGHT_QUERY_KEYS = [
  "quality_weight",
  "latency_weight",
  "throughput_weight",
  "vram_efficiency_weight"
] as const;

type WeightQueryKey = (typeof WEIGHT_QUERY_KEYS)[number];

export function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function checked(value: string | undefined): boolean {
  return value === "true" || value === "on";
}

export function numericParam(
  value: string | string[] | undefined,
  fallback: number
): number {
  const parsed = Number(first(value));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function copyOptionalParam(
  params: URLSearchParams,
  searchParams: SearchParamRecord,
  key: string
) {
  const value = first(searchParams[key]);
  if (value) params.set(key, value);
}

function copyWeightParam(
  params: URLSearchParams,
  searchParams: SearchParamRecord,
  key: WeightQueryKey
) {
  const value = first(searchParams[key]);
  if (value !== undefined && value !== "") params.set(key, value);
}

export function buildRecommendationParams(searchParams: SearchParamRecord) {
  const params = new URLSearchParams();

  copyOptionalParam(params, searchParams, "hardware_profile_id");
  copyOptionalParam(params, searchParams, "benchmark_task_id");
  if (checked(first(searchParams.require_tool_calling))) {
    params.set("require_tool_calling", "true");
  }
  if (checked(first(searchParams.require_structured_output))) {
    params.set("require_structured_output", "true");
  }
  if (checked(first(searchParams.commercial_use_required))) {
    params.set("commercial_use_required", "true");
  }
  copyOptionalParam(params, searchParams, "min_context_length");
  copyOptionalParam(params, searchParams, "top_k");
  for (const key of WEIGHT_QUERY_KEYS) {
    copyWeightParam(params, searchParams, key);
  }
  return params;
}

export function recommendationRequestToSearchParams(request: RecommendationRequest) {
  const params = new URLSearchParams();
  if (request.hardware_profile_id) {
    params.set("hardware_profile_id", request.hardware_profile_id);
  }
  if (request.benchmark_task_id) {
    params.set("benchmark_task_id", request.benchmark_task_id);
  }
  if (request.require_tool_calling) params.set("require_tool_calling", "true");
  if (request.require_structured_output) params.set("require_structured_output", "true");
  if (request.commercial_use_required) params.set("commercial_use_required", "true");
  if (request.min_context_length) {
    params.set("min_context_length", String(request.min_context_length));
  }
  params.set("top_k", String(request.top_k));
  params.set("quality_weight", String(request.weights.quality));
  params.set("latency_weight", String(request.weights.latency));
  params.set("throughput_weight", String(request.weights.throughput));
  params.set("vram_efficiency_weight", String(request.weights.vram_efficiency));
  return params;
}

export function recommendationRequestHref(request: RecommendationRequest) {
  const params = recommendationRequestToSearchParams(request);
  const query = params.toString();
  return query ? `/recommendations?${query}` : "/recommendations";
}
