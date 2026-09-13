import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { api } from "@/lib/api";
import {
  formatDate,
  releaseDecisionLabels,
  releaseDecisionTone,
  shortId
} from "@/lib/releaseDecisionPresentation";
import { statusLabel, statusTone } from "@/lib/statusPresentation";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  gate_evaluation_id?: string;
}>;

function markdownHref(decisionId: string): string {
  return `${API_BASE_URL}/release-decisions/${decisionId}/report.md`;
}

export default async function ReleaseDecisionsPage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const resolvedSearchParams = await searchParams;
  const decisionParams = new URLSearchParams({ limit: "200" });
  if (resolvedSearchParams.gate_evaluation_id) {
    decisionParams.set("gate_evaluation_id", resolvedSearchParams.gate_evaluation_id);
  }

  const [decisions, gates, configs, suites, policies] = await Promise.all([
    api.releaseDecisions(decisionParams),
    api.gateEvaluations(),
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies()
  ]);
  const selectedGate = gates.find((gate) => gate.id === resolvedSearchParams.gate_evaluation_id);
  const approvals = decisions.filter((decision) => decision.decision === "APPROVE_RELEASE");
  const requests = decisions.filter((decision) => decision.decision === "REQUEST_CHANGES");
  const rejections = decisions.filter((decision) => decision.decision === "REJECT_RELEASE");
  const needsReview = decisions.filter(
    (decision) => decision.operational_status === "needs_review"
  );
  const latest = decisions[0];

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Release Decisions</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Signed records for reviewed release readiness snapshots.
            </p>
          </div>
          {latest ? (
            <Badge tone={releaseDecisionTone(latest)}>
              {releaseDecisionLabels[latest.decision]}
            </Badge>
          ) : (
            <Badge tone="neutral">No decisions</Badge>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <form className="grid gap-3 md:grid-cols-[1fr_auto_auto]" action="/release-decisions">
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Gate evaluation
            <select
              name="gate_evaluation_id"
              defaultValue={resolvedSearchParams.gate_evaluation_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All gates</option>
              {gates.map((gate) => (
                <option key={gate.id} value={gate.id}>
                  {gate.verdict} - {gate.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white"
            >
              Filter
            </button>
            <Link
              className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium"
              href="/release-decisions"
            >
              Reset
            </Link>
          </div>
          <div className="flex items-end">
            <Link
              className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium"
              href="/release-readiness"
            >
              Readiness
            </Link>
          </div>
        </form>
        <div className="mt-3 text-xs text-neutral-500">
          Scope: gate {shortId(selectedGate?.id)}
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <SummaryCard label="Decisions" value={decisions.length} detail="signed records" />
        <SummaryCard
          label="Approvals"
          value={approvals.length}
          detail="release sign-offs"
          tone="teal"
        />
        <SummaryCard
          label="Change requests"
          value={requests.length}
          detail="follow-up required"
          tone="amber"
        />
        <SummaryCard
          label="Operational review"
          value={needsReview.length}
          detail="stale or review requested"
          tone={needsReview.length ? "amber" : "teal"}
        />
        <SummaryCard
          label="Rejections"
          value={rejections.length}
          detail={latest ? formatDate(latest.decided_at) : "no latest decision"}
          tone={rejections.length ? "rose" : "violet"}
        />
      </div>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Signed Decision History
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Decision</th>
              <th className="px-4 py-3">Readiness</th>
              <th className="px-4 py-3">Scope</th>
              <th className="px-4 py-3">Reason</th>
              <th className="px-4 py-3">Hashes</th>
              <th className="px-4 py-3">Export</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map((decision) => {
              const config = configs.find(
                (item) => item.id === decision.deployment_configuration_id
              );
              const suite = suites.find((item) => item.id === decision.evaluation_suite_id);
              const policy = policies.find((item) => item.id === decision.acceptance_policy_id);
              return (
                <tr key={decision.id} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <Link href={`/release-decisions/${decision.id}`}>
                      <Badge tone={releaseDecisionTone(decision)}>
                        {releaseDecisionLabels[decision.decision]}
                      </Badge>
                    </Link>
                    <div className="mt-2">
                      <Badge tone={statusTone(decision.operational_status)}>
                        {statusLabel(decision.operational_status)}
                      </Badge>
                    </div>
                    <div className="mt-2 text-xs text-neutral-500">
                      {formatDate(decision.decided_at)}
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">{decision.decided_by}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {decision.identity_verified ? "verified" : "self-attested"}
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">
                      policy {decision.approval_policy_json.allowed ? "allowed" : "denied"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">
                      {decision.release_readiness_status}
                    </div>
                    <Link
                      className="mt-2 block text-xs font-medium text-teal"
                      href={`/deployment-gates/${decision.gate_evaluation_id}`}
                    >
                      gate {shortId(decision.gate_evaluation_id)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-600">
                    <div>{config?.name ?? shortId(decision.deployment_configuration_id)}</div>
                    <div>{suite?.name ?? shortId(decision.evaluation_suite_id)}</div>
                    <div>{policy?.name ?? shortId(decision.acceptance_policy_id)}</div>
                  </td>
                  <td className="max-w-md px-4 py-3 text-neutral-700">
                    {decision.decision_reason}
                    {decision.notes ? (
                      <div className="mt-2 text-xs text-neutral-500">{decision.notes}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-500">
                    <div>decision {shortId(decision.decision_hash)}</div>
                    <div>snapshot {shortId(decision.snapshot_hash)}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
                      <Link
                        className="rounded-md border border-line px-3 py-2 text-xs font-medium"
                        href={`/release-decisions/${decision.id}`}
                      >
                        Open
                      </Link>
                      <a
                        className="rounded-md border border-line px-3 py-2 text-xs font-medium"
                        href={markdownHref(decision.id)}
                      >
                        Markdown
                      </a>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!decisions.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-sm text-neutral-600" colSpan={6}>
                  No signed release decisions are available for this scope.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </>
  );
}
