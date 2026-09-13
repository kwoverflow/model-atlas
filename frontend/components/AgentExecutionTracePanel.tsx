import {
  Bot,
  Database,
  Eye,
  GitBranch,
  HardDrive,
  MessageSquareText,
  PencilLine,
  RotateCcw,
  Search,
  ShieldCheck,
  Wrench,
  type LucideIcon
} from "lucide-react";

import { Badge } from "@/components/Badge";
import { AgentReplayButton } from "@/components/AgentReplayButton";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";
import type { AgentExecutionStep, AgentExecutionTraceRecord } from "@/types/api";

type AgentExecutionTracePanelProps = {
  traces: AgentExecutionTraceRecord[];
};

const actionIcons: Record<string, LucideIcon> = {
  approval_checkpoint: ShieldCheck,
  memory_read: HardDrive,
  memory_write: PencilLine,
  retrieve: Search,
  tool: Wrench,
  respond: MessageSquareText
};

export function AgentExecutionTracePanel({ traces }: AgentExecutionTracePanelProps) {
  return (
    <div className="divide-y divide-line">
      {traces.map((record) => {
        const trace = record.trace;
        const replanRate = trace.replan_count
          ? trace.successful_replan_count / trace.replan_count
          : null;
        const approvalRate = trace.approval_checkpoint_count
          ? trace.approved_checkpoint_count / trace.approval_checkpoint_count
          : null;
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
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-neutral-500">
                  <span>
                    {trace.step_count}/{trace.execution_step_limit ?? trace.step_limit} executed
                  </span>
                  <span>/</span>
                  <span>{trace.tool_call_count} tools</span>
                  <span>/</span>
                  <span>{trace.retrieval_count} retrievals</span>
                  <span>/</span>
                  <span>{trace.memory_action_count} memory actions</span>
                </div>
              </div>
              <div className="grid justify-items-end gap-2">
                <Badge tone={statusTone(trace.status)}>{statusLabel(trace.status)}</Badge>
                <AgentReplayButton benchmarkResultId={record.benchmark_result_id} />
              </div>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Plan valid" value={trace.plan_valid} />
              <Metric label="Sequence match" value={trace.sequence_match} />
              <RateMetric label="Step success" value={trace.step_success_rate} />
              <Metric label="Final response" value={trace.final_response_present} />
              <RateMetric label="Replan recovery" value={replanRate} />
              <RateMetric label="Approval compliance" value={approvalRate} />
              <CountMetric
                label="Unrecovered failures"
                value={trace.unrecovered_failure_count}
                healthyWhenZero
              />
              <CountMetric
                label="Violations"
                value={trace.policy_violation_count}
                healthyWhenZero
              />
            </div>

            {trace.parse_error || trace.halt_reason ? (
              <div className="mt-4 border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm text-neutral-700">
                {trace.parse_error ?? `Execution halted: ${statusLabel(trace.halt_reason ?? "")}`}
              </div>
            ) : null}

            <div className="mt-5 overflow-x-auto rounded-md border border-line">
              <table className="w-full min-w-[980px] text-left text-sm">
                <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
                  <tr>
                    <th className="px-4 py-3">Step</th>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">Expected</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Evidence</th>
                    <th className="px-4 py-3">Duration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {trace.steps.map((step) => (
                    <AgentStepRow key={`${record.sample_id}-${step.step_index}`} step={step} />
                  ))}
                  {!trace.steps.length ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-5 text-neutral-500">
                        No agent steps were executed.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            {trace.replans.length ? (
              <div className="mt-5 border-t border-line pt-4">
                <h4 className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                  <GitBranch size={15} aria-hidden="true" /> Recovery decisions
                </h4>
                <div className="mt-3 divide-y divide-line border-y border-line">
                  {trace.replans.map((replan) => (
                    <div
                      key={`${record.sample_id}-replan-${replan.replan_index}`}
                      className="grid gap-3 py-3 text-sm md:grid-cols-[120px_1fr_auto] md:items-center"
                    >
                      <div className="font-medium text-ink">Replan {replan.replan_index}</div>
                      <div className="min-w-0 text-neutral-600">
                        <div>
                          <span className="font-mono text-xs">{replan.trigger_error_type}</span>
                          <span className="mx-2">/</span>
                          <span>{statusLabel(replan.strategy)}</span>
                          <span className="mx-2">/</span>
                          <span>{replan.recovery_step_indices.length} recovery steps</span>
                        </div>
                        {replan.source === "live_callback" && replan.model_call ? (
                          <div className="mt-1 font-mono text-xs text-neutral-500">
                            {String(replan.model_call.model_name ?? "live callback")} / {" "}
                            {Number(replan.model_call.prompt_tokens ?? 0)}+
                            {Number(replan.model_call.completion_tokens ?? 0)} tokens / {" "}
                            {Number(replan.model_call.model_call_latency_ms ?? 0).toFixed(1)} ms / ${" "}
                            {Number(replan.model_call.estimated_cost_usd ?? 0).toFixed(6)}
                          </div>
                        ) : null}
                      </div>
                      <Badge tone={statusTone(replan.status)}>
                        {statusLabel(replan.status)}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-4 grid gap-3 border-t border-line pt-3 text-xs text-neutral-500 md:grid-cols-3 xl:grid-cols-6">
              <Provenance label="Trace" value={trace.schema_version} icon={Bot} />
              <Provenance label="Memory" value={trace.memory_registry_version} icon={HardDrive} />
              <Provenance label="Tools" value={trace.tool_registry_version} icon={Wrench} />
              <Provenance label="Retrieval" value={trace.retriever_version} icon={Database} />
              <Provenance
                label="Observation"
                value={trace.observation_schema_version ?? "unavailable"}
                icon={Eye}
              />
              <Provenance
                label="Approval"
                value={trace.approval_policy_version ?? "unavailable"}
                icon={ShieldCheck}
              />
            </div>

            <details className="mt-4 border-t border-line pt-3">
              <summary className="cursor-pointer text-sm font-medium text-neutral-700">
                Raw agent trace
              </summary>
              <pre className="mt-3 max-h-[480px] overflow-auto bg-neutral-950 p-3 text-xs leading-5 text-neutral-100">
                {JSON.stringify(trace, null, 2)}
              </pre>
            </details>
          </section>
        );
      })}
      {!traces.length ? (
        <div className="px-5 py-8 text-sm text-neutral-600">No agent traces are stored.</div>
      ) : null}
    </div>
  );
}

function AgentStepRow({ step }: { step: AgentExecutionStep }) {
  const Icon = actionIcons[step.action] ?? Bot;
  return (
    <tr className="align-top">
      <td className="px-4 py-3 font-medium text-ink">{step.step_index + 1}</td>
      <td className="px-4 py-3">
        <span className="inline-flex items-center gap-2 font-medium text-neutral-700">
          <Icon size={15} aria-hidden="true" />
          {statusLabel(step.action)}
        </span>
        <div className="mt-1 text-xs text-neutral-400">
          {step.phase === "recovery" ? "Recovery branch" : "Base plan"}
        </div>
        {step.recovered ? (
          <div className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-teal">
            <RotateCcw size={13} aria-hidden="true" /> recovered
          </div>
        ) : null}
        {step.recovered_by_replan ? (
          <div className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-teal">
            <GitBranch size={13} aria-hidden="true" /> recovered by replan
          </div>
        ) : null}
      </td>
      <td className="px-4 py-3 text-neutral-600">
        {step.expected_action ? statusLabel(step.expected_action) : "N/A"}
      </td>
      <td className="px-4 py-3">
        <Badge tone={statusTone(step.status)}>{statusLabel(step.status)}</Badge>
        {step.retry_count ? (
          <div className="mt-1 text-xs text-neutral-500">{step.retry_count} retries</div>
        ) : null}
      </td>
      <td className="px-4 py-3">
        {step.error_message ? (
          <div className="max-w-md text-rose">{step.error_message}</div>
        ) : (
          <div className="max-w-md break-words text-xs leading-5 text-neutral-600">
            {summarizeOutput(step)}
          </div>
        )}
        {step.policy_violations.length ? (
          <div className="mt-1 text-xs text-rose">{step.policy_violations.join("; ")}</div>
        ) : null}
      </td>
      <td className="px-4 py-3 text-neutral-600">{step.duration_ms.toFixed(2)} ms</td>
    </tr>
  );
}

function summarizeOutput(step: AgentExecutionStep): string {
  if (!step.output) return "No output";
  if (step.action === "memory_read") {
    return String(step.output.memory_id ?? "Memory read completed");
  }
  if (step.action === "memory_write") {
    return `${String(step.output.memory_id ?? "task memory")} / task-local`;
  }
  if (step.action === "retrieve") {
    const retrieval = step.output.retrieval;
    if (retrieval && typeof retrieval === "object" && "retrieved_chunks" in retrieval) {
      const chunks = (retrieval as { retrieved_chunks?: unknown[] }).retrieved_chunks;
      return `${chunks?.length ?? 0} chunks retrieved`;
    }
  }
  if (step.action === "tool") return "Registered tool execution captured";
  if (step.action === "approval_checkpoint") {
    return `${String(step.output.checkpoint_id ?? "checkpoint")} / ${String(
      step.output.decision ?? step.status
    )} / ${String(step.output.decided_by ?? "awaiting decision")}`;
  }
  if (step.action === "respond") return String(step.output.content ?? "Response captured");
  return JSON.stringify(step.output);
}

function Metric({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="border-b border-line pb-3">
      <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
      <div className={`mt-2 text-lg font-semibold ${value ? "text-teal" : "text-rose"}`}>
        {value ? "Pass" : "Fail"}
      </div>
    </div>
  );
}

function RateMetric({ label, value }: { label: string; value: number | null }) {
  const healthy = value === 1;
  return (
    <div className="border-b border-line pb-3">
      <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
      <div className={`mt-2 text-lg font-semibold ${healthy ? "text-teal" : "text-rose"}`}>
        {value === null ? "N/A" : percent(value)}
      </div>
    </div>
  );
}

function CountMetric({
  label,
  value,
  healthyWhenZero = false
}: {
  label: string;
  value: number;
  healthyWhenZero?: boolean;
}) {
  const healthy = healthyWhenZero ? value === 0 : value > 0;
  return (
    <div className="border-b border-line pb-3">
      <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
      <div className={`mt-2 text-lg font-semibold ${healthy ? "text-teal" : "text-rose"}`}>
        {value}
      </div>
    </div>
  );
}

function Provenance({
  label,
  value,
  icon: Icon
}: {
  label: string;
  value: string;
  icon: LucideIcon;
}) {
  return (
    <div>
      <div className="inline-flex items-center gap-1.5 font-semibold uppercase text-neutral-400">
        <Icon size={13} aria-hidden="true" /> {label}
      </div>
      <div className="mt-1 break-all font-mono">{value}</div>
    </div>
  );
}
