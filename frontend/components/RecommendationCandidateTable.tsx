import { Badge } from "@/components/Badge";
import type { RecommendationCandidate } from "@/types/api";

type RecommendationCandidateTableProps = {
  candidates: RecommendationCandidate[];
};

export function RecommendationCandidateTable({ candidates }: RecommendationCandidateTableProps) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="border-b border-line p-4">
        <h2 className="text-base font-semibold text-ink">Ranked Candidates</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1160px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Rank</th>
              <th className="px-4 py-3">Artifact</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Quality</th>
              <th className="px-4 py-3">Latency</th>
              <th className="px-4 py-3">Tokens/sec</th>
              <th className="px-4 py-3">VRAM</th>
              <th className="px-4 py-3">Coverage</th>
              <th className="px-4 py-3">Confidence</th>
              <th className="px-4 py-3">Pareto</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {candidates.map((candidate) => (
              <tr key={candidate.artifact_id} className="align-top">
                <td className="px-4 py-3 font-semibold text-ink">{candidate.rank}</td>
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{candidate.artifact_name}</div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {candidate.provider} / {candidate.family}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge tone="neutral">{candidate.format}</Badge>
                    {candidate.quantization ? (
                      <Badge tone="amber">{candidate.quantization}</Badge>
                    ) : null}
                    {candidate.precision ? (
                      <Badge tone="violet">{candidate.precision}</Badge>
                    ) : null}
                  </div>
                </td>
                <td className="px-4 py-3 font-semibold text-ink">
                  <div>{candidate.recommendation_score.toFixed(2)}</div>
                  <div className="mt-1 text-xs font-normal text-neutral-500">
                    Raw {candidate.raw_recommendation_score.toFixed(2)}
                  </div>
                </td>
                <td className="px-4 py-3 text-neutral-700">
                  {candidate.average_quality_score?.toFixed(2) ?? "n/a"}
                </td>
                <td className="px-4 py-3 text-neutral-700">
                  {candidate.average_end_to_end_latency_ms
                    ? `${Math.round(candidate.average_end_to_end_latency_ms)} ms`
                    : "n/a"}
                </td>
                <td className="px-4 py-3 text-neutral-700">
                  {candidate.average_tokens_per_second?.toFixed(1) ?? "n/a"}
                </td>
                <td className="px-4 py-3 text-neutral-700">
                  {candidate.average_vram_usage_mb
                    ? `${Math.round(candidate.average_vram_usage_mb)} MB`
                    : "n/a"}
                </td>
                <td className="px-4 py-3 text-neutral-700">
                  {candidate.benchmark_coverage_count}
                </td>
                <td className="px-4 py-3 text-neutral-700">
                  <div>{Math.round(candidate.evidence_confidence * 100)}%</div>
                  <div className="mt-1 text-xs text-neutral-500">
                    -{Math.round(candidate.confidence_penalty * 100)}%
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={candidate.pareto_optimal ? "teal" : "neutral"}>
                    {candidate.pareto_optimal ? "Yes" : "No"}
                  </Badge>
                </td>
              </tr>
            ))}
            {!candidates.length ? (
              <tr>
                <td className="px-4 py-6 text-neutral-500" colSpan={10}>
                  No eligible recommendation candidates.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
