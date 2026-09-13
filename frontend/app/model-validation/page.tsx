import { Badge } from "@/components/Badge";
import { ModelValidationConsole } from "@/components/ModelValidationConsole";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  deployment_configuration_id?: string;
  evaluation_suite_id?: string;
}>;

export default async function ModelValidationPage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const selected = await searchParams;
  const [configurations, suites, tasks, prompts] = await Promise.all([
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.benchmarkTasks(),
    api.promptVersions()
  ]);
  const initialConfiguration =
    configurations.find(
      (configuration) => configuration.id === selected.deployment_configuration_id
    ) ?? configurations[0];
  const initialSuite = suites.find(
    (suite) => suite.id === selected.evaluation_suite_id
  ) ?? suites.find(
    (suite) =>
      !initialConfiguration ||
      (suite.workload_profile_id === initialConfiguration.workload_profile_id &&
        !suite.is_synthetic)
  ) ?? suites.find(
    (suite) =>
      !initialConfiguration ||
      suite.workload_profile_id === initialConfiguration.workload_profile_id
  );
  const initialReport =
    initialConfiguration && initialSuite
      ? await api.modelValidationReport(
          new URLSearchParams({
            deployment_configuration_id: initialConfiguration.id,
            evaluation_suite_id: initialSuite.id
          })
        )
      : null;

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Model Validation</h1>
            <p className="mt-2 text-sm text-neutral-600">
              Local runtime campaigns, evidence cohorts, and judge calibration.
            </p>
          </div>
          <Badge tone="teal">Sprint 5G</Badge>
        </div>
      </section>

      <ModelValidationConsole
        configurations={configurations}
        suites={suites}
        tasks={tasks}
        prompts={prompts}
        initialConfigurationId={initialConfiguration?.id ?? ""}
        initialSuiteId={initialSuite?.id ?? ""}
        initialReport={initialReport}
      />
    </>
  );
}
