import { ExternalLink } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/Badge";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type { ReferenceConfiguration } from "@/types/api";

export function ConfigurationComparison({ rows }: { rows: ReferenceConfiguration[] }) {
  return (
    <div className="overflow-x-auto border-y border-line bg-panel">
      <table className="w-full min-w-[1320px] text-left text-sm">
        <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
          <tr>
            <th className="px-4 py-3">Configuration</th>
            <th className="px-4 py-3">Model / digest</th>
            <th className="px-4 py-3">Runtime</th>
            <th className="px-4 py-3">Context</th>
            <th className="px-4 py-3">Cases</th>
            <th className="px-4 py-3">Task completion</th>
            <th className="px-4 py-3">Groundedness</th>
            <th className="px-4 py-3">Tool success</th>
            <th className="px-4 py-3">P95</th>
            <th className="px-4 py-3">OOM / errors</th>
            <th className="px-4 py-3">Critical fails</th>
            <th className="px-4 py-3">Human review</th>
            <th className="px-4 py-3">Gate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((row) => (
            <tr key={row.entry_name} className="align-top">
              <td className="px-4 py-3">
                <div className="font-semibold text-ink">{row.entry_name}</div>
                <div className="mt-1 text-xs text-neutral-500">{row.prompt_bundle}</div>
              </td>
              <td className="max-w-56 px-4 py-3">
                <div className="font-medium text-ink">{row.model_name ?? "Not observed"}</div>
                <div className="mt-1 truncate font-mono text-xs text-neutral-500" title={row.model_digest ?? undefined}>
                  {shortDigest(row.model_digest)}
                </div>
              </td>
              <td className="px-4 py-3 text-neutral-700">
                {row.runtime_name ?? "Not run"}
                <div className="text-xs text-neutral-500">{row.runtime_version ?? ""}</div>
              </td>
              <td className="px-4 py-3 tabular-nums">{row.context_length.toLocaleString()}</td>
              <td className="px-4 py-3 tabular-nums">{row.completed_case_count}</td>
              <MetricCell value={row.metrics.task_completion_rate} />
              <MetricCell value={row.metrics.rag_groundedness_score} />
              <MetricCell value={row.metrics.tool_execution_success_rate} />
              <td className="px-4 py-3 tabular-nums">{formatLatency(row.metrics.p95_end_to_end_latency_ms)}</td>
              <td className="px-4 py-3 tabular-nums">{row.oom_count} / {row.error_count}</td>
              <td className="px-4 py-3 tabular-nums">{row.critical_failure_count}</td>
              <td className="px-4 py-3 tabular-nums">{row.human_reviewed_count}</td>
              <td className="px-4 py-3">
                {row.gate_evaluation_id ? (
                  <Link href={`/deployment-gates/${row.gate_evaluation_id}`} className="inline-flex items-center gap-1 font-medium text-teal hover:underline">
                    {statusLabel(row.gate_verdict)}
                    <ExternalLink size={13} aria-hidden="true" />
                  </Link>
                ) : row.status === "completed" && row.deployment_configuration_id ? (
                  <Link
                    href={`/deployment-gates/new?deployment_configuration_id=${row.deployment_configuration_id}`}
                    className="inline-flex items-center gap-1 font-medium text-teal hover:underline"
                  >
                    Run Preflight
                    <ExternalLink size={13} aria-hidden="true" />
                  </Link>
                ) : (
                  <Badge tone={statusTone(row.gate_verdict)}>{statusLabel(row.gate_verdict)}</Badge>
                )}
              </td>
            </tr>
          ))}
          {!rows.length ? (
            <tr>
              <td colSpan={13} className="px-4 py-8 text-neutral-500">No runtime configurations found.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function MetricCell({ value }: { value: number | null }) {
  return <td className="px-4 py-3 tabular-nums">{value === null ? "-" : `${(value * 100).toFixed(1)}%`}</td>;
}

function formatLatency(value: number | null): string {
  return value === null ? "-" : `${Math.round(value).toLocaleString()} ms`;
}

function shortDigest(value: string | null): string {
  if (!value) return "Digest unavailable";
  return value.length > 22 ? `${value.slice(0, 22)}...` : value;
}
