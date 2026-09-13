import { Badge } from "@/components/Badge";
import { BenchmarkExecutionForm } from "@/components/BenchmarkExecutionForm";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function NewBenchmarkExecutionPage() {
  const [
    configurations,
    suites,
    tasks,
    prompts,
    runs,
    toolRegistry,
    ragCorpusRegistry,
    ragRetriever,
    agentRuntime,
    operationalMemoryRegistry
  ] = await Promise.all([
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.benchmarkTasks(),
    api.promptVersions(),
    api.benchmarkRuns(),
    api.toolRegistry(),
    api.ragCorpusRegistry(),
    api.ragRetriever(),
    api.agentRuntime(),
    api.operationalMemoryRegistry()
  ]);
  const executableRuns = runs.filter((run) => run.deployment_configuration_id);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Benchmark Execution</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Generate gate-ready benchmark evidence through a local inference adapter.
            </p>
          </div>
          <Badge tone="teal">Sprint 5B evaluation packs</Badge>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        <SummaryCard label="Configurations" value={configurations.length} detail="ready candidates" />
        <SummaryCard label="Suites" value={suites.length} detail="case sets" tone="violet" />
        <SummaryCard label="Executed runs" value={executableRuns.length} detail="gate-linked runs" tone="amber" />
      </div>

      <BenchmarkExecutionForm
        configurations={configurations}
        suites={suites}
        tasks={tasks}
        prompts={prompts}
        toolRegistry={toolRegistry}
        ragCorpusRegistry={ragCorpusRegistry}
        ragRetriever={ragRetriever}
        agentRuntime={agentRuntime}
        operationalMemoryRegistry={operationalMemoryRegistry}
      />
    </>
  );
}
