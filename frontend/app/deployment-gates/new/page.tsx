import { Badge } from "@/components/Badge";
import { GateEvaluationForm } from "@/components/GateEvaluationForm";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function NewDeploymentGatePage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const resolvedSearchParams = await searchParams;
  const [configs, suites, policies, gates, baselines, runs, cases] = await Promise.all([
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies(),
    api.gateEvaluations(),
    api.deploymentBaselines(),
    api.benchmarkRuns(),
    api.evaluationCases()
  ]);
  const suiteIds = new Set(suites.map((suite) => suite.id));
  const gateRuns = runs.filter((run) => run.evaluation_suite_id && suiteIds.has(run.evaluation_suite_id));
  const syntheticCases = cases.filter((item) => item.data_source === "synthetic_demo").length;
  const localCases = cases.filter((item) => ["captured_local", "local_authored"].includes(item.data_source)).length;
  const productionCases = cases.filter((item) => item.data_source === "production_captured").length;
  const activeBaselineGateIds = new Set(baselines.map((baseline) => baseline.gate_evaluation_id));
  const baselineGates = gates.filter((gate) => activeBaselineGateIds.has(gate.id));
  const requestedConfigurationId = singleValue(
    resolvedSearchParams.deployment_configuration_id
  );
  const selectedConfiguration = configs.find(
    (configuration) => configuration.id === requestedConfigurationId
  );
  const selectedWorkloadId = selectedConfiguration?.workload_profile_id;
  const selectedSuite = suites.find(
    (suite) => suite.workload_profile_id === selectedWorkloadId
  );
  const selectedPolicy = policies.find(
    (policy) => policy.workload_profile_id === selectedWorkloadId
  );

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">New Deployment Gate</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Select a configuration, suite, and policy, then inspect the selected evidence before the gate is evaluated.
            </p>
          </div>
          <Badge tone={productionCases > 0 ? "teal" : localCases > 0 ? "amber" : "violet"}>
            {productionCases > 0 ? "Production evidence present" : localCases > 0 ? "Local evidence present" : "Synthetic / unknown evidence"}
          </Badge>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="Configurations" value={configs.length} detail="deployment candidates" />
        <SummaryCard label="Gate runs" value={gateRuns.length} detail="suite-linked completed runs" tone="violet" />
        <SummaryCard label="Local cases" value={localCases} detail="locally authored" tone="amber" />
        <SummaryCard label="Production cases" value={productionCases} detail={`${syntheticCases} synthetic`} tone={productionCases ? "teal" : "violet"} />
      </div>

      <GateEvaluationForm
        configurations={configs}
        suites={suites}
        policies={policies}
        baselines={baselineGates}
        initialConfigurationId={selectedConfiguration?.id}
        initialSuiteId={selectedSuite?.id}
        initialPolicyId={selectedPolicy?.id}
      />
    </>
  );
}

function singleValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}
