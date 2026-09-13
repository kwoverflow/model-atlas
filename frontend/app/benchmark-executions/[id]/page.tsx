import {
  Activity,
  ArrowLeft,
  Bot,
  Clock3,
  Database,
  Eye,
  GitBranch,
  ListChecks,
  MemoryStick,
  Quote,
  RotateCcw,
  SearchCheck,
  ShieldAlert,
  ShieldCheck
} from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge } from "@/components/Badge";
import { AgentApprovalControlPanel } from "@/components/AgentApprovalControlPanel";
import { AgentExecutionTracePanel } from "@/components/AgentExecutionTracePanel";
import { RagEvaluationTracePanel } from "@/components/RagEvaluationTracePanel";
import { RuntimeReliabilityTracePanel } from "@/components/RuntimeReliabilityTracePanel";
import { StatusSummaryGrid, type StatusSummaryItem } from "@/components/StatusSummaryGrid";
import { ToolExecutionTracePanel } from "@/components/ToolExecutionTracePanel";
import { api } from "@/lib/api";
import { percent, statusLabel, statusTone } from "@/lib/statusPresentation";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
};

export default async function BenchmarkExecutionDetailPage({ params }: PageProps) {
  const { id } = await params;
  const [detail, agentCheckpoints] = await Promise.all([
    api.benchmarkExecution(id),
    api.agentApprovalCheckpoints(id)
  ]);
  if (!detail) notFound();

  const toolSummary = detail.tool_execution_summary;
  const ragSummary = detail.rag_evaluation_summary;
  const reliabilitySummary = detail.runtime_reliability_summary;
  const agentSummary = detail.agent_execution_summary;
  const hasToolEvidence = toolSummary.tool_case_count > 0;
  const hasRagEvidence = ragSummary.rag_case_count > 0;
  const hasReliabilityEvidence = reliabilitySummary.trial_count > 0;
  const hasAgentEvidence = agentSummary.agent_case_count > 0;
  const toolTrace = detail.tool_traces[0]?.trace;
  const ragTrace = detail.rag_traces[0]?.trace;
  const reliabilityTrace = detail.reliability_traces[0]?.trace;
  const agentTrace = detail.agent_traces[0]?.trace;
  const summaryItems: StatusSummaryItem[] = [];
  if (hasToolEvidence) {
    summaryItems.push(
      {
        label: "Tool Cases",
        value: String(toolSummary.tool_case_count),
        detail: `${toolSummary.multi_step_case_count} multi-step`,
        icon: ListChecks
      },
      {
        label: "Successful Calls",
        value: `${toolSummary.successful_call_count}/${toolSummary.call_count}`,
        detail:
          toolSummary.execution_success_rate === null
            ? "No executable calls"
            : `${percent(toolSummary.execution_success_rate)} execution success`,
        icon: Activity
      },
      {
        label: "Retry Recovery",
        value: `${toolSummary.recovered_call_count}/${toolSummary.retried_call_count}`,
        detail:
          toolSummary.retry_recovery_rate === null
            ? "No retried calls"
            : `${percent(toolSummary.retry_recovery_rate)} recovered`,
        icon: RotateCcw
      },
      {
        label: "Sequence Match",
        value:
          toolSummary.sequence_success_rate === null
            ? "N/A"
            : percent(toolSummary.sequence_success_rate),
        detail: `${toolSummary.invalid_call_case_count} invalid call cases`,
        icon: GitBranch
      }
    );
  }
  if (hasRagEvidence) {
    summaryItems.push(
      {
        label: "RAG Cases",
        value: `${ragSummary.successful_case_count}/${ragSummary.rag_case_count}`,
        detail: `${ragSummary.failed_case_count} failed cases`,
        icon: Database
      },
      {
        label: "Retrieval Recall",
        value: formatRate(ragSummary.average_retrieval_recall),
        detail: `${ragSummary.retrieval_empty_case_count} empty retrievals`,
        icon: SearchCheck
      },
      {
        label: "Citation Precision",
        value: formatRate(ragSummary.average_citation_precision),
        detail: `${formatRate(ragSummary.average_citation_recall)} citation recall`,
        icon: Quote
      },
      {
        label: "Unsupported Claims",
        value: formatRate(ragSummary.average_unsupported_claim_rate),
        detail: `${formatRate(ragSummary.average_groundedness_score)} groundedness`,
        icon: ShieldAlert
      }
    );
  }
  if (hasReliabilityEvidence) {
    summaryItems.push(
      {
        label: "Successful Trials",
        value: `${reliabilitySummary.success_count}/${reliabilitySummary.trial_count}`,
        detail: `${formatRate(reliabilitySummary.trial_coverage_rate)} trial coverage`,
        icon: Activity
      },
      {
        label: "Timeout / OOM",
        value: `${reliabilitySummary.timeout_count} / ${reliabilitySummary.oom_count}`,
        detail: `${reliabilitySummary.error_count} other errors`,
        icon: MemoryStick
      },
      {
        label: "P99 Latency",
        value: formatLatency(reliabilitySummary.p99_end_to_end_latency_ms),
        detail: `${formatLatency(reliabilitySummary.p95_ttft_ms)} P95 TTFT`,
        icon: Clock3
      },
      {
        label: "Context Stress",
        value: formatRate(reliabilitySummary.context_stress_success_rate),
        detail: `${reliabilitySummary.context_stress_trial_count} high-context trials`,
        icon: ShieldAlert
      }
    );
  }
  if (hasAgentEvidence) {
    summaryItems.push(
      {
        label: "Agent Tasks",
        value: `${agentSummary.successful_case_count}/${agentSummary.agent_case_count}`,
        detail: `${agentSummary.failed_case_count} failed tasks`,
        icon: Bot
      },
      {
        label: "Step Success",
        value: formatRate(agentSummary.step_success_rate),
        detail: `${agentSummary.total_step_count} bounded steps`,
        icon: Activity
      },
      {
        label: "Replan Recovery",
        value: formatRate(agentSummary.replan_success_rate),
        detail: `${agentSummary.successful_replan_count}/${agentSummary.replan_count} replans recovered`,
        icon: RotateCcw
      },
      {
        label: "Approval Compliance",
        value: formatRate(agentSummary.approval_compliance_rate),
        detail: `${agentSummary.pending_checkpoint_count} pending / ${agentSummary.denied_checkpoint_count} denied`,
        icon: ShieldCheck
      },
      {
        label: "Policy Violations",
        value: formatRate(agentSummary.policy_violation_rate),
        detail: `${formatRate(agentSummary.action_sequence_accuracy)} sequence accuracy`,
        icon: ShieldAlert
      },
      {
        label: "Observation Coverage",
        value: formatRate(agentSummary.observation_coverage_rate),
        detail: `${agentSummary.halted_case_count} halted tasks`,
        icon: Eye
      }
    );
  }
  if (!summaryItems.length) {
    summaryItems.push({
      label: "Results",
      value: String(detail.result_count),
      detail: `${detail.metric_count} metrics / ${detail.log_count} logs`,
      icon: Activity
    });
  }

  return (
    <>
      <section className="border-b border-line pb-5">
        <Link
          href="/benchmark-executions/new"
          className="inline-flex items-center gap-2 text-sm font-medium text-neutral-600 hover:text-ink"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          Benchmark Execution
        </Link>
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase text-neutral-500">
              Evaluation Evidence
            </div>
            <h1 className="mt-1 text-2xl font-semibold text-ink">
              Run {detail.benchmark_run.id.slice(0, 8)}
            </h1>
            <p className="mt-2 text-sm text-neutral-600">
              {detail.benchmark_run.dataset_version}
            </p>
            {detail.benchmark_run.parent_benchmark_run_id ? (
              <Link
                href={`/benchmark-executions/${detail.benchmark_run.parent_benchmark_run_id}`}
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-teal"
              >
                <GitBranch size={13} aria-hidden="true" /> Parent run {detail.benchmark_run.parent_benchmark_run_id.slice(0, 8)}
              </Link>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={detail.benchmark_run.revision_number > 1 ? "amber" : "neutral"}>
              Revision {detail.benchmark_run.revision_number}
            </Badge>
            <Badge tone={statusTone(detail.benchmark_run.status)}>
              {statusLabel(detail.benchmark_run.status)}
            </Badge>
          </div>
        </div>
      </section>

      <StatusSummaryGrid items={summaryItems} />

      <section className="grid gap-3 border-y border-line py-4 text-sm md:grid-cols-3">
        <ProvenanceItem
          label="Trace schema"
          value={
            agentTrace?.schema_version ??
            reliabilityTrace?.schema_version ??
            ragTrace?.schema_version ??
            toolTrace?.schema_version ??
            "unavailable"
          }
        />
        <ProvenanceItem
          label={
            hasAgentEvidence
              ? "Memory / tools"
              : hasReliabilityEvidence
              ? "Trials / concurrency"
              : hasRagEvidence
                ? "Corpus / registry"
                : "Tool registry"
          }
          value={
            hasAgentEvidence
              ? `${agentTrace?.memory_registry_version ?? "unavailable"} / ${agentTrace?.tool_registry_version ?? "unavailable"}`
              : hasReliabilityEvidence
              ? `${reliabilityTrace?.total_trials ?? 0} / ${reliabilityTrace?.concurrency ?? 0}`
              : hasRagEvidence
              ? `${ragTrace?.retrieval.corpus_version ?? "unavailable"} / ${ragTrace?.retrieval.registry_version ?? "unavailable"}`
              : toolTrace?.registry_version ?? "unavailable"
          }
        />
        <ProvenanceItem label="Adapter" value={detail.benchmark_run.runtime_name} />
      </section>

      {toolSummary.failed_call_count ? (
        <section className="border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm leading-6 text-neutral-700">
          {toolSummary.failed_call_count} tool calls failed or were skipped. Inspect the affected
          step before Gate evaluation.
        </section>
      ) : null}
      {ragSummary.failed_case_count ? (
        <section className="border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm leading-6 text-neutral-700">
          {ragSummary.failed_case_count} RAG cases failed retrieval, citation, groundedness, or
          unsupported-claim checks.
        </section>
      ) : null}
      {hasReliabilityEvidence && reliabilitySummary.success_count < reliabilitySummary.trial_count ? (
        <section className="border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm leading-6 text-neutral-700">
          {reliabilitySummary.trial_count - reliabilitySummary.success_count} runtime trials failed.
          Timeout, OOM, and runtime errors remain separate in the trace.
        </section>
      ) : null}
      {hasAgentEvidence && agentSummary.failed_case_count ? (
        <section className="border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm leading-6 text-neutral-700">
          {agentSummary.failed_case_count} agent tasks failed or halted. Inspect approval decisions,
          recovery branches, action limits, policy violations, and final response evidence.
        </section>
      ) : null}

      {hasAgentEvidence ? (
        <section className="rounded-lg border border-line bg-panel shadow-soft">
          <div className="border-b border-line px-5 py-4">
            <h2 className="text-base font-semibold text-ink">Adaptive agent task traces</h2>
            <p className="mt-1 text-sm text-neutral-600">
              {detail.agent_traces.length} traces / {agentSummary.total_step_count} executed steps
            </p>
          </div>
          {agentCheckpoints.length ? (
            <AgentApprovalControlPanel checkpoints={agentCheckpoints} />
          ) : null}
          <AgentExecutionTracePanel traces={detail.agent_traces} />
        </section>
      ) : null}

      {hasReliabilityEvidence ? (
        <section className="rounded-lg border border-line bg-panel shadow-soft">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-ink">Runtime reliability trials</h2>
              <p className="mt-1 text-sm text-neutral-600">
                {detail.reliability_traces.length} traces / {detail.log_count} execution logs
              </p>
            </div>
            <Link
              href={`/runtime-reliability?left_run_id=${detail.benchmark_run.id}`}
              className="text-sm font-medium text-teal hover:underline"
            >
              Compare Runtime
            </Link>
          </div>
          <RuntimeReliabilityTracePanel traces={detail.reliability_traces} />
        </section>
      ) : null}

      {hasRagEvidence ? (
        <section className="rounded-lg border border-line bg-panel shadow-soft">
          <div className="border-b border-line px-5 py-4">
            <h2 className="text-base font-semibold text-ink">RAG case traces</h2>
            <p className="mt-1 text-sm text-neutral-600">
              {detail.rag_traces.length} traces / {detail.log_count} execution logs
            </p>
          </div>
          <RagEvaluationTracePanel traces={detail.rag_traces} />
        </section>
      ) : null}

      {hasToolEvidence ? (
        <section className="rounded-lg border border-line bg-panel shadow-soft">
          <div className="border-b border-line px-5 py-4">
            <h2 className="text-base font-semibold text-ink">Executable case traces</h2>
            <p className="mt-1 text-sm text-neutral-600">
              {detail.tool_traces.length} traces / {detail.log_count} execution logs
            </p>
          </div>
          <ToolExecutionTracePanel traces={detail.tool_traces} />
        </section>
      ) : null}
    </>
  );
}

function ProvenanceItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-neutral-500">{label}</div>
      <div className="mt-1 break-all font-mono text-xs text-neutral-700">{value}</div>
    </div>
  );
}

function formatRate(value: number | null): string {
  return value === null ? "N/A" : percent(value);
}

function formatLatency(value: number | null): string {
  if (value === null) return "N/A";
  return value >= 1_000 ? `${(value / 1_000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
}
