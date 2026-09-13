import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/Badge";
import { statusLabel, statusTone } from "@/lib/statusPresentation";

export type StatusSummaryItem = {
  label: string;
  value: string;
  detail?: string;
  icon: LucideIcon;
};

export function StatusSummaryGrid({ items }: { items: StatusSummaryItem[] }) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Status summary">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <article key={item.label} className="rounded-lg border border-line bg-panel p-4 shadow-soft">
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase text-neutral-500">{item.label}</span>
              <Icon size={17} className="text-neutral-500" aria-hidden="true" />
            </div>
            <div className="mt-3">
              <Badge tone={statusTone(item.value)}>{statusLabel(item.value)}</Badge>
            </div>
            {item.detail ? (
              <p className="mt-3 text-xs leading-5 text-neutral-600">{item.detail}</p>
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
