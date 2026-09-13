import Link from "next/link";

import { Badge } from "@/components/Badge";
import { EvidenceTrustPanel } from "@/components/EvidenceTrustPanel";
import { ReleaseDecisionOperations } from "@/components/ReleaseDecisionOperations";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { api } from "@/lib/api";
import {
  formatDate,
  releaseDecisionLabels,
  releaseDecisionTone,
  releaseReadinessTone,
  shortId
} from "@/lib/releaseDecisionPresentation";
import type { ReleaseReadinessSnapshot, SnapshotDiffStatus } from "@/types/api";
import { statusLabel, statusTone } from "@/lib/statusPresentation";

export const dynamic = "force-dynamic";

type PageParams = Promise<{
  id: string;
}>;

function metric(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : value.toFixed(3);
}

function markdownHref(decisionId: string): string {
  return `${API_BASE_URL}/release-decisions/${decisionId}/report.md`;
}

function snapshotJsonHref(decisionId: string): string {
  return `${API_BASE_URL}/release-decisions/${decisionId}/snapshot.json`;
}

function diffTone(status: SnapshotDiffStatus): "teal" | "amber" | "rose" | "violet" {
  if (status === "added") return "teal";
  if (status === "removed") return "rose";
  return "amber";
}

function snapshotValue(value: unknown): string {
  if (value === undefined) return "missing";
  const text =
    typeof value === "string"
      ? value
      : JSON.stringify(value, null, 0) ?? String(value);
  return text.length > 180 ? `${text.slice(0, 177)}...` : text;
}

function rowList(title: string, rows: string[]) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-neutral-500">{title}</div>
      <div className="mt-2 grid gap-2 text-sm text-neutral-700">
        {rows.length ? rows.map((row) => <div key={row}>{row}</div>) : <div>None</div>}
      </div>
    </div>
  );
}

function sourceDistribution(snapshot: ReleaseReadinessSnapshot): string {
  const entries = Object.entries(snapshot.gate.source_distribution);
  if (!entries.length) return "none";
  return entries.map(([key, value]) => `${key} ${value}`).join(", ");
}

