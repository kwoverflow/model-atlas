import { Factory, FileCheck2, GitBranch, ShieldCheck, Tags } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { DisclosurePanel } from "@/components/DisclosurePanel";
import { EvidenceTrustPanel } from "@/components/EvidenceTrustPanel";
import { ReleaseDecisionForm } from "@/components/ReleaseDecisionForm";
import { StatusSummaryGrid } from "@/components/StatusSummaryGrid";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import { API_BASE_URL } from "@/lib/apiBase";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type { ReleaseReadinessSnapshot } from "@/types/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  gate_evaluation_id?: string;
  replaces_release_decision_id?: string;
}>;

function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "none";
}

function exportHref(snapshot: ReleaseReadinessSnapshot | null, selectedGateId?: string): string {
  const gateId = selectedGateId ?? snapshot?.gate.gate_evaluation_id;
  return `${API_BASE_URL}/release-readiness/snapshot.md${gateId ? `?gate_evaluation_id=${gateId}` : ""}`;
}

export default async function ReleaseReadinessPage({ searchParams }: { searchParams: SearchParams }) {
  const resolvedSearchParams = await searchParams;
  const snapshotParams = new URLSearchParams();
  if (resolvedSearchParams.gate_evaluation_id) {
    snapshotParams.set("gate_evaluation_id", resolvedSearchParams.gate_evaluation_id);
  }
  const [gates, configs, suites, policies, snapshot] = await Promise.all([
    api.gateEvaluations(),
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies(),
    api.releaseReadinessSnapshot(snapshotParams)
  ]);
  const selectedGateId = resolvedSearchParams.gate_evaluation_id ?? snapshot?.gate.gate_evaluation_id;
  const selectedGate = gates.find((gate) => gate.id === selectedGateId);
  const selectedConfig = configs.find((item) => item.id === snapshot?.deployment_configuration_id);
  const selectedSuite = suites.find((item) => item.id === snapshot?.evaluation_suite_id);
  const selectedPolicy = policies.find((item) => item.id === snapshot?.acceptance_policy_id);

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Release Readiness</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Gate policy, evidence trust, baseline state, judge coverage, prompt regression, and
              lineage are evaluated without collapsing them into one ambiguous ready flag.
            </p>
          </div>
          <Badge tone={statusTone(snapshot?.status)}>{snapshot ? statusLabel(snapshot.status) : "No snapshot"}</Badge>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <form className="grid gap-3 md:grid-cols-[1fr_auto_auto]" action="/release-readiness">
          {resolvedSearchParams.replaces_release_decision_id ? (
            <input
              type="hidden"
              name="replaces_release_decision_id"
              value={resolvedSearchParams.replaces_release_decision_id}
            />
          ) : null}
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Gate evaluation
            <select name="gate_evaluation_id" defaultValue={resolvedSearchParams.gate_evaluation_id ?? ""} className="h-10 rounded-md border border-line bg-white px-3 text-sm">
              <option value="">Latest gate</option>
              {gates.map((gate) => <option key={gate.id} value={gate.id}>{gate.verdict} · {gate.id.slice(0, 8)}</option>)}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button type="submit" className="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white">Load</button>
            <Link className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium" href="/release-readiness">Latest</Link>
          </div>
          <div className="flex items-end">
            <a className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium" href={exportHref(snapshot, resolvedSearchParams.gate_evaluation_id)}>Markdown</a>
          </div>
        </form>
        <div className="mt-3 text-xs text-neutral-500">
          Scope: {selectedConfig?.name ?? "unknown deployment"} · {selectedSuite?.name ?? "unknown suite"} · {selectedPolicy?.name ?? "unknown policy"}
        </div>
      </section>

      {snapshot ? (
        <>
          <StatusSummaryGrid
            items={[
              { label: "Gate Verdict", value: snapshot.gate.verdict, detail: snapshot.gate.decision_summary, icon: ShieldCheck },
              { label: "Evidence Trust", value: snapshot.evidence_trust.trust_status, detail: snapshot.evidence_trust.reasons[0], icon: Tags },
              { label: "Release Readiness", value: snapshot.status, detail: snapshot.release_summary, icon: FileCheck2 },
              { label: "Production Readiness", value: snapshot.production_readiness, detail: "Requires production-captured evidence plus all release controls.", icon: Factory }
            ]}
          />

          {snapshot.evidence_trust.trust_status === "local_demo_ready" ? (
            <section className="border-l-4 border-amber bg-amber/5 px-4 py-3 text-sm leading-6 text-neutral-700">
              <div className="font-semibold text-ink">Local demonstration readiness only</div>
              <div>This configuration has sufficient locally authored and reviewed evidence for a reproducible local demonstration. It does not yet have enough production-captured evidence to be labeled production-ready.</div>
            </section>
          ) : null}

          <section className="rounded-lg border border-line bg-panel shadow-soft">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
              <div>
                <h2 className="text-base font-semibold text-ink">Readiness decision</h2>
                <p className="mt-2 max-w-4xl text-sm leading-6 text-neutral-700">{snapshot.release_summary}</p>
              </div>
              {selectedGate ? <Link className="text-sm font-medium text-teal hover:underline" href={`/deployment-gates/${selectedGate.id}`}>Open gate</Link> : null}
            </div>
            <div className="grid gap-6 px-5 py-5 lg:grid-cols-3">
              <ReasonList title="Readiness reasons" rows={snapshot.readiness_reasons} />
              <ReasonList title="Review reasons" rows={snapshot.review_reasons} />
              <ReasonList title="Next actions" rows={snapshot.next_actions} />
            </div>
          </section>

          <EvidenceTrustPanel evidence={snapshot.evidence_trust} />

          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Release control checks">
            <SummaryCard label="Baseline state" value={statusLabel(snapshot.baseline.baseline_status)} detail={shortId(snapshot.baseline.active_baseline_id)} tone={snapshot.baseline.gate_is_active_baseline ? "teal" : "violet"} />
            <SummaryCard label="Judge coverage" value={percent(snapshot.judge_calibration.applied_label_coverage_rate)} detail={`${snapshot.judge_calibration.heuristic_only_count} heuristic-only`} tone={snapshot.evidence_trust.trust_status === "needs_judge_review" ? "amber" : "teal"} />
            <SummaryCard label="Prompt regression" value={snapshot.prompt_regression.risk_row_count} detail={`${snapshot.prompt_regression.risk_flags.length} risk flag types`} tone={snapshot.prompt_regression.risk_row_count ? "amber" : "teal"} />
            <SummaryCard label="Lineage events" value={snapshot.lineage.event_count} detail={`${snapshot.lineage.lineage_count} lineage scopes`} tone={snapshot.lineage.event_count ? "teal" : "amber"} />
          </section>

          <ReleaseDecisionForm
            gateEvaluationId={snapshot.gate.gate_evaluation_id}
            readinessStatus={snapshot.status}
            replacesReleaseDecisionId={
              resolvedSearchParams.replaces_release_decision_id
            }
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
              <h2 className="text-base font-semibold text-ink">Gate evidence</h2>
              <dl className="mt-4 grid gap-3 text-sm text-neutral-700">
                <Line label="Passed / failed / insufficient rules" value={`${snapshot.gate.passed_rule_count} / ${snapshot.gate.failed_rule_count} / ${snapshot.gate.insufficient_rule_count}`} />
                <Line label="Critical failures" value={String(snapshot.gate.critical_failure_count)} />
                <Line label="Benchmark runs" value={String(snapshot.gate.benchmark_run_ids.length)} />
                <Line label="Results / metrics" value={`${snapshot.gate.result_count} / ${snapshot.gate.metric_count}`} />
              </dl>
            </section>
            <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
              <h2 className="text-base font-semibold text-ink">Calibration and regression</h2>
              <dl className="mt-4 grid gap-3 text-sm text-neutral-700">
                <Line label="Applied / human-reviewed" value={`${snapshot.judge_calibration.applied_label_count} / ${snapshot.judge_calibration.human_reviewed_count}`} />
                <Line label="Critical review coverage" value={percent(snapshot.judge_calibration.critical_review_coverage_rate)} />
                <Line label="Rows needing review" value={String(snapshot.judge_calibration.needs_review_count)} />
                <Line label="Prompt risk flags" value={snapshot.prompt_regression.risk_flags.join(", ") || "none"} />
              </dl>
            </section>
          </div>

          <DisclosurePanel title="Latest lineage events">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-sm">
                <thead className="text-xs uppercase text-neutral-500"><tr><th className="pb-3">Event</th><th className="pb-3">Status</th><th className="pb-3">Summary</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {snapshot.lineage.latest_events.map((event) => <tr key={`${event.event_type}-${event.event_time}`}><td className="py-3 font-medium text-ink">{event.event_type}</td><td className="py-3"><Badge tone={statusTone(event.status)}>{statusLabel(event.status)}</Badge></td><td className="py-3 text-neutral-700">{event.summary}</td></tr>)}
                  {!snapshot.lineage.latest_events.length ? <tr><td colSpan={3} className="py-4 text-neutral-500">No lineage events are available.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </DisclosurePanel>
        </>
      ) : (
        <section className="rounded-lg border border-line bg-panel p-5 text-sm text-neutral-600 shadow-soft">No gate evaluation is available for a release readiness snapshot.</section>
      )}
    </>
  );
}

function ReasonList({ title, rows }: { title: string; rows: string[] }) {
  return <div><div className="text-xs font-semibold uppercase text-neutral-500">{title}</div><div className="mt-3 grid gap-2 text-sm leading-6 text-neutral-700">{rows.length ? rows.map((row) => <div key={row}>{row}</div>) : <div>None</div>}</div></div>;
}

function Line({ label, value }: { label: string; value: string }) {
  return <div className="flex items-start justify-between gap-4 border-b border-line pb-2"><dt className="text-neutral-500">{label}</dt><dd className="text-right font-medium text-ink">{value}</dd></div>;
}
