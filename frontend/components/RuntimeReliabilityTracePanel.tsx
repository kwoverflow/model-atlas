import { AlertTriangle, CheckCircle2, Gauge, MemoryStick, Timer } from "lucide-react";

import { Badge } from "@/components/Badge";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type { RuntimeReliabilityTraceRecord } from "@/types/api";

type RuntimeReliabilityTracePanelProps = {
  traces: RuntimeReliabilityTraceRecord[];
};

export function RuntimeReliabilityTracePanel({
  traces
}: RuntimeReliabilityTracePanelProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1100px] text-left text-sm">
        <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
          <tr>
            <th className="px-4 py-3">Case / trial</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Latency</th>
            <th className="px-4 py-3">TTFT</th>
            <th className="px-4 py-3">Throughput</th>
            <th className="px-4 py-3">Context</th>
            <th className="px-4 py-3">Memory</th>
            <th className="px-4 py-3">Error</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {traces.map((record) => {
            const trace = record.trace;
            return (
              <tr key={record.benchmark_result_id} className="align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">
                    {record.case_title ?? trace.external_case_id}
                  </div>
                  <div className="mt-1 font-mono text-xs text-neutral-500">
                    {trace.external_case_id} / {trace.trial_index} of {trace.total_trials}
                  </div>
                  <div className="mt-1 text-xs text-neutral-500">
                    concurrency {trace.concurrency} / timeout {formatMs(trace.case_timeout_ms)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={statusTone(trace.status)}>{statusLabel(trace.status)}</Badge>
                  <div className="mt-2 inline-flex items-center gap-1.5 text-xs text-neutral-500">
                    {trace.successful ? (
                      <CheckCircle2 size={14} className="text-teal" aria-hidden="true" />
                    ) : (
                      <AlertTriangle size={14} className="text-rose" aria-hidden="true" />
                    )}
                    seed {trace.seed ?? "none"}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <MetricValue icon={Timer} value={formatMs(trace.end_to_end_latency_ms)} />
                  <div className="mt-1 text-xs text-neutral-500">
                    {trace.within_timeout ? "within timeout" : "timeout exceeded"}
                  </div>
                </td>
                <td className="px-4 py-3">{formatMs(trace.ttft_ms)}</td>
                <td className="px-4 py-3">
                  <MetricValue icon={Gauge} value={`${trace.tokens_per_second.toFixed(1)} tok/s`} />
                  <div className="mt-1 text-xs text-neutral-500">
                    {trace.completion_tokens} output tokens
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div>{percent(trace.context_utilization_ratio)}</div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {Math.round(trace.context_tokens).toLocaleString()} /{" "}
                    {trace.context_window_tokens.toLocaleString()}
                  </div>
                  {trace.context_stress ? (
                    <div className="mt-1 text-xs font-medium text-amber">context stress</div>
                  ) : null}
                </td>
                <td className="px-4 py-3">
                  <MetricValue
                    icon={MemoryStick}
                    value={formatMemory(trace.gpu_vram_used_mb)}
                  />
                  <div className="mt-1 text-xs text-neutral-500">
                    peak {formatMemory(trace.peak_memory_mb)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className={trace.error_type ? "font-medium text-rose" : "text-neutral-500"}>
                    {trace.error_type ?? "none"}
                  </div>
                  {trace.error_message ? (
                    <div className="mt-1 max-w-xs text-xs leading-5 text-neutral-500">
                      {trace.error_message}
                    </div>
                  ) : null}
                </td>
              </tr>
            );
          })}
          {!traces.length ? (
            <tr>
              <td colSpan={8} className="px-4 py-8 text-neutral-500">
                No runtime reliability traces are stored.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}

function MetricValue({
  icon: Icon,
  value
}: {
  icon: typeof Timer;
  value: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 font-medium text-ink">
      <Icon size={14} aria-hidden="true" />
      {value}
    </span>
  );
}

function formatMs(value: number): string {
  return value >= 1_000 ? `${(value / 1_000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
}

function formatMemory(value: number | null): string {
  return value === null ? "N/A" : `${(value / 1_024).toFixed(1)} GB`;
}
