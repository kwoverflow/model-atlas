import Link from "next/link";

import { Badge } from "@/components/Badge";
import { JudgeLabelImportForm } from "@/components/JudgeLabelImportForm";
import { JudgeLabelReviewDecisionForm } from "@/components/JudgeLabelReviewDecisionForm";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import { percent } from "@/lib/statusPresentation";
import type { JudgeLabelScoreSource } from "@/types/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  benchmark_run_id?: string;
  benchmark_result_id?: string;
}>;

const sourceLabels: Record<JudgeLabelScoreSource, string> = {
  applied_judge_label: "Applied judge",
  human_reviewed: "Human reviewed",
  candidate_judge_label: "Candidate judge",
  heuristic: "Heuristic",
  raw_label: "Raw label",
  unlabeled: "Unlabeled"
};

function sourceTone(
  source: JudgeLabelScoreSource
): "teal" | "amber" | "rose" | "violet" | "neutral" {
  if (source === "applied_judge_label") return "teal";
  if (source === "human_reviewed") return "teal";
  if (source === "candidate_judge_label") return "amber";
  if (source === "heuristic") return "violet";
  if (source === "unlabeled") return "rose";
  return "neutral";
}

function score(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(3);
}

function labelScore(labels: Record<string, unknown> | null, key: string): string {
  const value = labels?.[key];
  return typeof value === "number" ? value.toFixed(3) : "n/a";
}

function textValue(value: unknown): string {
  return typeof value === "string" && value ? value : "None";
}

export default async function JudgeLabelsPage({ searchParams }: { searchParams: SearchParams }) {
  const resolvedSearchParams = await searchParams;
  const benchmarkRunId = resolvedSearchParams.benchmark_run_id || undefined;
  const benchmarkResultId = resolvedSearchParams.benchmark_result_id || undefined;
  const [runs, review] = await Promise.all([
    api.benchmarkRuns(),
    api.judgeLabelReview({ benchmarkRunId, benchmarkResultId })
  ]);
  const selectedRun = runs.find((run) => run.id === benchmarkRunId);

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Judge Review</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Calibration view for heuristic scores, imported candidate labels, and applied human
              or LLM judge labels.
            </p>
          </div>
          <Badge tone={review.needs_review_count ? "amber" : "teal"}>
            {benchmarkResultId
              ? "Focused result"
              : review.needs_review_count
                ? "Review needed"
                : "Calibrated"}
          </Badge>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <form className="flex flex-wrap items-end gap-3" action="/judge-labels">
          <label className="grid min-w-80 flex-1 gap-2 text-sm font-medium text-neutral-700">
            Benchmark run
            <select
              name="benchmark_run_id"
              defaultValue={benchmarkRunId ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All benchmark runs</option>
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.runtime_name} - {run.data_source} - {run.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white"
          >
            Filter
          </button>
          {benchmarkRunId ? (
            <Link className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium" href="/judge-labels">
              All runs
            </Link>
          ) : null}
          <Link
            className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium"
            href="/reference-workload/review-plan"
          >
            Prioritized plan
          </Link>
        </form>
        {selectedRun ? (
          <div className="mt-3 text-xs text-neutral-500">
            Selected run {selectedRun.id} - {selectedRun.runtime_name} - {selectedRun.status}
            {benchmarkResultId ? ` - focused result ${benchmarkResultId}` : ""}
          </div>
        ) : null}
        {benchmarkResultId && benchmarkRunId ? (
          <Link
            className="mt-3 inline-flex text-xs font-medium text-teal hover:underline"
            href={`/judge-labels?benchmark_run_id=${benchmarkRunId}`}
          >
            Show every result in this run
          </Link>
        ) : null}
      </section>

      <JudgeLabelImportForm
        runs={runs}
        selectedBenchmarkRunId={benchmarkRunId}
      />

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7" aria-label="Judge review coverage">
        <SummaryCard label="Results" value={review.result_count} detail="reviewable samples" />
        <SummaryCard label="Heuristic only" value={review.heuristic_only_count} detail="deterministic scorer" tone="violet" />
        <SummaryCard label="Candidates" value={review.candidate_label_count} detail="not yet applied" tone="amber" />
        <SummaryCard label="Applied" value={review.applied_label_count} detail="judge labels" tone="teal" />
        <SummaryCard label="Human reviewed" value={review.human_reviewed_count} detail="explicit provenance" tone="teal" />
        <SummaryCard label="Applied coverage" value={percent(review.applied_label_coverage_rate)} detail="all results" tone={review.applied_label_coverage_rate >= 0.2 ? "teal" : "amber"} />
        <SummaryCard label="Critical review" value={percent(review.critical_review_coverage_rate)} detail={`${review.critical_reviewed_count}/${review.critical_result_count} critical`} tone={review.critical_result_count && review.critical_review_coverage_rate === 0 ? "rose" : "teal"} />
      </section>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Calibration Rows
        </div>
        <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Sample</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Scores</th>
              <th className="px-4 py-3">Candidate</th>
              <th className="px-4 py-3">Delta</th>
              <th className="px-4 py-3">Judge</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {review.rows.map((row) => (
              <tr key={row.benchmark_result_id} className="border-t border-line align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">
                    {row.external_case_id ?? row.sample_id}
                  </div>
                  <div className="mt-1 max-w-xs text-xs text-neutral-500">
                    {row.title ?? row.category ?? "No linked evaluation case"}
                  </div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {row.criticality ?? "unscoped"} - {row.data_source}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={sourceTone(row.score_source)}>
                    {sourceLabels[row.score_source]}
                  </Badge>
                  {row.needs_review ? (
                    <div className="mt-2 text-xs font-medium text-amber">Review</div>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <div>Q {score(row.quality_score)}</div>
                  <div className="text-xs text-neutral-500">G {score(row.groundedness_score)}</div>
                  <div className="text-xs text-neutral-500">F {score(row.faithfulness_score)}</div>
                  <div className="mt-1 text-xs text-neutral-500">{row.human_label ?? "No label"}</div>
                </td>
                <td className="px-4 py-3">
                  <div>Q {labelScore(row.candidate_judge_labels, "quality_score")}</div>
                  <div className="text-xs text-neutral-500">
                    G {labelScore(row.candidate_judge_labels, "groundedness_score")}
                  </div>
                  <div className="text-xs text-neutral-500">
                    F {labelScore(row.candidate_judge_labels, "faithfulness_score")}
                  </div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {textValue(row.candidate_judge_labels?.human_label)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {row.quality_delta_vs_candidate === null
                    ? "n/a"
                    : row.quality_delta_vs_candidate.toFixed(3)}
                </td>
                <td className="px-4 py-3">
                  <div>{textValue(row.judge_label_metadata?.source)}</div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {textValue(row.judge_label_metadata?.judge_model)}
                  </div>
                  {row.scorer_metadata ? (
                    <div className="mt-1 text-xs text-neutral-500">scorer metadata present</div>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <JudgeLabelReviewDecisionForm row={row} />
                </td>
              </tr>
            ))}
            {!review.rows.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-sm text-neutral-600" colSpan={7}>
                  No benchmark results available for judge-label review.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        </div>
      </section>
    </>
  );
}
