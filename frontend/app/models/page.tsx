import { Badge } from "@/components/Badge";
import { ModelsTable } from "@/components/ModelsTable";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ModelsPage() {
  const [models, artifacts, hardware, comparisons] = await Promise.all([
    api.models(),
    api.modelArtifacts(),
    api.hardwareProfiles(),
    api.modelComparison()
  ]);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Models</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Catalog of logical models, local artifacts, capability coverage, and workstation fit.
            </p>
          </div>
          <Badge tone="amber">Seeded values are synthetic</Badge>
        </div>
      </section>

      <ModelsTable
        models={models}
        artifacts={artifacts}
        hardware={hardware}
        comparisons={comparisons}
      />

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line p-4">
          <h2 className="text-base font-semibold text-ink">Benchmark Summaries</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Artifact</th>
                <th className="px-4 py-3">Task</th>
                <th className="px-4 py-3">Quality</th>
                <th className="px-4 py-3">Latency</th>
                <th className="px-4 py-3">Tokens/sec</th>
                <th className="px-4 py-3">Coverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {comparisons.map((row) => (
                <tr key={`${row.model_artifact_id}-${row.benchmark_task_id}`}>
                  <td className="px-4 py-3 font-medium text-ink">{row.artifact_name}</td>
                  <td className="px-4 py-3 text-neutral-700">{row.benchmark_task_name}</td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_quality_score !== null
                      ? row.average_quality_score.toFixed(2)
                      : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_end_to_end_latency_ms !== null
                      ? `${Math.round(row.average_end_to_end_latency_ms)} ms`
                      : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {row.average_tokens_per_second !== null
                      ? row.average_tokens_per_second.toFixed(1)
                      : "n/a"}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">{row.benchmark_coverage_count}</td>
                </tr>
              ))}
              {!comparisons.length ? (
                <tr>
                  <td className="px-4 py-6 text-neutral-500" colSpan={6}>
                    No benchmark comparison rows available.
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
