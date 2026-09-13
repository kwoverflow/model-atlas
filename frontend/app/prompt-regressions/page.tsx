import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import type { PromptRegressionMetric } from "@/types/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  deployment_configuration_id?: string;
  evaluation_suite_id?: string;
  acceptance_policy_id?: string;
}>;

const emptyMetric: PromptRegressionMetric = {
  value: null,
  sample_size: 0,
  delta_vs_baseline: null
};

function metric(value: PromptRegressionMetric | undefined, unit = ""): string {
  if (!value || value.value === null) return "n/a";
  return `${value.value.toFixed(3)}${unit}`;
}

function delta(value: PromptRegressionMetric | undefined, lowerIsBetter = false): string {
  if (!value) return "n/a";
  if (value.delta_vs_baseline === null) return "n/a";
  const prefix = value.delta_vs_baseline > 0 ? "+" : "";
  const directionBad = lowerIsBetter
    ? value.delta_vs_baseline > 0
    : value.delta_vs_baseline < 0;
  return `${prefix}${value.delta_vs_baseline.toFixed(3)}${directionBad ? " risk" : ""}`;
}

function riskTone(flags: string[]): "teal" | "amber" | "rose" | "violet" | "neutral" {
  if (flags.includes("critical_failures") || flags.includes("oom_risk")) return "rose";
  if (flags.length) return "amber";
  return "teal";
}

export default async function PromptRegressionsPage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const resolvedSearchParams = await searchParams;
  const reportParams = new URLSearchParams();
  if (resolvedSearchParams.deployment_configuration_id) {
    reportParams.set(
      "deployment_configuration_id",
      resolvedSearchParams.deployment_configuration_id
    );
  }
  if (resolvedSearchParams.evaluation_suite_id) {
    reportParams.set("evaluation_suite_id", resolvedSearchParams.evaluation_suite_id);
  }
  if (resolvedSearchParams.acceptance_policy_id) {
    reportParams.set("acceptance_policy_id", resolvedSearchParams.acceptance_policy_id);
  }
  const [configs, suites, policies, report] = await Promise.all([
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies(),
    api.promptRegressionReport(reportParams)
  ]);
  const selectedConfig = configs.find(
    (item) => item.id === resolvedSearchParams.deployment_configuration_id
  );
  const selectedSuite = suites.find((item) => item.id === resolvedSearchParams.evaluation_suite_id);
  const selectedPolicy = policies.find(
    (item) => item.id === resolvedSearchParams.acceptance_policy_id
  );
  const riskyRows = report.rows.filter((row) => row.risk_flags.length > 0);
  const baselineRow = report.rows.find((row) => row.is_baseline_prompt);
  const bestQualityRow = report.rows[0];

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Prompt Version Regression</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Prompt-version comparison over stored benchmark evidence, with baseline deltas when
              an active deployment baseline exists for the selected scope.
            </p>
          </div>
          <Badge tone={riskyRows.length ? "amber" : "teal"}>
            {riskyRows.length ? "Regression risk" : "No prompt risk"}
          </Badge>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <form className="grid gap-3 lg:grid-cols-4" action="/prompt-regressions">
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Deployment
            <select
              name="deployment_configuration_id"
              defaultValue={resolvedSearchParams.deployment_configuration_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All deployments</option>
              {configs.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Suite
            <select
              name="evaluation_suite_id"
              defaultValue={resolvedSearchParams.evaluation_suite_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All suites</option>
              {suites.map((suite) => (
                <option key={suite.id} value={suite.id}>
                  {suite.name} {suite.version_label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Policy
            <select
              name="acceptance_policy_id"
              defaultValue={resolvedSearchParams.acceptance_policy_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">No baseline lookup</option>
              {policies.map((policy) => (
                <option key={policy.id} value={policy.id}>
                  {policy.name} {policy.version_label}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white"
            >
              Compare
            </button>
            <Link
              className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium"
              href="/prompt-regressions"
            >
              Reset
            </Link>
          </div>
        </form>
        <div className="mt-3 text-xs text-neutral-500">
          Scope: {selectedConfig?.name ?? "all deployments"} - {selectedSuite?.name ?? "all suites"}{" "}
          - {selectedPolicy?.name ?? "no policy baseline"}
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <SummaryCard
          label="Prompt versions"
          value={report.row_count}
          detail="with benchmark evidence"
        />
        <SummaryCard
          label="Baseline"
          value={baselineRow ? "Found" : "None"}
          detail={report.baseline_gate_evaluation_id?.slice(0, 8) ?? "active baseline not selected"}
          tone="violet"
        />
        <SummaryCard
          label="Risk rows"
          value={riskyRows.length}
          detail="flags detected"
          tone="amber"
        />
        <SummaryCard
          label="Best quality"
          value={metric(bestQualityRow?.mean_quality_score ?? emptyMetric)}
          detail={bestQualityRow?.prompt_name ?? "no evidence"}
          tone="teal"
        />
      </div>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Prompt Regression Rows
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Prompt</th>
              <th className="px-4 py-3">Quality</th>
              <th className="px-4 py-3">Reliability</th>
              <th className="px-4 py-3">Latency</th>
              <th className="px-4 py-3">Evidence</th>
              <th className="px-4 py-3">Risk</th>
            </tr>
          </thead>
          <tbody>
            {report.rows.map((row) => (
              <tr key={row.prompt_version_id} className="border-t border-line align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{row.prompt_name}</div>
                  <div className="mt-1 text-xs text-neutral-500">{row.version_label}</div>
                  <div className="mt-1 font-mono text-xs text-neutral-500">
                    {row.prompt_hash.slice(0, 16)}
                  </div>
                  {row.is_baseline_prompt ? (
                    <Badge tone="violet">baseline prompt</Badge>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <div>Q {metric(row.mean_quality_score)}</div>
                  <div className="text-xs text-neutral-500">
                    delta {delta(row.mean_quality_score)}
                  </div>
                  <div className="mt-1 text-xs text-neutral-500">
                    G {metric(row.groundedness_score)} / F {metric(row.faithfulness_score)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div>JSON {metric(row.json_validity_rate)}</div>
                  <div className="text-xs text-neutral-500">
                    Tool {metric(row.tool_call_validity_rate)}
                  </div>
                  <div className="text-xs text-neutral-500">
                    Critical {metric(row.critical_case_failure_rate)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div>P95 {metric(row.p95_end_to_end_latency_ms, " ms")}</div>
                  <div className="text-xs text-neutral-500">
                    delta {delta(row.p95_end_to_end_latency_ms, true)}
                  </div>
                  <div className="text-xs text-neutral-500">
                    TPS {metric(row.mean_tokens_per_second)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div>{row.run_count} runs</div>
                  <div className="text-xs text-neutral-500">{row.result_count} results</div>
                  <div className="mt-1 max-w-xs text-xs text-neutral-500">
                    {row.data_sources.join(", ")}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={riskTone(row.risk_flags)}>
                    {row.risk_flags.length ? row.risk_flags.length : "clear"}
                  </Badge>
                  <div className="mt-2 grid gap-1 text-xs text-neutral-500">
                    {row.risk_flags.map((flag) => (
                      <span key={flag}>{flag}</span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
            {!report.rows.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-sm text-neutral-600" colSpan={6}>
                  No prompt-version benchmark evidence is available for this scope.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </>
  );
}
