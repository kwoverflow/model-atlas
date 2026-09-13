import { ArrowRight, CircleAlert } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import type { ControlPlaneOverview } from "@/types/api";

export function NextActions({ actions }: { actions: ControlPlaneOverview["next_actions"] }) {
  return (
    <section className="rounded-lg border border-line bg-panel shadow-soft">
      <div className="flex items-center gap-2 border-b border-line px-5 py-4">
        <CircleAlert size={18} className="text-amber" aria-hidden="true" />
        <h2 className="text-base font-semibold text-ink">Next actions</h2>
      </div>
      <div className="divide-y divide-line">
        {actions.map((action) => (
          <Link
            key={`${action.kind}-${action.href}`}
            href={action.href}
            className="flex items-start justify-between gap-4 px-5 py-4 hover:bg-neutral-50"
          >
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-ink">{action.title}</span>
                <Badge tone={action.priority === "high" ? "rose" : action.priority === "medium" ? "amber" : "neutral"}>
                  {action.priority}
                </Badge>
              </span>
              <span className="mt-1 block text-sm leading-6 text-neutral-600">
                {action.description}
              </span>
            </span>
            <ArrowRight size={18} className="mt-1 shrink-0 text-neutral-400" aria-hidden="true" />
          </Link>
        ))}
        {!actions.length ? (
          <div className="px-5 py-6 text-sm text-neutral-600">No immediate release actions.</div>
        ) : null}
      </div>
    </section>
  );
}
