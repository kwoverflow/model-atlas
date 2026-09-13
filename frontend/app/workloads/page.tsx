import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WorkloadsPage() {
  const [workloads, suites, cases, policies, baselines] = await Promise.all([
    api.workloads(),
    api.evaluationSuites(),
    api.evaluationCases(),
    api.acceptancePolicies(),
    api.deploymentBaselines()
  ]);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Workloads</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Versioned workload contracts, evaluation suites, policy coverage, and evidence mix.
            </p>
          </div>
          <Badge tone="teal">Deployment Gate</Badge>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <SummaryCard label="Workloads" value={workloads.length} detail="active approval scopes" />
        <SummaryCard label="Suites" value={suites.length} detail="versioned case sets" tone="violet" />
        <SummaryCard label="Cases" value={cases.length} detail="acceptance checks" tone="amber" />
        <SummaryCard label="Policies" value={policies.length} detail="rule sets" tone="rose" />
      </div>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <table className="w-full text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Workload</th>
              <th className="px-4 py-3">Suites</th>
              <th className="px-4 py-3">Policies</th>
              <th className="px-4 py-3">Cases</th>
              <th className="px-4 py-3">Evidence</th>
              <th className="px-4 py-3">Approved baseline</th>
            </tr>
          </thead>
          <tbody>
            {workloads.map((workload) => {
              const workloadSuites = suites.filter((suite) => suite.workload_profile_id === workload.id);
              const suiteIds = new Set(workloadSuites.map((suite) => suite.id));
              const workloadCases = cases.filter((item) => suiteIds.has(item.evaluation_suite_id));
              const critical = workloadCases.filter((item) => item.criticality === "critical").length;
              const synthetic = workloadCases.filter((item) => item.data_source === "synthetic_demo").length;
              const real = workloadCases.length - synthetic;
              const workloadPolicies = policies.filter((policy) => policy.workload_profile_id === workload.id);
              const approved = baselines.find((baseline) => {
                const suite = suites.find((item) => item.id === baseline.evaluation_suite_id);
                return suite?.workload_profile_id === workload.id;
              });
              return (
                <tr key={workload.id} className="border-t border-line">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{workload.name}</div>
                    <div className="text-xs text-neutral-500">{workload.domain} - {workload.primary_language}</div>
                  </td>
                  <td className="px-4 py-3">{workloadSuites.length}</td>
                  <td className="px-4 py-3">{workloadPolicies.length}</td>
                  <td className="px-4 py-3">{workloadCases.length} total - {critical} critical</td>
                  <td className="px-4 py-3">{real} real - {synthetic} synthetic</td>
                  <td className="px-4 py-3">
                    {approved ? (
                      <Link className="font-medium text-teal" href={`/deployment-gates/${approved.gate_evaluation_id}`}>
                        {approved.gate_evaluation_id.slice(0, 8)}
                      </Link>
                    ) : (
                      "None"
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}
