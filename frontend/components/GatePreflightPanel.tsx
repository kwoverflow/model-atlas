import { AlertTriangle, Ban, CheckCircle2 } from "lucide-react";

import { Badge } from "@/components/Badge";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type { GatePreflightResponse } from "@/types/api";

export function GatePreflightPanel({ preflight }: { preflight: GatePreflightResponse }) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-ink">Preflight summary</h2>
          <p className="mt-1 text-sm text-neutral-600">Selected evidence, policy, and baseline before evaluation.</p>
        </div>
        <Badge tone={preflight.can_evaluate ? statusTone(preflight.evidence.trust_status) : "rose"}>
          {preflight.can_evaluate ? statusLabel(preflight.evidence.trust_status) : "Blocked preflight"}
        </Badge>
      </div>
      <div className="grid gap-6 px-5 py-5 lg:grid-cols-3">
        <div>
          <div className="text-xs font-semibold uppercase text-neutral-500">Selection</div>
          <dl className="mt-3 grid gap-2 text-sm">
            <Row label="Configuration" value={preflight.configuration.name} />
            <Row label="Artifact" value={preflight.configuration.artifact_name} />
            <Row label="Runtime" value={preflight.configuration.runtime_name} />
            <Row label="Hardware" value={preflight.configuration.hardware_name} />
            <Row label="Suite" value={`${preflight.suite.name} ${preflight.suite.version_label}`} />
            <Row label="Policy" value={`${preflight.policy.name} ${preflight.policy.version_label}`} />
          </dl>
        </div>
        <div>
          <div className="text-xs font-semibold uppercase text-neutral-500">Evidence coverage</div>
          <dl className="mt-3 grid gap-2 text-sm">
            <Row label="Completed runs" value={String(preflight.evidence.completed_run_count)} />
            <Row label="Results / metrics" value={`${preflight.evidence.result_count} / ${preflight.evidence.metric_count}`} />
            <Row label="Active / critical cases" value={`${preflight.suite.active_case_count} / ${preflight.suite.critical_case_count}`} />
            <Row label="Applied labels" value={percent(preflight.evidence.applied_judge_label_rate)} />
            <Row label="Critical review" value={percent(preflight.evidence.critical_review_coverage_rate)} />
            <Row label="Baseline" value={preflight.baseline ? `${preflight.baseline.verdict} (${preflight.baseline.source})` : "None"} />
          </dl>
        </div>
        <div>
          <div className="text-xs font-semibold uppercase text-neutral-500">Constraints</div>
          <div className="mt-3 grid gap-2 text-sm leading-6 text-neutral-700">
            {preflight.blocking_preconditions.map((item) => (
              <Message key={item} icon={Ban} tone="text-rose" text={item} />
            ))}
            {preflight.warnings.map((item) => (
              <Message key={item} icon={AlertTriangle} tone="text-amber" text={item} />
            ))}
            {!preflight.blocking_preconditions.length && !preflight.warnings.length ? (
              <Message icon={CheckCircle2} tone="text-teal" text="Preflight checks are clear." />
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line pb-2">
      <dt className="text-neutral-500">{label}</dt>
      <dd className="max-w-[60%] text-right font-medium text-ink">{value}</dd>
    </div>
  );
}

function Message({ icon: Icon, tone, text }: { icon: typeof Ban; tone: string; text: string }) {
  return (
    <div className="flex gap-2">
      <Icon size={16} className={`mt-1 shrink-0 ${tone}`} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}
