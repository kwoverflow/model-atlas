import { Badge } from "@/components/Badge";
import { RecommendationCandidateTable } from "@/components/RecommendationCandidateTable";
import { RecommendationDetails } from "@/components/RecommendationDetails";
import { RecommendationExportActions } from "@/components/RecommendationExportActions";
import { RecommendationFilters } from "@/components/RecommendationFilters";
import { RecommendationScenarioList } from "@/components/RecommendationScenarioList";
import { RecommendationSummary } from "@/components/RecommendationSummary";
import { SaveScenarioForm } from "@/components/SaveScenarioForm";
import { api } from "@/lib/api";
import {
  buildRecommendationParams,
  type SearchParamRecord
} from "@/lib/recommendationParams";

export const dynamic = "force-dynamic";

type SearchParams = Promise<SearchParamRecord>;

export default async function RecommendationsPage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const resolvedSearchParams = await searchParams;
  const recommendationParams = buildRecommendationParams(resolvedSearchParams);
  const [hardware, tasks, report, scenarios] = await Promise.all([
    api.hardwareProfiles(),
    api.benchmarkTasks(),
    api.recommendationReport(recommendationParams),
    api.recommendationScenarios()
  ]);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Candidate Discovery</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Non-binding artifact ranking for deciding which candidates deserve Deployment Gate
              evaluation.
            </p>
          </div>
          <Badge tone="amber">Synthetic benchmark evidence</Badge>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <RecommendationFilters
          hardware={hardware}
          key={recommendationParams.toString()}
          tasks={tasks}
          searchParams={resolvedSearchParams}
        />
        <div className="grid gap-4">
          <SaveScenarioForm request={report.request} />
          <RecommendationExportActions params={recommendationParams} />
        </div>
      </div>
      <RecommendationScenarioList scenarios={scenarios} />
      <RecommendationSummary report={report} />
      <RecommendationCandidateTable candidates={report.candidates} />
      <RecommendationDetails report={report} />
    </>
  );
}
