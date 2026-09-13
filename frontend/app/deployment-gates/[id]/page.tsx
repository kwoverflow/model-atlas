import { Download, Factory, FileCheck2, ShieldAlert, ShieldCheck, Tags } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge } from "@/components/Badge";
import { DecisionExplanation } from "@/components/DecisionExplanation";
import { DisclosurePanel } from "@/components/DisclosurePanel";
import { EvidenceTrustPanel } from "@/components/EvidenceTrustPanel";
import { PromoteBaselineButton } from "@/components/PromoteBaselineButton";
import { StatusSummaryGrid } from "@/components/StatusSummaryGrid";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type { EvidenceTrustSummary } from "@/types/api";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function DeploymentGatePage({ params }: PageProps) {
  const { id } = await params;
  const [gate, baselines] = await Promise.all([
    api.gateEvaluation(id),
    api.deploymentBaselines()
  ]);
  if (!gate) notFound();

  const metrics = gate.scorecard_json.metrics ?? {};
  const ruleResults = gate.scorecard_json.rule_results ?? [];
  const criticalCases = gate.scorecard_json.critical_case_outcomes ?? [];
  const failedRules = ruleResults.filter((rule) => rule.status === "fail");
  const insufficientRules = ruleResults.filter((rule) => rule.status === "insufficient");
  const failedCritical = criticalCases.filter((item) => item.status === "fail");
  const baseline = gate.scorecard_json.baseline_comparison;
  const snapshotTrust = gate.evidence_snapshot_json.evidence_trust as
    | EvidenceTrustSummary
    | undefined;
  const evidenceTrust = gate.scorecard_json.evidence_trust ?? snapshotTrust;
  const schemaVersion = String(
    gate.evidence_snapshot_json.schema_version ?? "legacy-gate-evidence-snapshot-v1"
  );
  const activeScopeBaseline = baselines.find(
    (item) =>
      item.deployment_configuration_id === gate.deployment_configuration_id &&
      item.evaluation_suite_id === gate.evaluation_suite_id &&
      item.acceptance_policy_id === gate.acceptance_policy_id
  );
  const isActiveBaseline = activeScopeBaseline?.gate_evaluation_id === gate.id;

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Deployment Gate</div>
            <h1 className="mt-1 text-2xl font-semibold text-ink">Decision report</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-neutral-600">
              {gate.decision_summary}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(gate.status)}>{statusLabel(gate.status)}</Badge>
            <Badge tone={statusTone(gate.verdict)}>{gate.verdict}</Badge>
            <a
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium"
              href={`${API_BASE_URL}/deployment-gates/evaluations/${gate.id}/report.md`}
            >
              <Download size={16} aria-hidden="true" />
              Markdown
            </a>
            <a
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 text-sm font-medium"
              href={`${API_BASE_URL}/deployment-gates/evaluations/${gate.id}/report.pdf`}
            >
              <Download size={16} aria-hidden="true" />
              PDF
            </a>
          </div>
        </div>
      </section>

      {gate.status === "stale" ? (
        <section className="flex flex-wrap items-center justify-between gap-3 border-l-4 border-rose bg-rose/5 px-4 py-3">
          <div className="flex min-w-0 items-start gap-3">
            <ShieldAlert className="mt-0.5 shrink-0 text-rose" size={18} aria-hidden="true" />
            <div>
              <div className="text-sm font-semibold text-rose">Evidence revision changed</div>
              <div className="mt-1 text-sm text-neutral-700">
                {gate.stale_reason ?? "This Gate must be evaluated again before release."}
              </div>
            </div>
          </div>
          <Link
            href="/deployment-gates/new"
            className="inline-flex h-9 items-center rounded-md bg-ink px-3 text-sm font-medium text-white"
          >
            Run new Gate
          </Link>
        </section>
      ) : null}

      <StatusSummaryGrid
        items={[
          {
            label: "Gate Verdict",
            value: gate.verdict,
            detail: "Absolute acceptance-policy outcome.",
            icon: ShieldCheck
          },
          {
            label: "Evidence Trust",
            value: evidenceTrust?.trust_status ?? "Unknown",
            detail: evidenceTrust?.reasons[0] ?? "Legacy snapshot has no trust summary.",
            icon: Tags
          },
          {
            label: "Release Readiness",
            value: "Not evaluated here",
            detail: "Open Release Readiness for baseline, regression, review, and lineage checks.",
            icon: FileCheck2
          },
          {
            label: "Production Readiness",
            value: evidenceTrust?.production_readiness ?? "Unknown",
            detail: "Production evidence interpretation, separate from policy pass/fail.",
            icon: Factory
          }
        ]}
      />

      <DecisionExplanation explanation={gate.scorecard_json.decision_explanation} />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Gate evidence counts">
        <SummaryCard
          label="Blocking rules"
          value={failedRules.filter((rule) => rule.severity === "blocker").length}
          detail={`${insufficientRules.length} insufficient`}
          tone={failedRules.length || insufficientRules.length ? "rose" : "teal"}
        />
        <SummaryCard
          label="Critical failures"
          value={failedCritical.length}
          detail={`${criticalCases.length} critical outcomes`}
          tone={failedCritical.length ? "rose" : "teal"}
        />
        <SummaryCard
          label="Results"
          value={String(gate.evidence_snapshot_json.result_count ?? 0)}
          detail="selected evidence rows"
        />
        <SummaryCard
          label="Completed runs"
          value={
            (gate.evidence_snapshot_json.benchmark_run_ids as string[] | undefined)?.length ?? 0
          }
          detail="frozen run references"
          tone="violet"
        />
      </section>

      {gate.scorecard_json.synthetic_data_warning ? (
        <section className="border-l-4 border-amber bg-amber/5 px-4 py-3 text-sm leading-6 text-neutral-700">
          {gate.scorecard_json.synthetic_data_warning}
        </section>
      ) : null}

      <EvidenceTrustPanel evidence={evidenceTrust} legacy={!evidenceTrust} />

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Critical case review</h2>
            <p className="mt-1 text-sm text-neutral-600">Critical failures block the gate regardless of aggregate averages.</p>
          </div>
          <Badge tone={failedCritical.length ? "rose" : "teal"}>
            {failedCritical.length ? `${failedCritical.length} failed` : "No failures"}
          </Badge>
        </div>
        <div className="divide-y divide-line">
          {criticalCases.map((item) => (
            <div key={`${item.case_id}-${item.benchmark_run_id}-${item.sample_id}`} className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
              <div>
                <div className="text-sm font-medium text-ink">{item.external_case_id} · {item.title}</div>
                <div className="mt-1 text-xs text-neutral-500">{item.category} · {statusLabel(item.data_source)}</div>
                {item.tool_execution_status ? (
                  <Link
                    href={`/benchmark-executions/${item.benchmark_run_id}`}
                    className="mt-2 inline-flex text-xs font-medium text-teal hover:underline"
                  >
                    Tool trace: {statusLabel(item.tool_execution_status)}
                  </Link>
                ) : null}
                {item.rag_evaluation_status ? (
                  <Link
                    href={`/benchmark-executions/${item.benchmark_run_id}`}
                    className="mt-2 ml-3 inline-flex text-xs font-medium text-teal hover:underline"
                  >
                    RAG trace: {statusLabel(item.rag_evaluation_status)}
                  </Link>
                ) : null}
                {item.runtime_reliability_status ? (
                  <Link
                    href={`/benchmark-executions/${item.benchmark_run_id}`}
                    className="mt-2 ml-3 inline-flex text-xs font-medium text-teal hover:underline"
                  >
                    Reliability trace: {statusLabel(item.runtime_reliability_status)}
                  </Link>
                ) : null}
                {item.agent_execution_status ? (
                  <Link
                    href={`/benchmark-executions/${item.benchmark_run_id}`}
                    className="mt-2 ml-3 inline-flex text-xs font-medium text-teal hover:underline"
                  >
                    Agent trace: {statusLabel(item.agent_execution_status)}
                  </Link>
                ) : null}
                {item.agent_halt_reason ? (
                  <div className="mt-2 ml-3 text-xs text-rose">
                    Halt: {statusLabel(item.agent_halt_reason)}
                  </div>
                ) : null}
                {item.agent_replan_count ? (
                  <div className="mt-1 ml-3 text-xs text-neutral-500">
                    Replans: {item.agent_replan_count}
                  </div>
                ) : null}
                {item.agent_pending_approval_count ? (
                  <div className="mt-1 ml-3 text-xs text-amber-700">
                    Pending approvals: {item.agent_pending_approval_count}
                  </div>
                ) : null}
              </div>
              <div className="text-right">
                <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                <div className="mt-1 text-xs text-neutral-500">quality {item.quality_score ?? "n/a"}</div>
              </div>
            </div>
          ))}
          {!criticalCases.length ? <div className="px-5 py-6 text-sm text-neutral-600">No critical case outcomes are stored.</div> : null}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold text-ink">Policy rule results</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Rule</th>
                <th className="px-4 py-3">Metric</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {ruleResults.map((rule) => (
                <tr key={rule.rule_id}>
                  <td className="px-4 py-3 font-medium text-ink">{rule.rule_name}</td>
                  <td className="px-4 py-3 text-neutral-700">{rule.metric_key}</td>
                  <td className="px-4 py-3"><Badge tone={statusTone(rule.status)}>{statusLabel(rule.status)}</Badge></td>
                  <td className="px-4 py-3 text-neutral-700">{rule.severity}</td>
                  <td className="px-4 py-3 text-neutral-700">{rule.metric_value ?? "n/a"}</td>
                </tr>
              ))}
              {!ruleResults.length ? <tr><td colSpan={5} className="px-4 py-6 text-neutral-500">No policy rule results are stored.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-ink">Baseline and release handoff</h2>
            <div className="mt-3 grid gap-1 text-sm text-neutral-700">
              <div>Active scope baseline: {activeScopeBaseline?.gate_evaluation_id ?? "None"}</div>
              <div>Compared baseline: {baseline?.baseline_gate_evaluation_id ?? "None"}</div>
              <div>Quality delta: {baseline?.quality_regression_vs_baseline ?? "n/a"}</div>
              <div>Latency delta: {baseline?.latency_regression_vs_baseline ?? "n/a"}</div>
            </div>
          </div>
          <div className="flex flex-col items-start gap-3">
            <PromoteBaselineButton
              gateId={gate.id}
              canPromote={gate.status === "completed" && gate.verdict === "APPROVED"}
              isActiveBaseline={isActiveBaseline}
            />
            <Link href="/release-readiness" className="text-sm font-medium text-teal hover:underline">
              Open Release Readiness
            </Link>
          </div>
        </div>
      </section>

      <DisclosurePanel title="Metrics and regression">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="text-xs uppercase text-neutral-500">
              <tr><th className="pb-3">Metric</th><th className="pb-3">Value</th><th className="pb-3">Samples</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {Object.entries(metrics).map(([key, metric]) => (
                <tr key={key}><td className="py-3 font-medium text-ink">{key}</td><td className="py-3">{metric.value ?? "n/a"}</td><td className="py-3">{metric.sample_size}</td></tr>
              ))}
              {!Object.keys(metrics).length ? <tr><td colSpan={3} className="py-4 text-neutral-500">No metrics are stored.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </DisclosurePanel>

      <DisclosurePanel title="Provenance, hashes, and raw snapshot">
        <dl className="grid gap-3 text-sm md:grid-cols-2">
          <HashRow label="Snapshot schema" value={schemaVersion} />
          <HashRow label="Evidence trust version" value={String(gate.evidence_snapshot_json.evidence_trust_version ?? "unavailable")} />
          <HashRow label="Tool registry versions" value={formatVersions(gate.evidence_snapshot_json.tool_registry_versions)} />
          <HashRow label="Tool execution versions" value={formatVersions(gate.evidence_snapshot_json.tool_execution_versions)} />
          <HashRow label="RAG corpus versions" value={formatVersions(gate.evidence_snapshot_json.rag_corpus_versions)} />
          <HashRow label="Retriever versions" value={formatVersions(gate.evidence_snapshot_json.retriever_versions)} />
          <HashRow label="RAG evaluation versions" value={formatVersions(gate.evidence_snapshot_json.rag_evaluation_versions)} />
          <HashRow label="Runtime reliability versions" value={formatVersions(gate.evidence_snapshot_json.runtime_reliability_versions)} />
          <HashRow label="Agent runtime versions" value={formatVersions(gate.evidence_snapshot_json.agent_runtime_versions)} />
          <HashRow label="Agent execution versions" value={formatVersions(gate.evidence_snapshot_json.agent_execution_versions)} />
          <HashRow label="Operational memory versions" value={formatVersions(gate.evidence_snapshot_json.operational_memory_registry_versions)} />
          <HashRow label="Agent observation versions" value={formatVersions(gate.evidence_snapshot_json.agent_observation_versions)} />
          <HashRow label="Agent recovery policies" value={formatVersions(gate.evidence_snapshot_json.agent_recovery_policy_versions)} />
          <HashRow label="Agent approval policies" value={formatVersions(gate.evidence_snapshot_json.agent_approval_policy_versions)} />
          <HashRow label="Decision hash" value={gate.decision_hash} />
          <HashRow label="Configuration hash" value={String(gate.evidence_snapshot_json.configuration_hash ?? "unavailable")} />
          <HashRow label="Suite hash" value={String(gate.evidence_snapshot_json.suite_hash ?? "unavailable")} />
          <HashRow label="Policy hash" value={String(gate.evidence_snapshot_json.policy_hash ?? "unavailable")} />
        </dl>
        <pre className="mt-5 max-h-[520px] overflow-auto rounded-md bg-neutral-950 p-4 text-xs leading-5 text-neutral-100">
          {JSON.stringify(gate.evidence_snapshot_json, null, 2)}
        </pre>
      </DisclosurePanel>
    </>
  );
}

function HashRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase text-neutral-500">{label}</dt>
      <dd className="mt-1 break-all font-mono text-xs text-neutral-700">{value}</dd>
    </div>
  );
}

function formatVersions(value: unknown): string {
  return Array.isArray(value) && value.length ? value.map(String).join(", ") : "unavailable";
}
