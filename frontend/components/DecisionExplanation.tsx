import { AlertTriangle, ArrowRight, Ban } from "lucide-react";
import Link from "next/link";

import type { GateEvaluation } from "@/types/api";

type Explanation = NonNullable<GateEvaluation["scorecard_json"]["decision_explanation"]>;

export function DecisionExplanation({ explanation }: { explanation: Explanation | undefined }) {
  if (!explanation) {
    return (
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <h2 className="text-base font-semibold text-ink">Why this decision was made</h2>
        <p className="mt-3 text-sm text-neutral-600">Structured explanation is unavailable for this legacy gate snapshot.</p>
      </section>
    );
  }
  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="border-b border-line px-5 py-4">
        <h2 className="text-base font-semibold text-ink">Why this decision was made</h2>
        <p className="mt-2 text-sm leading-6 text-neutral-700">{explanation.summary}</p>
      </div>
      <div className="grid gap-6 px-5 py-5 lg:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">Blocking issues</h3>
          <div className="mt-3 grid gap-3">
            {explanation.blockers.map((blocker) => (
              <div key={`${blocker.code}-${blocker.title}`} className="flex gap-3 border-l-2 border-rose pl-3">
                <Ban size={17} className="mt-0.5 shrink-0 text-rose" aria-hidden="true" />
                <div>
                  <div className="text-sm font-medium text-ink">{blocker.title}</div>
                  <div className="mt-1 text-sm leading-6 text-neutral-600">{blocker.detail}</div>
                </div>
              </div>
            ))}
            {!explanation.blockers.length ? <div className="text-sm text-neutral-600">No blocking issues.</div> : null}
          </div>
          {explanation.warnings.length ? (
            <div className="mt-5 grid gap-2">
              {explanation.warnings.slice(0, 4).map((warning) => (
                <div key={`${warning.code}-${warning.detail}`} className="flex gap-2 text-sm text-neutral-600">
                  <AlertTriangle size={16} className="mt-1 shrink-0 text-amber" aria-hidden="true" />
                  <span>{warning.detail}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div>
          <h3 className="text-sm font-semibold text-ink">Recommended next actions</h3>
          <div className="mt-3 divide-y divide-line border-y border-line">
            {explanation.next_actions.map((action) => (
              <Link key={action.code} href={action.href} className="flex items-start justify-between gap-3 py-3 hover:text-teal">
                <span>
                  <span className="block text-sm font-medium">{action.title}</span>
                  <span className="mt-1 block text-xs leading-5 text-neutral-500">{action.description}</span>
                </span>
                <ArrowRight size={17} className="mt-1 shrink-0" aria-hidden="true" />
              </Link>
            ))}
            {!explanation.next_actions.length ? <div className="py-3 text-sm text-neutral-600">No actions required.</div> : null}
          </div>
        </div>
      </div>
    </section>
  );
}
