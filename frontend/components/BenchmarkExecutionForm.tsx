"use client";

import {
  Activity,
  BrainCircuit,
  Database,
  Gauge,
  HardDrive,
  Layers3,
  ListChecks,
  PlayCircle,
  Quote,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  Timer,
  Workflow,
  Wrench
} from "lucide-react";
import Link from "next/link";
import type { FormEvent } from "react";
import { useMemo, useState } from "react";

import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  AgentRuntimeDescriptor,
  BenchmarkExecutionRead,
  BenchmarkTask,
  DeploymentConfiguration,
  EvaluationSuite,
  OperationalMemoryRegistry,
  PromptVersion,
  RagCorpusRegistry,
  RetrieverDescriptor,
  RuntimeHealthRead,
  ToolRegistry
} from "@/types/api";

type BenchmarkExecutionFormProps = {
  configurations: DeploymentConfiguration[];
  suites: EvaluationSuite[];
  tasks: BenchmarkTask[];
  prompts: PromptVersion[];
  toolRegistry: ToolRegistry;
  ragCorpusRegistry: RagCorpusRegistry;
  ragRetriever: RetrieverDescriptor;
  agentRuntime: AgentRuntimeDescriptor;
  operationalMemoryRegistry: OperationalMemoryRegistry;
};

