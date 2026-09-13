import { CheckCircle2, CircleX, GitBranch, RotateCcw } from "lucide-react";

import { Badge } from "@/components/Badge";
import { statusLabel, statusTone } from "@/lib/statusPresentation";
import type { ToolExecutionTraceRecord } from "@/types/api";

type ToolExecutionTracePanelProps = {
  traces: ToolExecutionTraceRecord[];
};

export function ToolExecutionTracePanel({ traces }: ToolExecutionTracePanelProps) {
  return (
    <div className="divide-y divide-line">
      {traces.map((record) => {
        const trace = record.trace;
        return (
          <section key={record.benchmark_result_id} className="px-5 py-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-xs font-semibold uppercase text-neutral-500">
                  {record.sample_id} {record.criticality ? `/ ${record.criticality}` : ""}
                </div>
                <h3 className="mt-1 text-base font-semibold text-ink">
                  {record.case_title ?? trace.external_case_id}
                </h3>
              </div>
              <Badge tone={statusTone(trace.status)}>{statusLabel(trace.status)}</Badge>
            </div>

            <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
              <SequenceRow label="Expected" values={trace.expected_tool_sequence} />
              <SequenceRow label="Actual" values={trace.actual_tool_sequence} />
            </div>

            {!trace.parse_valid ? (
              <div className="mt-4 border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm text-neutral-700">
                {trace.parse_error ?? "Tool call parsing failed."}
              </div>
            ) : null}

            <div className="mt-4 overflow-x-auto rounded-md border border-line">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
                  <tr>
                    <th className="px-4 py-3">Step</th>
                    <th className="px-4 py-3">Tool</th>
                    <th className="px-4 py-3">Selection</th>
                    <th className="px-4 py-3">Arguments</th>
                    <th className="px-4 py-3">Execution</th>
                    <th className="px-4 py-3">Attempts</th>
                    <th className="px-4 py-3">Duration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {trace.steps.map((step) => (
                    <tr key={step.call_id}>
                      <td className="px-4 py-3 font-medium text-ink">{step.step_index + 1}</td>
                      <td className="px-4 py-3">
                        <div className="font-mono text-xs text-ink">{step.tool_name}</div>
                        {step.expected_tool_name && step.expected_tool_name !== step.tool_name ? (
                          <div className="mt-1 text-xs text-rose">
                            expected {step.expected_tool_name}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <BooleanState value={step.selection_valid} />
                      </td>
                      <td className="px-4 py-3">
                        <BooleanState value={step.arguments_valid} />
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(step.execution_status)}>
                          {statusLabel(step.execution_status)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-neutral-700">
                        <span className="inline-flex items-center gap-1.5">
                          {step.retry_count ? <RotateCcw size={14} aria-hidden="true" /> : null}
                          {step.attempt_count}
                          {step.recovered ? " / recovered" : ""}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-neutral-700">
                        {step.duration_ms.toFixed(2)} ms
                      </td>
                    </tr>
                  ))}
                  {!trace.steps.length ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-5 text-neutral-500">
                        No executable steps were produced.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            {trace.steps.map((step) => (
              <details key={`${step.call_id}-payload`} className="border-b border-line py-3">
                <summary className="cursor-pointer text-sm font-medium text-neutral-700">
                  Step {step.step_index + 1} arguments, attempts, and output
                </summary>
                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  <PayloadBlock label="Arguments" value={step.arguments} />
                  <PayloadBlock label="Attempts" value={step.attempts} />
                  <PayloadBlock
                    label="Output"
                    value={
                      step.output ?? {
                        error_type: step.error_type,
                        error_message: step.error_message,
                        validation_errors: step.validation_errors
                      }
                    }
                  />
                </div>
              </details>
            ))}
          </section>
        );
      })}
      {!traces.length ? (
        <div className="px-5 py-8 text-sm text-neutral-600">No tool execution traces are stored.</div>
      ) : null}
    </div>
  );
}

function SequenceRow({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="flex min-w-0 items-start gap-3 border-b border-line pb-3">
      <GitBranch size={16} className="mt-0.5 shrink-0 text-neutral-400" aria-hidden="true" />
      <div className="min-w-0">
        <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
        <div className="mt-1 break-words font-mono text-xs leading-5 text-neutral-700">
          {values.length ? values.join(" -> ") : "None"}
        </div>
      </div>
    </div>
  );
}

function BooleanState({ value }: { value: boolean }) {
  return value ? (
    <span className="inline-flex items-center gap-1.5 text-teal">
      <CheckCircle2 size={15} aria-hidden="true" /> Valid
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-rose">
      <CircleX size={15} aria-hidden="true" /> Invalid
    </span>
  );
}

function PayloadBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
      <pre className="mt-2 max-h-64 overflow-auto bg-neutral-950 p-3 text-xs leading-5 text-neutral-100">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
