import {
  ArrowRight,
  BookOpenCheck,
  Database,
  Factory,
  FileCheck2,
  Gauge,
  ShieldCheck,
  TestTube2
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { NextActions } from "@/components/NextActions";
import { StatusSummaryGrid } from "@/components/StatusSummaryGrid";
import { SummaryCard } from "@/components/SummaryCard";
import { WorkflowStepper } from "@/components/WorkflowStepper";
import { api } from "@/lib/api";
import { statusLabel, statusTone } from "@/lib/statusPresentation";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const [control, reference] = await Promise.all([
    api.controlPlaneOverview(),
    api.referenceWorkloadOverview()
  ]);
  const inventory = control.inventory;
  const latest = control.latest_gate;
  const reviewedOutputs =
    reference.review_coverage.human_reviewed_count +
    reference.review_coverage.applied_judge_label_count;
  const bestConfiguration = reference.metric_comparison.reduce<(typeof reference.metric_comparison)[number] | null>(
    (best, candidate) => {
      const candidateScore = candidate.metrics.mean_quality_score ?? -1;
      const bestScore = best?.metrics.mean_quality_score ?? -1;
      return candidateScore > bestScore ? candidate : best;
    },
    null
  );

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Model Atlas</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Evidence-driven release control for local AI workloads. Candidate ranking selects what
              to test; a Deployment Gate decides whether a concrete configuration satisfies a
              versioned acceptance policy.
            </p>
          </div>
          <Badge tone={control.mode === "production_evidence" ? "teal" : control.mode === "empty" ? "neutral" : "amber"}>
            {control.mode === "production_evidence"
              ? "Production evidence present"
              : control.mode === "empty"
                ? "Empty workspace"
                : "Demo / local evidence mode"}
          </Badge>
        </div>
      </section>

      {control.mode === "demo" ? (
        <section className="flex items-start gap-3 border-l-4 border-amber bg-amber/5 px-4 py-3 text-sm leading-6 text-neutral-700">
          <TestTube2 size={18} className="mt-1 shrink-0 text-amber" aria-hidden="true" />
          <div>
            <div className="font-semibold text-ink">Demo / local evidence mode</div>
            <div>Some evidence is synthetic or locally authored. This does not imply production readiness.</div>
          </div>
        </section>
      ) : null}

      <section className="border-y border-line bg-panel px-4 py-5 sm:px-5" aria-labelledby="reference-evaluation-title">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-sm font-medium text-teal">
              <BookOpenCheck size={17} aria-hidden="true" />
              Portfolio evaluation
            </div>
            <h2 id="reference-evaluation-title" className="mt-2 text-lg font-semibold text-ink">
              Korean Operator Assistant Reference Workload
            </h2>
            <p className="mt-2 text-sm leading-6 text-neutral-600">
              {reference.actual_runtime_result_count} actual local-runtime results across {reference.metric_comparison.length} comparable configurations, with {reviewedOutputs} reviewed model outputs. Production readiness is <strong className="font-semibold text-rose">not established</strong> until verified production-captured evidence is linked.
            </p>
          </div>
          <Link href="/reference-workload" className="inline-flex min-h-10 items-center gap-2 rounded-md bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-neutral-700">
            Open evaluation detail <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        <div className="mt-5 grid gap-4 border-t border-line pt-4 text-sm sm:grid-cols-3">
          <div><div className="text-xs uppercase text-neutral-500">Evaluation</div><div className="mt-1 font-semibold text-ink">{statusLabel(reference.evaluation_status)}</div></div>
          <div><div className="text-xs uppercase text-neutral-500">Best observed configuration</div><div className="mt-1 font-semibold text-ink">{bestConfiguration?.entry_name ?? "Not available"}</div></div>
          <div><div className="text-xs uppercase text-neutral-500">Mean quality</div><div className="mt-1 font-semibold tabular-nums text-ink">{bestConfiguration?.metrics.mean_quality_score === null || bestConfiguration?.metrics.mean_quality_score === undefined ? "Not available" : bestConfiguration.metrics.mean_quality_score.toFixed(3)}</div></div>
        </div>
      </section>

      {control.workflow_steps.length ? (
        <WorkflowStepper steps={control.workflow_steps} />
      ) : null}

      <StatusSummaryGrid
        items={[
          {
            label: "Latest Gate Verdict",
            value: latest?.verdict ?? "Not evaluated",
            detail: latest?.decision_summary ?? "Create a gate after benchmark evidence is available.",
            icon: ShieldCheck
          },
          {
            label: "Evidence Trust",
            value: latest?.evidence_trust_status ?? "Unknown",
            detail: `${control.local_authored_result_count} local, ${control.production_evidence_result_count} production-captured results`,
            icon: Database
          },
          {
            label: "Production Readiness",
            value: latest?.production_readiness ?? "Unknown",
            detail: "A separate interpretation from gate policy pass/fail.",
            icon: Factory
          },
          {
            label: "Release State",
            value: control.needs_review_count ? "Needs review" : control.release_ready_configuration_count ? "Ready" : "Not started",
            detail: `${control.release_ready_configuration_count} configuration(s) ready or ready to promote`,
            icon: FileCheck2
          }
        ]}
      />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Operational counts">
        <SummaryCard
          label="Items requiring review"
          value={control.needs_review_count}
          detail="latest configuration states"
          tone={control.needs_review_count ? "amber" : "teal"}
        />
        <SummaryCard
          label="Critical failure outcomes"
          value={control.failed_critical_case_count}
          detail="latest Gate for every configuration"
          tone={control.failed_critical_case_count ? "rose" : "teal"}
        />
        <SummaryCard
          label="Active baselines"
          value={control.active_baseline_count}
          detail="current release comparison scopes"
          tone="violet"
        />
        <SummaryCard
          label="Production evidence"
          value={control.production_evidence_result_count}
          detail="captured result rows"
          tone={control.production_evidence_result_count ? "teal" : "amber"}
        />
      </section>

      <NextActions actions={control.next_actions} />

      <section className="border-t border-line pt-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-ink">Inventory and recent execution</h2>
            <p className="mt-1 text-sm text-neutral-600">Supporting catalog and benchmark activity.</p>
          </div>
          {latest ? (
            <Link href={`/deployment-gates/${latest.id}`} className="text-sm font-medium text-teal hover:underline">
              Open latest gate
            </Link>
          ) : null}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <SummaryCard label="Models" value={inventory.model_count} tone="teal" />
          <SummaryCard label="Artifacts" value={inventory.model_artifact_count} tone="violet" />
          <SummaryCard label="Tasks" value={inventory.benchmark_task_count} tone="amber" />
          <SummaryCard label="Runs" value={inventory.benchmark_run_count} tone="teal" />
          <SummaryCard label="Results" value={inventory.benchmark_result_count} tone="rose" />
          <SummaryCard label="Synthetic rows" value={inventory.synthetic_record_count} tone="amber" />
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex items-center gap-2 border-b border-line px-5 py-4">
          <Gauge size={18} className="text-neutral-500" aria-hidden="true" />
          <h2 className="text-base font-semibold text-ink">Recent benchmark runs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Run</th>
                <th className="px-4 py-3">Runtime</th>
                <th className="px-4 py-3">Evidence source</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {control.recent_runs.map((run) => (
                <tr key={run.id}>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-600">{run.id.slice(0, 8)}</td>
                  <td className="px-4 py-3 font-medium text-ink">{run.runtime_name}</td>
                  <td className="px-4 py-3 text-neutral-700">{statusLabel(run.data_source)}</td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
                  </td>
                  <td className="px-4 py-3 text-neutral-600">{new Date(run.started_at).toLocaleString()}</td>
                </tr>
              ))}
              {!control.recent_runs.length ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-neutral-500">No benchmark runs available.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
