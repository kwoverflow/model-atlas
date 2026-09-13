import { ExternalLink, FileSearch, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type { ReferenceCriticalFailure } from "@/types/api";

export function FailureReviewQueue({ failures }: { failures: ReferenceCriticalFailure[] }) {
  const visible = failures.slice(0, 12);

  return (
    <div className="overflow-x-auto border-y border-line bg-panel">
      <table className="w-full min-w-[1120px] text-left text-sm">
        <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
          <tr>
            <th className="px-4 py-3">Case</th>
            <th className="px-4 py-3">Configuration</th>
            <th className="px-4 py-3">Failure reason</th>
            <th className="px-4 py-3">Observed output</th>
            <th className="px-4 py-3">Quality</th>
            <th className="px-4 py-3">Review</th>
            <th className="px-4 py-3">Inspect</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {visible.map((failure) => (
            <tr key={failure.benchmark_result_id} className="align-top">
              <td className="max-w-64 px-4 py-3">
                <div className="font-semibold text-ink">{failure.title}</div>
                <div className="mt-1 font-mono text-xs text-neutral-500">{failure.external_case_id}</div>
              </td>
              <td className="px-4 py-3 text-neutral-700">{failure.entry_name}</td>
              <td className="px-4 py-3"><Badge tone="rose">{statusLabel(failure.failure_reason)}</Badge></td>
              <td className="max-w-80 px-4 py-3 text-xs leading-5 text-neutral-600">{failure.observed_output_summary}</td>
              <td className="px-4 py-3 tabular-nums">{failure.quality_score === null ? "-" : failure.quality_score.toFixed(3)}</td>
              <td className="px-4 py-3"><Badge tone={statusTone(failure.review_status)}>{statusLabel(failure.review_status)}</Badge></td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <Link href={failure.benchmark_execution_href} aria-label={`Open run for ${failure.external_case_id}`} title="Open benchmark run" className="text-neutral-600 hover:text-teal">
                    <FileSearch size={18} aria-hidden="true" />
                  </Link>
                  <Link href={failure.judge_review_href} aria-label={`Review ${failure.external_case_id}`} title="Open Judge review" className="text-neutral-600 hover:text-teal">
                    <ExternalLink size={18} aria-hidden="true" />
                  </Link>
                  {failure.gate_detail_href ? (
                    <Link href={failure.gate_detail_href} aria-label={`Open Gate for ${failure.external_case_id}`} title="Open Deployment Gate" className="text-neutral-600 hover:text-teal">
                      <ShieldCheck size={18} aria-hidden="true" />
                    </Link>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
          {!visible.length ? (
            <tr><td colSpan={7} className="px-4 py-8 text-neutral-500">No critical failures are present in the selected runs.</td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
