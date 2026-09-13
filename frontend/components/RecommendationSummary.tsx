import { SummaryCard } from "@/components/SummaryCard";
import type { RecommendationReport } from "@/types/api";

type RecommendationSummaryProps = {
  report: RecommendationReport;
};

export function RecommendationSummary({ report }: RecommendationSummaryProps) {
  const top = report.recommended_candidate;

  return (
    <>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          label="Top score"
          value={top?.recommendation_score.toFixed(2) ?? "n/a"}
          detail={top ? `Raw ${top.raw_recommendation_score.toFixed(2)}` : "No eligible artifact"}
          tone="teal"
        />
        <SummaryCard
          label="Eligible"
          value={`${report.eligible_count}/${report.candidate_count}`}
          detail={report.hardware_profile_name}
          tone="violet"
        />
        <SummaryCard
          label="Pareto frontier"
          value={report.pareto_frontier.length}
          detail={report.benchmark_task_name ?? "All tasks"}
          tone="amber"
        />
        <SummaryCard
          label="Evidence confidence"
          value={top ? `${Math.round(top.evidence_confidence * 100)}%` : "n/a"}
          detail={top ? `${top.benchmark_coverage_count} benchmark run(s)` : "No evidence"}
          tone="rose"
        />
      </section>

      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <h2 className="text-base font-semibold text-ink">Decision Summary</h2>
        <p className="mt-2 text-sm leading-6 text-neutral-600">{report.decision_summary}</p>
      </section>
    </>
  );
}