export function BenchmarkExecutionForm({
  configurations,
  suites,
  tasks,
  prompts,
  toolRegistry,
  ragCorpusRegistry,
  ragRetriever,
  agentRuntime,
  operationalMemoryRegistry
}: BenchmarkExecutionFormProps) {
  const [configurationId, setConfigurationId] = useState(configurations[0]?.id ?? "");
  const [suiteId, setSuiteId] = useState(suites[0]?.id ?? "");
  const [taskId, setTaskId] = useState(tasks[0]?.id ?? "");
  const matchingPrompts = useMemo(
    () => prompts.filter((prompt) => prompt.benchmark_task_id === taskId),
    [prompts, taskId]
  );
  const [promptId, setPromptId] = useState(matchingPrompts[0]?.id ?? prompts[0]?.id ?? "");
  const [adapterName, setAdapterName] = useState<"mock" | "openai_compatible">("mock");
  const [agentReplanMode, setAgentReplanMode] = useState<
    "disabled" | "mock_fixture" | "openai_compatible"
  >("disabled");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelName, setModelName] = useState("");
  const [maxCases, setMaxCases] = useState("5");
  const [dataSource, setDataSource] = useState("local_authored");
  const [executionMode, setExecutionMode] = useState<"standard" | "reliability">("standard");
  const [trialsPerCase, setTrialsPerCase] = useState("5");
  const [concurrency, setConcurrency] = useState("4");
  const [caseTimeoutMs, setCaseTimeoutMs] = useState("120000");
  const [status, setStatus] = useState<string | null>(null);
  const [health, setHealth] = useState<RuntimeHealthRead | null>(null);
  const [result, setResult] = useState<BenchmarkExecutionRead | null>(null);

  async function checkHealth() {
    setStatus("Checking runtime");
    const params = new URLSearchParams({
      deployment_configuration_id: configurationId,
      adapter_name: adapterName
    });
    if (baseUrl) {
      params.set("base_url", baseUrl);
    }
    if (modelName) {
      params.set("model", modelName);
    }
    const response = await browserApiFetch(
      `${API_BASE_URL}/benchmark-executions/runtime-health?${params.toString()}`
    );
    if (!response.ok) {
      setStatus("Runtime check failed");
      return;
    }
    const payload = (await response.json()) as RuntimeHealthRead;
    setHealth(payload);
    setStatus(payload.healthy ? "Runtime ready" : "Runtime unavailable");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Executing cases");
    setResult(null);
    const response = await browserApiFetch(`${API_BASE_URL}/benchmark-executions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        deployment_configuration_id: configurationId,
        evaluation_suite_id: suiteId,
        benchmark_task_id: taskId,
        prompt_version_id: promptId,
        adapter_name: adapterName,
        adapter_config_json: {
          ...(baseUrl ? { base_url: baseUrl } : {}),
          ...(modelName ? { model: modelName } : {}),
          ...(agentReplanMode === "openai_compatible" && baseUrl
            ? { agent_replan_base_url: baseUrl }
            : {}),
          ...(agentReplanMode === "openai_compatible" && modelName
            ? { agent_replan_model: modelName }
            : {})
        },
        agent_live_replan_mode: agentReplanMode,
        data_source: dataSource,
        max_cases: maxCases ? Number(maxCases) : null,
        reliability_mode: executionMode === "reliability",
        trials_per_case: executionMode === "reliability" ? Number(trialsPerCase) : 1,
        concurrency: executionMode === "reliability" ? Number(concurrency) : 1,
        case_timeout_ms: Number(caseTimeoutMs)
      })
    });
    if (!response.ok) {
      setStatus("Execution failed");
      return;
    }
    const payload = (await response.json()) as BenchmarkExecutionRead;
    setResult(payload);
    setStatus("Execution completed");
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <form onSubmit={submit} className="grid gap-4 rounded-lg border border-line bg-panel p-5 shadow-soft">
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Deployment configuration
          <select value={configurationId} onChange={(event) => setConfigurationId(event.target.value)} className="h-10 rounded-md border border-line bg-white px-3 text-sm">
            {configurations.map((configuration) => (
              <option key={configuration.id} value={configuration.id}>{configuration.name}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-2 text-sm font-medium text-neutral-700">
          Evaluation suite
          <select value={suiteId} onChange={(event) => setSuiteId(event.target.value)} className="h-10 rounded-md border border-line bg-white px-3 text-sm">
            {suites.map((suite) => (
              <option key={suite.id} value={suite.id}>{suite.name} {suite.version_label}</option>
            ))}
          </select>
        </label>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Benchmark task
            <select
              value={taskId}
              onChange={(event) => {
                const nextTaskId = event.target.value;
                setTaskId(nextTaskId);
                setPromptId(
                  prompts.find((prompt) => prompt.benchmark_task_id === nextTaskId)?.id ?? ""
                );
              }}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>{task.name}</option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Prompt version
            <select value={promptId} onChange={(event) => setPromptId(event.target.value)} className="h-10 rounded-md border border-line bg-white px-3 text-sm">
              {matchingPrompts.map((prompt) => (
                <option key={prompt.id} value={prompt.id}>{prompt.name} {prompt.version_label}</option>
              ))}
            </select>
          </label>
        </div>
        <div>
          <div className="text-sm font-medium text-neutral-700">Execution mode</div>
          <div className="mt-2 inline-flex rounded-md border border-line bg-neutral-50 p-1">
            {(["standard", "reliability"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setExecutionMode(mode)}
                aria-pressed={executionMode === mode}
                className={`h-8 rounded px-3 text-sm font-medium ${
                  executionMode === mode
                    ? "bg-white text-ink shadow-sm"
                    : "text-neutral-500 hover:text-ink"
                }`}
              >
                {mode === "standard" ? "Standard" : "Reliability"}
              </button>
            ))}
          </div>
        </div>
        {executionMode === "reliability" ? (
          <div className="grid gap-4 md:grid-cols-3">
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Trials per case
              <input
                value={trialsPerCase}
                onChange={(event) => setTrialsPerCase(event.target.value)}
                min={1}
                max={20}
                type="number"
                className="h-10 rounded-md border border-line bg-white px-3 text-sm"
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Concurrency
              <input
                value={concurrency}
                onChange={(event) => setConcurrency(event.target.value)}
                min={1}
                max={16}
                type="number"
                className="h-10 rounded-md border border-line bg-white px-3 text-sm"
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Case timeout (ms)
              <input
                value={caseTimeoutMs}
                onChange={(event) => setCaseTimeoutMs(event.target.value)}
                min={100}
                max={300000}
                step={100}
                type="number"
                className="h-10 rounded-md border border-line bg-white px-3 text-sm"
              />
            </label>
          </div>
        ) : null}
        <div className="border-y border-line py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2 text-sm font-medium text-neutral-700">
              <ShieldCheck size={16} aria-hidden="true" />
              Agent approval control
            </div>
            <span className="font-mono text-xs text-neutral-500">
              persisted / policy scoped
            </span>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Adapter
            <select
              value={adapterName}
              onChange={(event) => {
                const value = event.target.value as "mock" | "openai_compatible";
                setAdapterName(value);
                if (value !== "mock" && agentReplanMode === "mock_fixture") {
                  setAgentReplanMode("disabled");
                }
              }}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="mock">mock</option>
              <option value="openai_compatible">openai_compatible</option>
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Agent replan
            <select
              value={agentReplanMode}
              onChange={(event) =>
                setAgentReplanMode(
                  event.target.value as
                    | "disabled"
                    | "mock_fixture"
                    | "openai_compatible"
                )
              }
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="disabled">Disabled</option>
              {adapterName === "mock" ? <option value="mock_fixture">Mock fixture</option> : null}
              <option value="openai_compatible">OpenAI compatible</option>
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Max cases
            <input value={maxCases} onChange={(event) => setMaxCases(event.target.value)} min={1} max={500} type="number" className="h-10 rounded-md border border-line bg-white px-3 text-sm" />
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Data source
            <select value={dataSource} onChange={(event) => setDataSource(event.target.value)} className="h-10 rounded-md border border-line bg-white px-3 text-sm">
              <option value="local_authored">local_authored</option>
              <option value="production_captured">production_captured</option>
              <option value="external_benchmark">external_benchmark</option>
              <option value="synthetic_demo">synthetic_demo</option>
            </select>
          </label>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            OpenAI base URL
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="http://host.docker.internal:1234"
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Model name
            <input
              value={modelName}
              onChange={(event) => setModelName(event.target.value)}
              placeholder="optional; first /v1/models entry if blank"
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={checkHealth} className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm font-medium">
            <Activity size={16} aria-hidden="true" />
            Check Runtime
          </button>
          <button type="submit" className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white">
            <PlayCircle size={16} aria-hidden="true" />
            {executionMode === "reliability" ? "Run Trials" : "Run Cases"}
          </button>
          {status ? <span className="text-sm text-neutral-600">{status}</span> : null}
        </div>
      </form>

      <aside className="grid gap-4">
        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <h2 className="text-sm font-semibold text-ink">Runtime Health</h2>
          <div className="mt-3 text-sm text-neutral-700">
            {health ? (
              <>
                <div>{health.healthy ? "Healthy" : "Unavailable"}</div>
                <div className="mt-1 text-neutral-500">{health.message}</div>
              </>
            ) : (
              "No health check yet."
            )}
          </div>
        </section>
        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <div className="flex items-center justify-between gap-3">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
              <BrainCircuit size={16} aria-hidden="true" />
              Agent Runtime
            </h2>
            <span className="font-mono text-xs text-neutral-500">
              {agentRuntime.runtime_version}
            </span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm text-neutral-700">
            <span>Step limit</span>
            <span className="text-right">{agentRuntime.limits.max_steps ?? 0}</span>
            <span>Replan budget</span>
            <span className="text-right">{agentRuntime.limits.max_replans ?? 0}</span>
            <span>Recovery steps</span>
            <span className="text-right">{agentRuntime.limits.max_recovery_steps ?? 0}</span>
            <span>Checkpoints</span>
            <span className="text-right">
              {agentRuntime.limits.max_approval_checkpoints ?? 0}
            </span>
            <span>Allowed actions</span>
            <span className="text-right">{agentRuntime.allowed_actions.length}</span>
            <span>Memory records</span>
            <span className="text-right">{operationalMemoryRegistry.record_count}</span>
            <span>Memory writes</span>
            <span className="text-right">task-local</span>
          </div>
          <div className="mt-3 divide-y divide-line border-t border-line text-xs">
            {operationalMemoryRegistry.records.map((record) => (
              <div key={record.memory_id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0 truncate text-neutral-700">{record.title}</span>
                <span className="shrink-0 font-mono text-neutral-400">
                  {record.content_hash.slice(0, 8)}
                </span>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <div className="flex items-center justify-between gap-3">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
              <Database size={16} aria-hidden="true" />
              RAG Evidence
            </h2>
            <span className="font-mono text-xs text-neutral-500">
              {ragCorpusRegistry.registry_version}
            </span>
          </div>
          <div className="mt-3 grid gap-3 text-sm text-neutral-700">
            {ragCorpusRegistry.corpora.map((corpus) => (
              <div key={corpus.corpus_id} className="border-b border-line pb-3">
                <div className="font-medium text-ink">{corpus.display_name}</div>
                <div className="mt-1 text-xs text-neutral-500">
                  {corpus.corpus_version} / {corpus.chunk_count} chunks / {corpus.document_count} documents
                </div>
              </div>
            ))}
            <div>
              <div className="text-xs font-semibold uppercase text-neutral-500">Retriever</div>
              <div className="mt-1 font-medium">{ragRetriever.display_name}</div>
              <div className="mt-1 font-mono text-xs text-neutral-500">
                {ragRetriever.retriever_version}
              </div>
            </div>
            {!ragCorpusRegistry.corpora.length ? (
              <div className="text-neutral-500">Corpus registry unavailable.</div>
            ) : null}
          </div>
        </section>
        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <div className="flex items-center justify-between gap-3">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
              <Wrench size={16} aria-hidden="true" />
              Tool Runtime
            </h2>
            <span className="font-mono text-xs text-neutral-500">
              {toolRegistry.registry_version}
            </span>
          </div>
          <div className="mt-3 divide-y divide-line text-sm">
            {toolRegistry.tools.map((tool) => (
              <div key={tool.tool_id} className="flex items-center justify-between gap-3 py-2">
                <span className="font-medium text-neutral-700">{tool.display_name}</span>
                <span className={tool.side_effect_mode === "simulated" ? "text-amber" : "text-neutral-500"}>
                  {tool.side_effect_mode}
                </span>
              </div>
            ))}
            {!toolRegistry.tools.length ? (
              <div className="py-3 text-neutral-500">Registry unavailable.</div>
            ) : null}
          </div>
        </section>
        <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <h2 className="text-sm font-semibold text-ink">Execution Result</h2>
          <div className="mt-3 grid gap-2 text-sm text-neutral-700">
            {result ? (
              <>
                <div>Run: <span className="font-mono">{result.benchmark_run.id.slice(0, 8)}</span></div>
                <div>Status: {result.benchmark_run.status}</div>
                <div>Results: {result.result_count}</div>
                <div>Metrics: {result.metric_count}</div>
                <div>Logs: {result.log_count}</div>
                {result.agent_execution_summary.agent_case_count ? (
                  <>
                    <div className="mt-3 border-t border-line pt-3 font-medium text-ink">
                      Agent execution
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                      <span className="inline-flex items-center gap-1.5">
                        <BrainCircuit size={14} aria-hidden="true" />
                        Successful tasks
                      </span>
                      <span className="text-right">
                        {result.agent_execution_summary.successful_case_count}/
                        {result.agent_execution_summary.agent_case_count}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Workflow size={14} aria-hidden="true" />
                        Successful steps
                      </span>
                      <span className="text-right">
                        {result.agent_execution_summary.successful_step_count}/
                        {result.agent_execution_summary.total_step_count}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <HardDrive size={14} aria-hidden="true" />
                        Memory provenance
                      </span>
                      <span className="text-right">
                        {formatRate(result.agent_execution_summary.memory_provenance_rate)}
                      </span>
                      <span>Policy violations</span>
                      <span className="text-right">
                        {formatRate(result.agent_execution_summary.policy_violation_rate)}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <RotateCcw size={14} aria-hidden="true" />
                        Replan recovery
                      </span>
                      <span className="text-right">
                        {formatRate(result.agent_execution_summary.replan_success_rate)}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck size={14} aria-hidden="true" />
                        Approval compliance
                      </span>
                      <span className="text-right">
                        {formatRate(result.agent_execution_summary.approval_compliance_rate)}
                      </span>
                    </div>
                    <Link
                      href={`/benchmark-executions/${result.benchmark_run.id}`}
                      className="mt-3 inline-flex text-sm font-medium text-teal hover:underline"
                    >
                      Inspect Agent Trace
                    </Link>
                  </>
                ) : null}
                {result.runtime_reliability_summary.trial_count ? (
                  <>
                    <div className="mt-3 border-t border-line pt-3 font-medium text-ink">
                      Runtime reliability
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                      <span className="inline-flex items-center gap-1.5">
                        <Layers3 size={14} aria-hidden="true" />
                        Successful trials
                      </span>
                      <span className="text-right">
                        {result.runtime_reliability_summary.success_count}/
                        {result.runtime_reliability_summary.trial_count}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Timer size={14} aria-hidden="true" />
                        P99 latency
                      </span>
                      <span className="text-right">
                        {formatLatency(
                          result.runtime_reliability_summary.p99_end_to_end_latency_ms
                        )}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Gauge size={14} aria-hidden="true" />
                        Timeout / OOM
                      </span>
                      <span className="text-right">
                        {result.runtime_reliability_summary.timeout_count} /{" "}
                        {result.runtime_reliability_summary.oom_count}
                      </span>
                    </div>
                    <Link
                      href={`/benchmark-executions/${result.benchmark_run.id}`}
                      className="mt-3 inline-flex text-sm font-medium text-teal hover:underline"
                    >
                      Inspect Reliability Trace
                    </Link>
                  </>
                ) : null}
                {result.tool_execution_summary.tool_case_count ? (
                  <>
                    <div className="mt-3 border-t border-line pt-3 font-medium text-ink">
                      Tool execution
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                      <span className="inline-flex items-center gap-1.5">
                        <ListChecks size={14} aria-hidden="true" />
                        Calls
                      </span>
                      <span className="text-right">
                        {result.tool_execution_summary.successful_call_count}/
                        {result.tool_execution_summary.call_count}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <RotateCcw size={14} aria-hidden="true" />
                        Recovered
                      </span>
                      <span className="text-right">
                        {result.tool_execution_summary.recovered_call_count}/
                        {result.tool_execution_summary.retried_call_count}
                      </span>
                      <span>Multi-step cases</span>
                      <span className="text-right">
                        {result.tool_execution_summary.multi_step_case_count}
                      </span>
                    </div>
                    <Link
                      href={`/benchmark-executions/${result.benchmark_run.id}`}
                      className="mt-3 inline-flex text-sm font-medium text-teal hover:underline"
                    >
                      Inspect Tool Trace
                    </Link>
                  </>
                ) : null}
                {result.rag_evaluation_summary.rag_case_count ? (
                  <>
                    <div className="mt-3 border-t border-line pt-3 font-medium text-ink">
                      RAG evaluation
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                      <span className="inline-flex items-center gap-1.5">
                        <SearchCheck size={14} aria-hidden="true" />
                        Retrieval recall
                      </span>
                      <span className="text-right">
                        {formatRate(result.rag_evaluation_summary.average_retrieval_recall)}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Quote size={14} aria-hidden="true" />
                        Citation precision
                      </span>
                      <span className="text-right">
                        {formatRate(result.rag_evaluation_summary.average_citation_precision)}
                      </span>
                      <span>Unsupported claims</span>
                      <span className="text-right">
                        {formatRate(result.rag_evaluation_summary.average_unsupported_claim_rate)}
                      </span>
                    </div>
                    <Link
                      href={`/benchmark-executions/${result.benchmark_run.id}`}
                      className="mt-3 inline-flex text-sm font-medium text-teal hover:underline"
                    >
                      Inspect RAG Trace
                    </Link>
                  </>
                ) : null}
              </>
            ) : (
              "Run evidence has not been generated."
            )}
          </div>
        </section>
      </aside>
    </div>
  );
}

function formatRate(value: number | null): string {
  return value === null ? "N/A" : `${Math.round(value * 100)}%`;
}

function formatLatency(value: number | null): string {
  if (value === null) return "N/A";
  return value >= 1_000 ? `${(value / 1_000).toFixed(2)} s` : `${value.toFixed(0)} ms`;
}
