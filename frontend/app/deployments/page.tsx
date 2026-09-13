import Link from "next/link";

import { Badge } from "@/components/Badge";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DeploymentsPage() {
  const [configs, workloads, artifacts, hardware, gates, baselines] = await Promise.all([
    api.deploymentConfigurations(),
    api.workloads(),
    api.modelArtifacts(),
    api.hardwareProfiles(),
    api.gateEvaluations(),
    api.deploymentBaselines()
  ]);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Deployments</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Immutable local AI deployment configurations and latest gate decisions.
            </p>
          </div>
          <Badge tone="violet">Hashable configurations</Badge>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <table className="w-full text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Configuration</th>
              <th className="px-4 py-3">Model artifact</th>
              <th className="px-4 py-3">Runtime</th>
              <th className="px-4 py-3">Workload</th>
              <th className="px-4 py-3">Hardware</th>
              <th className="px-4 py-3">Latest gate</th>
              <th className="px-4 py-3">Baseline</th>
            </tr>
          </thead>
          <tbody>
            {configs.map((config) => {
              const artifact = artifacts.find((item) => item.id === config.model_artifact_id);
              const workload = workloads.find((item) => item.id === config.workload_profile_id);
              const hardwareProfile = hardware.find((item) => item.id === config.hardware_profile_id);
              const latestGate = gates.find((gate) => gate.deployment_configuration_id === config.id);
              const activeBaseline = baselines.find(
                (baseline) => baseline.deployment_configuration_id === config.id
              );
              return (
                <tr key={config.id} className="border-t border-line">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{config.name}</div>
                    <div className="font-mono text-xs text-neutral-500">{config.configuration_hash.slice(0, 16)}</div>
                    <div className="text-xs text-neutral-500">{config.status} - ctx {config.context_length}</div>
                  </td>
                  <td className="px-4 py-3">{artifact?.artifact_name ?? "Unknown"}</td>
                  <td className="px-4 py-3">{config.runtime_name} {config.runtime_version}</td>
                  <td className="px-4 py-3">{workload?.name ?? "Unknown"}</td>
                  <td className="px-4 py-3">{hardwareProfile?.name ?? "Unknown"}</td>
                  <td className="px-4 py-3">
                    {latestGate ? (
                      <Link className="font-medium text-teal" href={`/deployment-gates/${latestGate.id}`}>
                        {latestGate.verdict}
                      </Link>
                    ) : (
                      "Not evaluated"
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {activeBaseline ? (
                      <Link className="font-medium text-teal" href={`/deployment-gates/${activeBaseline.gate_evaluation_id}`}>
                        {activeBaseline.gate_evaluation_id.slice(0, 8)}
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
