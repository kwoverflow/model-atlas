import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

function statusTone(status: string): "teal" | "amber" | "rose" | "violet" | "neutral" {
  if (status === "active") return "teal";
  if (status === "superseded") return "amber";
  if (status === "archived") return "violet";
  return "neutral";
}

function formatTimestamp(value: string | null): string {
  if (!value) return "None";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(new Date(value));
}

export default async function DeploymentBaselinesPage() {
  const [baselines, configs, suites, policies, gates] = await Promise.all([
    api.deploymentBaselines({ activeOnly: false }),
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies(),
    api.gateEvaluations()
  ]);
  const gatesById = new Map(gates.map((gate) => [gate.id, gate]));
  const activeBaselines = baselines.filter((baseline) => baseline.status === "active");
  const supersededBaselines = baselines.filter((baseline) => baseline.status === "superseded");
  const approvedBaselineGates = baselines.filter(
    (baseline) => gatesById.get(baseline.gate_evaluation_id)?.verdict === "APPROVED"
  );

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Deployment Baselines</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Approval history for promoted gate evaluations, including active baselines and
              superseded comparison points.
            </p>
          </div>
          <Badge tone={activeBaselines.length ? "teal" : "amber"}>
            {activeBaselines.length ? "Active baseline ready" : "No active baseline"}
          </Badge>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <SummaryCard label="Baselines" value={baselines.length} detail="promoted approvals" />
        <SummaryCard label="Active" value={activeBaselines.length} detail="current comparison points" tone="teal" />
        <SummaryCard label="Superseded" value={supersededBaselines.length} detail="retired by newer approvals" tone="amber" />
        <SummaryCard label="Approved gates" value={approvedBaselineGates.length} detail="source verdicts preserved" tone="violet" />
      </div>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Baseline History
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Scope</th>
              <th className="px-4 py-3">Gate</th>
              <th className="px-4 py-3">Promoted</th>
              <th className="px-4 py-3">Superseded By</th>
              <th className="px-4 py-3">Hash</th>
            </tr>
          </thead>
          <tbody>
            {baselines.map((baseline) => {
              const config = configs.find(
                (item) => item.id === baseline.deployment_configuration_id
              );
              const suite = suites.find((item) => item.id === baseline.evaluation_suite_id);
              const policy = policies.find((item) => item.id === baseline.acceptance_policy_id);
              const gate = gatesById.get(baseline.gate_evaluation_id);
              return (
                <tr key={baseline.id} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(baseline.status)}>{baseline.status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{config?.name ?? "Unknown config"}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {suite?.name ?? "Unknown suite"} - {policy?.name ?? "Unknown policy"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      className="font-medium text-teal"
                      href={`/deployment-gates/${baseline.gate_evaluation_id}`}
                    >
                      {gate?.verdict ?? "Gate"} {baseline.gate_evaluation_id.slice(0, 8)}
                    </Link>
                    <div className="mt-1 text-xs text-neutral-500">
                      {gate?.decision_hash.slice(0, 16) ?? "decision unavailable"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div>{formatTimestamp(baseline.promoted_at)}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {baseline.promoted_by ?? "unknown promoter"}
                    </div>
                    {baseline.promotion_reason ? (
                      <div className="mt-1 max-w-xs text-xs text-neutral-500">
                        {baseline.promotion_reason}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    {baseline.superseded_by_baseline_id ? (
                      <span className="font-mono text-xs">
                        {baseline.superseded_by_baseline_id.slice(0, 8)}
                      </span>
                    ) : (
                      "None"
                    )}
                    <div className="mt-1 text-xs text-neutral-500">
                      {formatTimestamp(baseline.superseded_at)}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                    {baseline.baseline_hash.slice(0, 16)}
                  </td>
                </tr>
              );
            })}
            {!baselines.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-sm text-neutral-600" colSpan={6}>
                  No promoted baselines yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </>
  );
}
