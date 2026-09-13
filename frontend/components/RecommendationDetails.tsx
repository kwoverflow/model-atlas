import type { RecommendationReport } from "@/types/api";

type RecommendationDetailsProps = {
  report: RecommendationReport;
};

export function RecommendationDetails({ report }: RecommendationDetailsProps) {
  return (
    <section className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <h2 className="text-base font-semibold text-ink">Top Rationale</h2>
        {report.recommended_candidate ? (
          <ul className="mt-3 grid gap-2 text-sm text-neutral-700">
            {report.recommended_candidate.rationale.map((item) => (
              <li key={item} className="rounded-md border border-line px-3 py-2">
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-neutral-600">No rationale available.</p>
        )}
      </div>
      <div className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <h2 className="text-base font-semibold text-ink">Excluded Artifacts</h2>
        <div className="mt-3 grid gap-2">
          {report.excluded.slice(0, 8).map((issue) => (
            <div
              key={`${issue.artifact_name}-${issue.reason_code}`}
              className="rounded-md border border-line px-3 py-2 text-sm"
            >
              <div className="font-medium text-ink">{issue.artifact_name}</div>
              <div className="mt-1 text-neutral-600">{issue.message}</div>
            </div>
          ))}
          {!report.excluded.length ? (
            <p className="text-sm text-neutral-600">No artifacts were excluded.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
