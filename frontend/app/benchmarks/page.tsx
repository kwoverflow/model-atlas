import { Badge } from "@/components/Badge";
import { BenchmarkExplorer } from "@/components/BenchmarkExplorer";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function BenchmarksPage() {
  const [runs, artifacts, tasks, hardware, comparisons] = await Promise.all([
    api.benchmarkRuns(),
    api.modelArtifacts(),
    api.benchmarkTasks(),
    api.hardwareProfiles(),
    api.modelComparison()
  ]);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Benchmarks</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Run traceability, quality aggregation, and local inference metric comparisons.
            </p>
          </div>
          <Badge tone="amber">Synthetic demonstration data</Badge>
        </div>
      </section>
      <BenchmarkExplorer
        runs={runs}
        artifacts={artifacts}
        tasks={tasks}
        hardware={hardware}
        comparisons={comparisons}
      />
    </>
  );
}
