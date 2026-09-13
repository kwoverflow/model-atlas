import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/Badge";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type { EvidenceTrustSummary } from "@/types/api";

export function EvidenceTrustPanel({
  evidence,
  legacy = false
}: {
  evidence: EvidenceTrustSummary | null | undefined;
  legacy?: boolean;
}) {
  if (!evidence) {
    return (
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <h2 className="text-base font-semibold text-ink">Evidence trust</h2>
        <div className="mt-4 flex items-start gap-3 text-sm text-neutral-600">
          <AlertTriangle size={18} className="shrink-0 text-amber" aria-hidden="true" />
          <p>
            {legacy
              ? "This legacy snapshot predates evidence trust metadata. Re-evaluate the gate to generate a v2 snapshot."
              : "Evidence trust is not available."}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-ink">Evidence trust</h2>
          <p className="mt-1 text-sm text-neutral-600">Source provenance and score provenance are evaluated separately.</p>
        </div>
        <Badge tone={statusTone(evidence.trust_status)}>{statusLabel(evidence.trust_status)}</Badge>
      </div>
      <div className="grid gap-6 px-5 py-5 lg:grid-cols-[0.8fr_0.8fr_1.4fr]">
        <Distribution title="Source trust" values={evidence.source_distribution} />
        <Distribution title="Score trust" values={evidence.score_distribution} />
        <div>
          <div className="grid grid-cols-2 gap-4">
            <Metric label="Applied labels" value={percent(evidence.applied_judge_label_rate)} />
            <Metric label="Critical review" value={percent(evidence.critical_review_coverage_rate)} />
            <Metric label="Heuristic only" value={String(evidence.heuristic_only_count)} />
            <Metric label="Production captured" value={String(evidence.production_captured_count)} />
            <Metric
              label="Unverified production"
              value={String(evidence.unverified_production_captured_count)}
            />
            <Metric label="Human reviewed" value={String(evidence.human_reviewed_count)} />
          </div>
          <div className="mt-5 grid gap-2 text-sm leading-6 text-neutral-700">
            {evidence.reasons.map((reason) => (
              <div key={reason} className="flex gap-2">
                <CheckCircle2 size={16} className="mt-1 shrink-0 text-teal" aria-hidden="true" />
                <span>{reason}</span>
              </div>
            ))}
            {evidence.limitations.map((limitation) => (
              <div key={limitation} className="flex gap-2">
                <AlertTriangle size={16} className="mt-1 shrink-0 text-amber" aria-hidden="true" />
                <span>{limitation}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Distribution({ title, values }: { title: string; values: Record<string, number> }) {
  const entries = Object.entries(values);
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-neutral-500">{title}</div>
      <dl className="mt-3 divide-y divide-line text-sm">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-3 py-2">
            <dt className="text-neutral-600">{statusLabel(key)}</dt>
            <dd className="font-semibold text-ink">{value}</dd>
          </div>
        ))}
        {!entries.length ? <div className="py-2 text-neutral-500">No classified results</div> : null}
      </dl>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-neutral-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}