export default async function ReleaseDecisionDetailPage({
  params
}: {
  params: PageParams;
}) {
  const { id } = await params;
  const [decision, actions, snapshotDiff, configs, suites, policies] = await Promise.all([
    api.releaseDecision(id),
    api.releaseDecisionActions(id),
    api.releaseDecisionSnapshotDiff(id),
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies()
  ]);

  if (!decision) {
    return (
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Release Decision</h1>
            <p className="mt-2 text-sm text-neutral-600">Decision record was not found.</p>
          </div>
          <Link
            className="rounded-md border border-line px-3 py-2 text-sm font-medium"
            href="/release-decisions"
          >
            Decisions
          </Link>
        </div>
      </section>
    );
  }

  const snapshot = decision.snapshot_json;
  const config = configs.find((item) => item.id === decision.deployment_configuration_id);
  const suite = suites.find((item) => item.id === decision.evaluation_suite_id);
  const policy = policies.find((item) => item.id === decision.acceptance_policy_id);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Release Decision</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge tone={releaseDecisionTone(decision)}>
                {releaseDecisionLabels[decision.decision]}
              </Badge>
              <Badge tone={releaseReadinessTone(decision.release_readiness_status)}>
                {decision.release_readiness_status}
              </Badge>
              <Badge tone={decision.identity_verified ? "teal" : "amber"}>
                {decision.identity_verified ? "Verified signer" : "Self-attested signer"}
              </Badge>
              <Badge tone={statusTone(decision.operational_status)}>
                {statusLabel(decision.operational_status)}
              </Badge>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              className="rounded-md border border-line px-3 py-2 text-sm font-medium"
              href="/release-decisions"
            >
              Decisions
            </Link>
            {decision.operational_status === "needs_review" ? (
              <Link
                className="rounded-md bg-ink px-3 py-2 text-sm font-medium text-white"
                href={`/release-readiness?replaces_release_decision_id=${decision.id}`}
              >
                Create Replacement
              </Link>
            ) : null}
            <a
              className="rounded-md border border-line px-3 py-2 text-sm font-medium"
              href={markdownHref(decision.id)}
            >
              Markdown
            </a>
            <a
              className="rounded-md border border-line px-3 py-2 text-sm font-medium"
              href={snapshotJsonHref(decision.id)}
            >
              Snapshot JSON
            </a>
          </div>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-neutral-700 md:grid-cols-3">
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Decided</div>
            <div className="mt-2">{formatDate(decision.decided_at)}</div>
            <div className="text-xs text-neutral-500">{decision.decided_by}</div>
            <div className="text-xs text-neutral-500">
              {decision.signer_identity_json.role ?? "role n/a"}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Scope</div>
            <div className="mt-2">{config?.name ?? shortId(decision.deployment_configuration_id)}</div>
            <div className="text-xs text-neutral-500">
              {suite?.name ?? shortId(decision.evaluation_suite_id)} -{" "}
              {policy?.name ?? shortId(decision.acceptance_policy_id)}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Gate</div>
            <Link
              className="mt-2 block font-medium text-teal"
              href={`/deployment-gates/${decision.gate_evaluation_id}`}
            >
              {shortId(decision.gate_evaluation_id)}
            </Link>
            <div className="text-xs text-neutral-500">{snapshot.gate.verdict}</div>
          </div>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        <SummaryCard
          label="Readiness"
          value={statusLabel(snapshot.status)}
          detail={statusLabel(snapshot.gate.verdict)}
          tone={releaseReadinessTone(snapshot.status)}
        />
        <SummaryCard
          label="Baseline"
          value={statusLabel(snapshot.baseline.baseline_status)}
          detail={shortId(snapshot.baseline.active_baseline_id)}
          tone={snapshot.baseline.gate_is_active_baseline ? "teal" : "violet"}
        />
        <SummaryCard
          label="Judge review"
          value={snapshot.judge_calibration.needs_review_count}
          detail={`${snapshot.judge_calibration.reviewed_count} reviewed`}
          tone={snapshot.judge_calibration.needs_review_count ? "amber" : "teal"}
        />
        <SummaryCard
          label="Prompt risks"
          value={snapshot.prompt_regression.risk_row_count}
          detail={`${snapshot.prompt_regression.prompt_version_count} prompt versions`}
          tone={snapshot.prompt_regression.risk_row_count ? "amber" : "teal"}
        />
        <SummaryCard
          label="Evidence trust"
          value={statusLabel(snapshot.evidence_trust.trust_status)}
          detail={`${snapshot.evidence_trust.production_captured_count} production results`}
          tone={statusTone(snapshot.evidence_trust.trust_status)}
        />
        <SummaryCard
          label="Production"
          value={statusLabel(snapshot.production_readiness)}
          detail={snapshot.evidence_trust.limitations[0] ?? "No evidence limitation"}
          tone={statusTone(snapshot.production_readiness)}
        />
        <SummaryCard
          label="Policy"
          value={decision.approval_policy_json.allowed ? "Allowed" : "Denied"}
          detail={decision.approval_policy_json.policy_version}
          tone={decision.approval_policy_json.allowed ? "teal" : "rose"}
        />
      </div>

      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <h2 className="text-lg font-semibold text-ink">Decision Reason</h2>
        <div className="mt-3 text-sm leading-6 text-neutral-700">{decision.decision_reason}</div>
        {decision.notes ? (
          <div className="mt-4 rounded-md border border-line bg-neutral-50 p-3 text-sm text-neutral-700">
            {decision.notes}
          </div>
        ) : null}
      </section>

      <ReleaseDecisionOperations decision={decision} actions={actions} />

      <EvidenceTrustPanel evidence={snapshot.evidence_trust} />

      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <h2 className="text-lg font-semibold text-ink">Signer Identity</h2>
        <div className="mt-4 grid gap-3 text-sm text-neutral-700 md:grid-cols-3">
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Subject</div>
            <div className="mt-2">{decision.signer_identity_json.subject_id ?? "n/a"}</div>
            <div className="text-xs text-neutral-500">
              {decision.signer_identity_json.auth_source ?? "unknown source"}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Provider</div>
            <div className="mt-2">
              {decision.signer_identity_json.identity_provider ?? "n/a"}
            </div>
            <div className="text-xs text-neutral-500">
              {decision.identity_verified ? "verified identity" : "self-attested identity"}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">Ticket</div>
            <div className="mt-2">
              {decision.signer_identity_json.ticket_reference ?? "none"}
            </div>
            <div className="text-xs text-neutral-500">
              {decision.signature_hash ? shortId(decision.signature_hash) : "signature pending"}
            </div>
          </div>
        </div>
        <div className="mt-4 rounded-md border border-line bg-neutral-50 p-3 text-sm text-neutral-700">
          {decision.signature_statement ?? "No signature statement was stored."}
        </div>
        <div className="mt-4 rounded-md border border-line bg-neutral-50 p-3 text-sm text-neutral-700">
          <div className="text-xs font-semibold uppercase text-neutral-500">
            Approval Policy
          </div>
          <div className="mt-2">
            {decision.approval_policy_json.policy_version} -{" "}
            {decision.approval_policy_json.allowed ? "allowed" : "denied"}
          </div>
          <div className="mt-1 text-xs text-neutral-500">
            roles: {decision.approval_policy_json.allowed_roles.join(", ")}
          </div>
          {decision.approval_policy_json.reasons.length ? (
            <div className="mt-2 text-xs text-rose">
              {decision.approval_policy_json.reasons.join(" ")}
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <h2 className="text-lg font-semibold text-ink">Frozen Snapshot</h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-neutral-600">
          {snapshot.release_summary}
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {rowList("Readiness reasons", snapshot.readiness_reasons)}
          {rowList("Review reasons", snapshot.review_reasons)}
          {rowList("Next actions", snapshot.next_actions)}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">Snapshot Diff</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-neutral-600">
              Frozen release evidence compared with the current readiness snapshot for this gate.
            </p>
          </div>
          <Badge tone={snapshotDiff?.changed ? "amber" : "teal"}>
            {snapshotDiff?.changed ? `${snapshotDiff.diff_count} change(s)` : "No drift"}
          </Badge>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-neutral-700 md:grid-cols-3">
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">
              Frozen hash
            </div>
            <div className="mt-2 font-mono text-xs text-neutral-600">
              {shortId(snapshotDiff?.frozen_snapshot_hash ?? decision.snapshot_hash)}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">
              Current hash
            </div>
            <div className="mt-2 font-mono text-xs text-neutral-600">
              {shortId(snapshotDiff?.current_snapshot_hash)}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">
              Ignored paths
            </div>
            <div className="mt-2 text-xs text-neutral-600">
              {snapshotDiff?.ignored_paths.join(", ") || "none"}
            </div>
          </div>
        </div>
        {snapshotDiff?.diffs.length ? (
          <div className="mt-4 overflow-x-auto rounded-md border border-line">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Path</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Frozen</th>
                  <th className="px-3 py-2">Current</th>
                </tr>
              </thead>
              <tbody>
                {snapshotDiff.diffs.map((diff) => (
                  <tr key={`${diff.path}-${diff.status}`} className="border-t border-line">
                    <td className="px-3 py-2 font-mono text-xs text-neutral-600">
                      {diff.path}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={diffTone(diff.status)}>{diff.status}</Badge>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-neutral-600">
                      {diff.frozen_present ? snapshotValue(diff.frozen_value) : "missing"}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-neutral-600">
                      {diff.current_present ? snapshotValue(diff.current_value) : "missing"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4 rounded-md border border-line bg-neutral-50 p-3 text-sm text-neutral-700">
            No material snapshot drift was detected.
          </div>
        )}
        {snapshotDiff?.truncated ? (
          <div className="mt-3 text-xs text-neutral-500">
            Diff output is truncated to the first 200 items.
          </div>
        ) : null}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <h2 className="text-lg font-semibold text-ink">Gate Evidence</h2>
          <div className="mt-4 grid gap-3 text-sm text-neutral-700">
            <div>Passed rules: {snapshot.gate.passed_rule_count}</div>
            <div>Failed rules: {snapshot.gate.failed_rule_count}</div>
            <div>Insufficient rules: {snapshot.gate.insufficient_rule_count}</div>
            <div>Critical failures: {snapshot.gate.critical_failure_count}</div>
            <div>Benchmark runs: {snapshot.gate.benchmark_run_ids.length}</div>
            <div>
              Results / metrics: {snapshot.gate.result_count} / {snapshot.gate.metric_count}
            </div>
            <div>Sources: {sourceDistribution(snapshot)}</div>
          </div>
        </section>

        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <h2 className="text-lg font-semibold text-ink">Calibration And Regression</h2>
          <div className="mt-4 grid gap-3 text-sm text-neutral-700">
            <div>Average quality: {metric(snapshot.judge_calibration.average_quality_score)}</div>
            <div>Candidate labels: {snapshot.judge_calibration.candidate_label_count}</div>
            <div>Heuristic scored: {snapshot.judge_calibration.heuristic_scored_count}</div>
            <div>Unlabeled: {snapshot.judge_calibration.unlabeled_count}</div>
            <div>Prompt risk flags: {snapshot.prompt_regression.risk_flags.join(", ") || "none"}</div>
            <div>Baseline prompt: {shortId(snapshot.prompt_regression.baseline_prompt_version_id)}</div>
          </div>
        </section>
      </div>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Hashes
        </div>
        <table className="w-full text-left text-sm">
          <tbody>
            <tr className="border-t border-line">
              <th className="w-48 px-4 py-3 text-xs uppercase text-neutral-500">
                Decision hash
              </th>
              <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                {decision.decision_hash}
              </td>
            </tr>
            <tr className="border-t border-line">
              <th className="w-48 px-4 py-3 text-xs uppercase text-neutral-500">
                Snapshot hash
              </th>
              <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                {decision.snapshot_hash}
              </td>
            </tr>
            <tr className="border-t border-line">
              <th className="w-48 px-4 py-3 text-xs uppercase text-neutral-500">
                Signature hash
              </th>
              <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                {decision.signature_hash ?? "none"}
              </td>
            </tr>
            <tr className="border-t border-line">
              <th className="w-48 px-4 py-3 text-xs uppercase text-neutral-500">
                Gate hash
              </th>
              <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                {snapshot.gate.decision_hash}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </>
  );
}
