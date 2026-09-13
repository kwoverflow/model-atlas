import { CheckCircle2, CircleAlert, ExternalLink } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type { ReferenceWorkloadOverview } from "@/types/api";

export function GateEvidenceSummary({ data }: { data: ReferenceWorkloadOverview }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="overflow-x-auto border-y border-line bg-panel">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Configuration</th>
              <th className="px-4 py-3">Gate</th>
              <th className="px-4 py-3">Evidence trust</th>
              <th className="px-4 py-3">Release readiness</th>
              <th className="px-4 py-3">Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.gate_outcomes.map((outcome) => (
              <tr key={outcome.entry_name} className="align-top">
                <td className="px-4 py-3 font-semibold text-ink">{outcome.entry_name}</td>
                <td className="px-4 py-3"><Badge tone={statusTone(outcome.verdict)}>{statusLabel(outcome.verdict)}</Badge></td>
                <td className="px-4 py-3">{statusLabel(outcome.evidence_trust_status)}</td>
                <td className="px-4 py-3">{statusLabel(outcome.release_readiness)}</td>
                <td className="max-w-80 px-4 py-3 text-neutral-600">
                  <div>{outcome.decision_summary}</div>
                  {outcome.gate_detail_href ? (
                    <Link href={outcome.gate_detail_href} className="mt-2 inline-flex items-center gap-1 font-medium text-teal hover:underline">
                      Open Gate <ExternalLink size={13} aria-hidden="true" />
                    </Link>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid content-start gap-5">
        <div>
          <h3 className="text-sm font-semibold text-ink">Evidence interpretation</h3>
          <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <Metric label="Local authored" value={data.evidence_trust.local_authored_count} />
            <Metric label="Production captured" value={data.evidence_trust.production_captured_count} />
            <Metric label="Heuristic only" value={data.evidence_trust.heuristic_only_count} />
            <Metric label="Critical reviewed" value={data.evidence_trust.critical_reviewed_count} />
          </div>
          {data.evidence_trust.reasons.length ? (
            <ul className="mt-4 grid gap-2 text-sm leading-5 text-neutral-600">
              {data.evidence_trust.reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          ) : null}
        </div>

        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold text-ink">Portfolio completion</h3>
          <ul className="mt-3 grid gap-2">
            {data.portfolio_completion.checks.map((check) => (
              <li key={check.key} className="flex items-start gap-3 text-sm">
                {check.passed ? (
                  <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-teal" aria-hidden="true" />
                ) : (
                  <CircleAlert size={17} className="mt-0.5 shrink-0 text-amber" aria-hidden="true" />
                )}
                <div className="min-w-0 flex-1">
                  {check.href ? <Link href={check.href} className="font-medium text-ink hover:underline">{check.label}</Link> : <span className="font-medium text-ink">{check.label}</span>}
                  <div className="mt-0.5 text-xs text-neutral-500">Observed {check.observed} · Required {check.required}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-b border-line pb-2">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-ink">{value}</div>
    </div>
  );
}
