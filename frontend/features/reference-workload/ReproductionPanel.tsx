import { ArrowRight, TerminalSquare } from "lucide-react";
import Link from "next/link";

import type { ReferenceWorkloadOverview } from "@/types/api";

export function ReproductionPanel({ data }: { data: ReferenceWorkloadOverview }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <TerminalSquare size={18} className="text-neutral-500" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-ink">Reproduction commands</h3>
        </div>
        <pre className="mt-3 max-w-full overflow-x-auto rounded-lg bg-neutral-950 p-4 text-xs leading-6 text-neutral-100">
          <code>{data.reproduction_commands.join("\n") || "No reproduction commands available."}</code>
        </pre>
        <dl className="mt-4 grid gap-3 text-xs text-neutral-600 sm:grid-cols-2">
          <Hash label="Manifest" value={data.manifest.manifest_hash} />
          <Hash label="Corpus" value={data.corpus.corpus_hash} />
          <Hash label="Suite" value={data.workload.evaluation_suite_hash ?? "Not bootstrapped"} />
          <Hash label="Comparison" value={data.comparison_hash} />
        </dl>
      </div>

      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-ink">Next actions</h3>
        <div className="mt-3 divide-y divide-line border-y border-line">
          {data.portfolio_completion.next_actions.map((action) => (
            <Link key={`${action.title}-${action.href}`} href={action.href} className="flex items-start justify-between gap-4 py-4 hover:text-teal">
              <div>
                <div className="text-xs font-semibold uppercase text-neutral-500">{action.priority}</div>
                <div className="mt-1 font-semibold text-ink">{action.title}</div>
                <div className="mt-1 text-sm leading-5 text-neutral-600">{action.description}</div>
              </div>
              <ArrowRight size={17} className="mt-1 shrink-0" aria-hidden="true" />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function Hash({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-semibold text-neutral-700">{label}</dt>
      <dd className="mt-1 truncate font-mono" title={value}>{value || "Unavailable"}</dd>
    </div>
  );
}
