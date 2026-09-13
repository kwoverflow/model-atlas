import {
  ArrowLeft,
  ExternalLink,
  FileJson,
  ShieldAlert
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { statusLabel } from "@/lib/statusPresentation";
import type { ReferenceReviewPriority } from "@/types/api";

export const dynamic = "force-dynamic";

function priorityTone(priority: ReferenceReviewPriority): "rose" | "amber" | "neutral" {
  if (priority === "P0") return "rose";
  if (priority === "P1") return "amber";
  return "neutral";
}

function score(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(3);
}

export default async function ReferenceOutputReviewPlanPage() {
  const plan = await api.referenceOutputReviewPlan(30);

  return (
    <>
      <header className="border-b border-line pb-5">
        <Link
          href="/reference-workload"
          className="inline-flex items-center gap-2 text-sm font-medium text-teal hover:underline"
        >
          <ArrowLeft size={16} aria-hidden="true" /> Reference Workload
        </Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-4xl">
            <div className="text-sm font-medium text-teal">Output review plan</div>
            <h1 className="mt-2 text-2xl font-semibold text-ink">
              Prioritized critical evidence
            </h1>
            <p className="mt-2 text-sm leading-6 text-neutral-600">
              {plan.total_failure_count} stored critical outcomes grouped into {plan.cluster_count}{" "}
              repeatable failure clusters. Candidate assessments remain unapplied.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={plan.status === "ready_for_human_review" ? "amber" : "neutral"}>
              {statusLabel(plan.status)}
            </Badge>
            <a
              href={`${API_BASE_URL}/reference-workload/output-review-plan?target_count=30`}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium text-ink hover:bg-neutral-50"
              title="Open the output review plan as JSON"
            >
              <FileJson size={16} aria-hidden="true" /> JSON
            </a>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-neutral-500">
          <span>Plan {plan.plan_hash.slice(0, 16)}</span>
          <span>Comparison {plan.comparison_hash.slice(0, 16)}</span>
        </div>
      </header>

      <section className="border-y border-line bg-amber-50 px-4 py-3" aria-label="Review boundary">
        <div className="flex items-start gap-3">
          <ShieldAlert size={19} className="mt-0.5 shrink-0 text-amber-700" aria-hidden="true" />
          <div>
            <div className="text-sm font-semibold text-amber-950">Human decision required</div>
            <p className="mt-1 text-sm leading-6 text-amber-900">
              Selected rows are review suggestions only. Applied reviews remain {plan.currently_human_reviewed_count};
              the outstanding target remains {plan.remaining_human_review_target}.
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7" aria-label="Review plan summary">
        <SummaryCard label="Failure outcomes" value={plan.total_failure_count} detail="selected portfolio runs" tone="rose" />
        <SummaryCard label="Failure clusters" value={plan.cluster_count} detail="case and reason groups" tone="violet" />
        <SummaryCard label="Selected outputs" value={plan.selected_result_count} detail={`target ${plan.target_review_count}`} tone="amber" />
        <SummaryCard label="Cases covered" value={plan.selected_unique_case_count} detail="unique critical cases" />
        <SummaryCard label="Categories" value={plan.selected_category_count} detail="risk taxonomy coverage" />
        <SummaryCard label="Configurations" value={plan.selected_configuration_count} detail="runtime matrix coverage" />
        <SummaryCard label="Human reviewed" value={plan.currently_human_reviewed_count} detail={`${plan.remaining_human_review_target} remaining`} tone="amber" />
      </section>

      <section className="border-t border-line pt-6" aria-labelledby="failure-clusters">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="failure-clusters" className="text-base font-semibold text-ink">Failure clusters</h2>
            <p className="mt-1 text-sm text-neutral-600">
              P0 reproduces across every selected configuration; P1 is repeated or cross-configuration.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <Badge tone="rose">P0 {plan.clusters.filter((item) => item.priority === "P0").length}</Badge>
            <Badge tone="amber">P1 {plan.clusters.filter((item) => item.priority === "P1").length}</Badge>
            <Badge tone="neutral">P2 {plan.clusters.filter((item) => item.priority === "P2").length}</Badge>
          </div>
        </div>
        <div className="overflow-x-auto border-y border-line bg-panel">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Case</th>
                <th className="px-4 py-3">Failure</th>
                <th className="px-4 py-3">Occurrences</th>
                <th className="px-4 py-3">Configurations</th>
                <th className="px-4 py-3">Unreviewed</th>
                <th className="px-4 py-3">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {plan.clusters.map((cluster) => (
                <tr key={cluster.cluster_key} className="align-top">
                  <td className="px-4 py-3"><Badge tone={priorityTone(cluster.priority)}>{cluster.priority}</Badge></td>
                  <td className="max-w-64 px-4 py-3">
                    <div className="font-semibold text-ink">{cluster.title}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">{cluster.external_case_id}</div>
                    <div className="mt-1 text-xs text-neutral-500">{statusLabel(cluster.category)}</div>
                  </td>
                  <td className="px-4 py-3 text-neutral-700">{statusLabel(cluster.failure_reason)}</td>
                  <td className="px-4 py-3 tabular-nums">{cluster.occurrence_count}</td>
                  <td className="max-w-64 px-4 py-3 text-xs leading-5 text-neutral-600">
                    {cluster.configuration_names.join(", ")}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{cluster.unreviewed_count}</td>
                  <td className="px-4 py-3">
                    <Link
                      href={cluster.representative_review_href}
                      aria-label={`Review representative result for ${cluster.external_case_id}`}
                      title="Open representative result"
                      className="text-neutral-600 hover:text-teal"
                    >
                      <ExternalLink size={18} aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border-t border-line pt-6" aria-labelledby="selected-review-set">
        <div className="mb-4">
          <h2 id="selected-review-set" className="text-base font-semibold text-ink">Selected review set</h2>
          <p className="mt-1 text-sm text-neutral-600">
            One representative per cluster first, followed by configuration-balanced repeated evidence.
          </p>
        </div>
        <div className="overflow-x-auto border-y border-line bg-panel">
          <table className="w-full min-w-[1280px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Rank</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Case</th>
                <th className="px-4 py-3">Configuration</th>
                <th className="px-4 py-3">Observed output</th>
                <th className="px-4 py-3">Candidate</th>
                <th className="px-4 py-3">Scores</th>
                <th className="px-4 py-3">Review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {plan.selected_items.map((item) => (
                <tr key={item.failure.benchmark_result_id} className="align-top">
                  <td className="px-4 py-3 font-mono text-xs">{item.rank}</td>
                  <td className="px-4 py-3"><Badge tone={priorityTone(item.priority)}>{item.priority}</Badge></td>
                  <td className="max-w-64 px-4 py-3">
                    <div className="font-semibold text-ink">{item.failure.title}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">{item.failure.external_case_id}</div>
                    <div className="mt-1 text-xs text-neutral-500">{item.failure.sample_id}</div>
                  </td>
                  <td className="px-4 py-3 text-neutral-700">{item.failure.entry_name}</td>
                  <td className="max-w-80 px-4 py-3 text-xs leading-5 text-neutral-600">
                    {item.failure.observed_output_summary}
                  </td>
                  <td className="max-w-72 px-4 py-3">
                    <div className="font-mono text-xs text-neutral-700">{item.candidate_assessment.candidate_label}</div>
                    <div className="mt-2 text-xs text-neutral-500">
                      {item.candidate_assessment.confidence} confidence · not applied
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs tabular-nums">
                    <div>Q {score(item.candidate_assessment.quality_score)}</div>
                    <div>G {score(item.candidate_assessment.groundedness_score)}</div>
                    <div>F {score(item.candidate_assessment.faithfulness_score)}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={item.failure.judge_review_href}
                      className="inline-flex items-center gap-2 text-sm font-medium text-teal hover:underline"
                    >
                      Inspect <ExternalLink size={15} aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="border-t border-line py-6" aria-labelledby="review-limitations">
        <h2 id="review-limitations" className="text-base font-semibold text-ink">Evidence boundary</h2>
        <ul className="mt-3 grid gap-2 text-sm leading-6 text-neutral-600">
          {plan.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      </section>
    </>
  );
}
