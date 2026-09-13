"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Fingerprint,
  FlaskConical,
  RefreshCw
} from "lucide-react";
import Link from "next/link";
import type { FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  AgentExecutionJob,
  BenchmarkTask,
  DeploymentConfiguration,
  EvaluationSuite,
  ModelValidationReport,
  ModelValidationStatus,
  ObservedRuntimeConfiguration,
  OperatorIdentity,
  PromptVersion
} from "@/types/api";

type ModelValidationConsoleProps = {
  configurations: DeploymentConfiguration[];
  suites: EvaluationSuite[];
  tasks: BenchmarkTask[];
  prompts: PromptVersion[];
  initialConfigurationId: string;
  initialSuiteId: string;
  initialReport: ModelValidationReport | null;
};

export function ModelValidationConsole({
  configurations,
  suites,
  tasks,
  prompts,
  initialConfigurationId,
  initialSuiteId,
  initialReport
}: ModelValidationConsoleProps) {
  const [configurationId, setConfigurationId] = useState(initialConfigurationId);
  const selectedConfiguration = configurations.find(
    (configuration) => configuration.id === configurationId
  );
  const matchingSuites = useMemo(
    () =>
      suites.filter(
        (suite) =>
          !selectedConfiguration ||
          suite.workload_profile_id === selectedConfiguration.workload_profile_id
      ),
    [selectedConfiguration, suites]
  );
  const [suiteId, setSuiteId] = useState(initialSuiteId);
  const [taskId, setTaskId] = useState(tasks[0]?.id ?? "");
  const matchingPrompts = useMemo(
    () => prompts.filter((prompt) => prompt.benchmark_task_id === taskId),
    [prompts, taskId]
  );
  const [promptId, setPromptId] = useState(
    matchingPrompts[0]?.id ?? prompts[0]?.id ?? ""
  );
  const [adapterName, setAdapterName] = useState<
    "openai_compatible" | "mock"
  >("openai_compatible");
  const [baseUrl, setBaseUrl] = useState(
    "http://host.docker.internal:11434"
  );
  const [modelName, setModelName] = useState("");
  const [maxCases, setMaxCases] = useState("10");
  const [reliabilityMode, setReliabilityMode] = useState(false);
  const [trialsPerCase, setTrialsPerCase] = useState("3");
  const [concurrency, setConcurrency] = useState("2");
  const [useApiKeyEnv, setUseApiKeyEnv] = useState(false);
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [job, setJob] = useState<AgentExecutionJob | null>(null);
  const [report, setReport] = useState<ModelValidationReport | null>(
    initialReport
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<"queue" | "refresh" | "attest" | null>(null);

  useEffect(() => {
    let active = true;
    async function loadIdentity() {
      const response = await browserApiFetch(`${API_BASE_URL}/operator-identity/me`, {
        cache: "no-store"
      }).catch(() => null);
      if (!active || !response?.ok) return;
      setIdentity((await response.json()) as OperatorIdentity);
    }
    void loadIdentity();
    return () => {
      active = false;
    };
  }, []);

  function selectConfiguration(nextConfigurationId: string) {
    setConfigurationId(nextConfigurationId);
    const configuration = configurations.find(
      (item) => item.id === nextConfigurationId
    );
    const nextSuite = suites.find(
      (suite) =>
        !configuration ||
        (suite.workload_profile_id === configuration.workload_profile_id &&
          !suite.is_synthetic)
    ) ?? suites.find(
      (suite) =>
        !configuration ||
        suite.workload_profile_id === configuration.workload_profile_id
    );
    setSuiteId(nextSuite?.id ?? "");
    setReport(null);
  }

  function selectTask(nextTaskId: string) {
    setTaskId(nextTaskId);
    setPromptId(
      prompts.find((prompt) => prompt.benchmark_task_id === nextTaskId)?.id ??
        ""
    );
  }

  async function queueCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("queue");
    setNotice("Queueing validation campaign");
    setJob(null);
    const response = await browserApiFetch(`${API_BASE_URL}/model-validation/campaigns`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        deployment_configuration_id: configurationId,
        evaluation_suite_id: suiteId,
        benchmark_task_id: taskId,
        prompt_version_id: promptId,
        adapter_name: adapterName,
        adapter_config_json:
          adapterName === "openai_compatible"
            ? {
                ...(baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
                ...(modelName.trim() ? { model: modelName.trim() } : {}),
                ...(useApiKeyEnv
                  ? { api_key_env: "OPENAI_COMPATIBLE_API_KEY" }
                  : {})
              }
            : {},
        data_source: adapterName === "mock" ? "synthetic_demo" : "local_authored",
        max_cases: maxCases ? Number(maxCases) : null,
        reliability_mode: reliabilityMode,
        trials_per_case: reliabilityMode ? Number(trialsPerCase) : 1,
        concurrency: reliabilityMode ? Number(concurrency) : 1,
        case_timeout_ms: 120000
      })
    });
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(null);
      return;
    }
    const queued = (await response.json()) as AgentExecutionJob;
    setJob(queued);
    setNotice("Campaign queued");
    setBusy(null);
    void pollJob(queued.id);
  }

  async function pollJob(jobId: string) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await delay(2000);
      const response = await browserApiFetch(`${API_BASE_URL}/agents/jobs/${jobId}`, {
        cache: "no-store"
      }).catch(() => null);
      if (!response?.ok) continue;
      const current = (await response.json()) as AgentExecutionJob;
      setJob(current);
      if (current.status === "completed") {
        const completedReport = current.result_json?.report;
        if (isModelValidationReport(completedReport)) {
          setReport(completedReport);
        }
        setNotice("Validation completed");
        return;
      }
      if (current.status === "failed" || current.status === "cancelled") {
        setNotice(current.last_error ?? `Validation ${current.status}`);
        return;
      }
      setNotice(`Validation ${current.status}`);
    }
    setNotice("Validation is still running; monitor Agent Jobs");
  }

  async function refreshReport() {
    if (!configurationId || !suiteId) return;
    setBusy("refresh");
    setNotice("Refreshing report");
    const params = reportParams(configurationId, suiteId);
    const response = await browserApiFetch(
      `${API_BASE_URL}/model-validation/report?${params.toString()}`,
      { cache: "no-store" }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(null);
      return;
    }
    setReport((await response.json()) as ModelValidationReport);
    setNotice("Report refreshed");
    setBusy(null);
  }

  async function attestRuntime() {
    if (!configurationId || !baseUrl.trim() || !modelName.trim()) return;
    setBusy("attest");
    setNotice("Inspecting runtime manifest");
    const response = await browserApiFetch(
      `${API_BASE_URL}/model-validation/observed-runtime-configurations`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          source_deployment_configuration_id: configurationId,
          base_url: baseUrl.trim(),
          model_name: modelName.trim()
        })
      }
    );
    if (!response.ok) {
      setNotice(await responseError(response));
      setBusy(null);
      return;
    }
    const created = (await response.json()) as ObservedRuntimeConfiguration;
    setNotice(`Verified ${created.manifest.digest_value.slice(0, 19)}`);
    const params = new URLSearchParams({
      deployment_configuration_id: created.deployment_configuration.id,
      evaluation_suite_id: suiteId
    });
    window.location.assign(`/model-validation?${params.toString()}`);
  }

  const canQueue =
    identity?.identity_verified === true &&
    Boolean(configurationId && suiteId && taskId && promptId);

  return (
    <>
      <section className="grid gap-5 rounded-lg border border-line bg-panel p-5 shadow-soft xl:grid-cols-[minmax(0,1fr)_minmax(260px,340px)]">
        <form onSubmit={queueCampaign} className="grid min-w-0 gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-ink">
              <FlaskConical size={18} aria-hidden="true" />
              Validation Campaign
            </h2>
            <div className="inline-flex rounded-md border border-line bg-neutral-50 p-1">
              {(["openai_compatible", "mock"] as const).map((adapter) => (
                <button
                  key={adapter}
                  type="button"
                  onClick={() => setAdapterName(adapter)}
                  aria-pressed={adapterName === adapter}
                  className={`h-8 rounded px-3 text-xs font-medium ${
                    adapterName === adapter
                      ? "bg-white text-ink shadow-sm"
                      : "text-neutral-500"
                  }`}
                >
                  {adapter === "openai_compatible" ? "Local runtime" : "Fixture"}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
              Deployment configuration
              <select
                value={configurationId}
                onChange={(event) => selectConfiguration(event.target.value)}
                className="h-10 w-full min-w-0 rounded-md border border-line bg-white px-3 text-sm"
              >
                {configurations.map((configuration) => (
                  <option key={configuration.id} value={configuration.id}>
                    {configuration.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
              Evaluation suite
              <select
                value={suiteId}
                onChange={(event) => {
                  setSuiteId(event.target.value);
                  setReport(null);
                }}
                className="h-10 w-full min-w-0 rounded-md border border-line bg-white px-3 text-sm"
              >
                {matchingSuites.map((suite) => (
                  <option key={suite.id} value={suite.id}>
                    {suite.name} {suite.version_label}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
              Benchmark task
              <select
                value={taskId}
                onChange={(event) => selectTask(event.target.value)}
                className="h-10 w-full min-w-0 rounded-md border border-line bg-white px-3 text-sm"
              >
                {tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
              Prompt version
              <select
                value={promptId}
                onChange={(event) => setPromptId(event.target.value)}
                className="h-10 w-full min-w-0 rounded-md border border-line bg-white px-3 text-sm"
              >
                {matchingPrompts.map((prompt) => (
                  <option key={prompt.id} value={prompt.id}>
                    {prompt.name} {prompt.version_label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {adapterName === "openai_compatible" ? (
            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
                Runtime URL
                <input
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  className="h-10 w-full min-w-0 rounded-md border border-line bg-white px-3 text-sm"
                />
              </label>
              <label className="grid min-w-0 gap-2 text-sm font-medium text-neutral-700">
                Model name
                <input
                  value={modelName}
                  onChange={(event) => setModelName(event.target.value)}
                  placeholder="first available model"
                  className="h-10 w-full min-w-0 rounded-md border border-line bg-white px-3 text-sm"
                />
              </label>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-3">
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Max cases
              <input
                type="number"
                min={1}
                max={500}
                value={maxCases}
                onChange={(event) => setMaxCases(event.target.value)}
                className="h-10 rounded-md border border-line bg-white px-3 text-sm"
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Trials per case
              <input
                type="number"
                min={1}
                max={20}
                disabled={!reliabilityMode}
                value={trialsPerCase}
                onChange={(event) => setTrialsPerCase(event.target.value)}
                className="h-10 rounded-md border border-line bg-white px-3 text-sm disabled:bg-neutral-100"
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-neutral-700">
              Concurrency
              <input
                type="number"
                min={1}
                max={16}
                disabled={!reliabilityMode}
                value={concurrency}
                onChange={(event) => setConcurrency(event.target.value)}
                className="h-10 rounded-md border border-line bg-white px-3 text-sm disabled:bg-neutral-100"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-5 border-y border-line py-3 text-sm text-neutral-700">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={reliabilityMode}
                onChange={(event) => setReliabilityMode(event.target.checked)}
              />
              Reliability trials
            </label>
            {adapterName === "openai_compatible" ? (
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={useApiKeyEnv}
                  onChange={(event) => setUseApiKeyEnv(event.target.checked)}
                />
                API key environment
              </label>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={!canQueue || busy !== null}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Activity size={16} aria-hidden="true" />
              Queue Campaign
            </button>
            <button
              type="button"
              onClick={() => void refreshReport()}
              disabled={!configurationId || !suiteId || busy !== null}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm font-medium disabled:opacity-40"
            >
              <RefreshCw size={16} aria-hidden="true" />
              Refresh Report
            </button>
            {adapterName === "openai_compatible" ? (
              <button
                type="button"
                onClick={() => void attestRuntime()}
                disabled={
                  !canQueue ||
                  !baseUrl.trim() ||
                  !modelName.trim() ||
                  busy !== null
                }
                className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm font-medium disabled:opacity-40"
              >
                <Fingerprint size={16} aria-hidden="true" />
                Attest Runtime
              </button>
            ) : null}
            {notice ? (
              <span className="text-sm text-neutral-600">{notice}</span>
            ) : null}
          </div>
        </form>

        <aside className="min-w-0 border-t border-line pt-5 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0">
          <h3 className="text-sm font-semibold text-ink">Operator</h3>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge tone={identity?.identity_verified ? "teal" : "amber"}>
              {identity?.identity_verified ? "verified" : "verification required"}
            </Badge>
            <span className="text-sm text-neutral-700">
              {identity?.display_name ?? "Checking identity"}
            </span>
          </div>
          <div className="mt-2 text-xs text-neutral-500">
            {identity?.role ?? "SRE Lead, ML Ops Lead, Release Manager, or Admin"}
          </div>
          <div className="mt-5 border-t border-line pt-4">
            <h3 className="text-sm font-semibold text-ink">Current job</h3>
            {job ? (
              <div className="mt-3 grid gap-2 text-sm text-neutral-700">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs">{job.id.slice(0, 8)}</span>
                  <Badge tone={jobTone(job.status)}>{job.status}</Badge>
                </div>
                <div>Attempt {job.attempt_count}/{job.max_attempts}</div>
                <Link
                  href="/agent-jobs"
                  className="inline-flex items-center gap-1.5 font-medium text-teal"
                >
                  Open Agent Jobs
                  <ExternalLink size={14} aria-hidden="true" />
                </Link>
              </div>
            ) : (
              <div className="mt-3 text-sm text-neutral-500">No queued campaign.</div>
            )}
          </div>
        </aside>
      </section>

      {report ? (
        <ModelValidationReportPanel report={report} />
      ) : (
        <section className="rounded-lg border border-line bg-panel px-5 py-12 text-center text-sm text-neutral-500 shadow-soft">
          No validation report for the selected scope.
        </section>
      )}
    </>
  );
}

function ModelValidationReportPanel({
  report
}: {
  report: ModelValidationReport;
}) {
  const primaryCohort =
    report.cohorts.find((cohort) => cohort.actual_runtime_result_count > 0) ??
    report.cohorts.at(-1);
  const markdownParams = reportParams(
    report.deployment_configuration_id,
    report.evaluation_suite_id
  );
  if (report.focus_benchmark_run_id) {
    markdownParams.set(
      "focus_benchmark_run_id",
      report.focus_benchmark_run_id
    );
  }

  return (
    <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Validation status"
          value={statusLabel(report.status)}
          detail={report.actual_runtime_validated ? "actual runtime evidence" : "fixture or imported evidence"}
          tone={summaryTone(report.status)}
        />
        <SummaryCard
          label="Results"
          value={report.result_count}
          detail={`${report.selected_run_count} completed runs`}
        />
        <SummaryCard
          label="P95 latency"
          value={formatMs(primaryCohort?.p95_end_to_end_latency_ms ?? null)}
          detail={primaryCohort?.data_source ?? "no cohort"}
          tone="amber"
        />
        <SummaryCard
          label="Judge calibration"
          value={report.judge_calibration.status.replaceAll("_", " ")}
          detail={`${report.judge_calibration.candidate_label_count} candidate labels`}
          tone={report.judge_calibration.status === "calibrated" ? "teal" : "violet"}
        />
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-ink">Evidence Cohorts</h2>
            <div className="mt-1 text-xs text-neutral-500">
              {new Intl.DateTimeFormat("en", {
                dateStyle: "medium",
                timeStyle: "short",
                timeZone: "UTC"
              }).format(new Date(report.generated_at))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={summaryTone(report.status)}>{report.status}</Badge>
            <Badge
              tone={
                report.configuration_model_match === true
                  ? "teal"
                  : report.configuration_model_match === false
                    ? "rose"
                    : "neutral"
              }
            >
              {report.configuration_model_match === true
                ? "model matched"
                : report.configuration_model_match === false
                  ? "model mismatch"
                  : "model match unknown"}
            </Badge>
            <Badge
              tone={
                report.artifact_attestation_status === "verified"
                  ? "teal"
                  : report.artifact_attestation_status === "missing"
                    ? "amber"
                    : "rose"
              }
            >
              {report.artifact_attestation_status.replaceAll("_", " ")}
            </Badge>
            <Badge
              tone={
                report.supply_chain_status === "verified"
                  ? "teal"
                  : report.supply_chain_status === "revoked"
                    ? "rose"
                    : "amber"
              }
            >
              supply {report.supply_chain_status}
            </Badge>
            <Badge tone={report.supply_chain_production_eligible ? "teal" : "neutral"}>
              {report.supply_chain_trust_tier.replaceAll("_", " ")}
            </Badge>
            <Badge
              tone={
                report.transparency_status === "verified"
                  ? "teal"
                  : report.transparency_status === "invalidated"
                    ? "rose"
                    : report.transparency_status === "development"
                      ? "neutral"
                      : "amber"
              }
            >
              transparency {report.transparency_status}
            </Badge>
            <Badge
              tone={
                report.production_capture_status === "verified"
                  ? "teal"
                  : report.production_capture_status === "unverified"
                    ? "rose"
                    : "neutral"
              }
            >
              capture {report.production_capture_status.replaceAll("_", " ")}
            </Badge>
            <a
              href={`${API_BASE_URL}/model-validation/report.md?${markdownParams.toString()}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-9 items-center gap-2 rounded-md border border-line px-3 text-sm font-medium"
            >
              Markdown
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          </div>
        </div>
        <div className="border-b border-line bg-neutral-50 px-5 py-3 text-xs text-neutral-600">
          Configured:{" "}
          <span className="font-mono">{report.configured_model_artifact_name}</span>
          {" / "}
          Observed:{" "}
          <span className="font-mono">
            {report.observed_model_names.join(", ") || "unknown"}
          </span>
          <span className="ml-3 font-mono text-neutral-500">
            {report.configured_artifact_digest?.slice(0, 24) ?? "digest unknown"}
          </span>
          <span className="ml-3 text-neutral-500">
            {report.verified_production_run_count} verified production runs /{" "}
            {report.verified_production_result_count} results
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[1120px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Runtime</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Results</th>
                <th className="px-4 py-3">Quality</th>
                <th className="px-4 py-3">JSON</th>
                <th className="px-4 py-3">Tool</th>
                <th className="px-4 py-3">P95 latency</th>
                <th className="px-4 py-3">P50 tok/s</th>
                <th className="px-4 py-3">Error</th>
                <th className="px-4 py-3">Review</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {report.cohorts.map((cohort) => (
                <tr key={cohort.data_source}>
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{cohort.data_source}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {cohort.trust_status}
                    </div>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {cohort.adapter_names.join(", ")}
                  </td>
                  <td className="max-w-56 break-words px-4 py-3 text-xs">
                    {cohort.model_names.join(", ")}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{cohort.result_count}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatRate(cohort.average_quality_score)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatRate(cohort.json_validity_rate)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatRate(cohort.tool_call_validity_rate)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatMs(cohort.p95_end_to_end_latency_ms)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatNumber(cohort.p50_tokens_per_second)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatRate(cohort.error_rate)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatRate(cohort.review_coverage_rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {report.comparisons.length ? (
        <section className="rounded-lg border border-line bg-panel shadow-soft">
          <div className="border-b border-line px-5 py-4">
            <h2 className="text-lg font-semibold text-ink">Source Comparison</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-[760px] text-left text-sm">
              <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
                <tr>
                  <th className="px-4 py-3">Comparison</th>
                  <th className="px-4 py-3">Quality delta</th>
                  <th className="px-4 py-3">P95 latency delta</th>
                  <th className="px-4 py-3">Throughput delta</th>
                  <th className="px-4 py-3">Error delta</th>
                  <th className="px-4 py-3">OOM delta</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {report.comparisons.map((comparison) => (
                  <tr key={`${comparison.baseline_source}-${comparison.candidate_source}`}>
                    <td className="px-4 py-3 font-medium text-ink">
                      {comparison.candidate_source} vs {comparison.baseline_source}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {formatSigned(comparison.quality_delta)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {formatSigned(comparison.p95_latency_delta_ms, " ms")}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {formatSigned(comparison.p50_throughput_delta)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {formatSigned(comparison.error_rate_delta)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {formatSigned(comparison.oom_rate_delta)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <h2 className="text-lg font-semibold text-ink">Recommendations</h2>
          <div className="mt-4 divide-y divide-line">
            {report.recommendations.map((item) => (
              <div key={item} className="flex items-start gap-3 py-3 text-sm leading-6 text-neutral-700">
                <CheckCircle2 size={16} className="mt-1 shrink-0 text-teal" aria-hidden="true" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-line bg-panel p-5 shadow-soft">
          <h2 className="text-lg font-semibold text-ink">Limitations</h2>
          <div className="mt-4 divide-y divide-line">
            {report.limitations.map((item) => (
              <div key={item} className="flex items-start gap-3 py-3 text-sm leading-6 text-neutral-700">
                <AlertTriangle size={16} className="mt-1 shrink-0 text-amber" aria-hidden="true" />
                <span>{item}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 border-t border-line pt-3 font-mono text-xs text-neutral-500">
            report {report.report_hash.slice(0, 16)} / evidence{" "}
            {report.evidence_revision_hash.slice(0, 16)}
          </div>
        </div>
      </section>
    </>
  );
}

function reportParams(configurationId: string, suiteId: string): URLSearchParams {
  return new URLSearchParams({
    deployment_configuration_id: configurationId,
    evaluation_suite_id: suiteId
  });
}

function isModelValidationReport(value: unknown): value is ModelValidationReport {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    typeof (value as { report_hash?: unknown }).report_hash === "string"
  );
}

function statusLabel(status: ModelValidationStatus): string {
  return {
    no_evidence: "No evidence",
    fixture_only: "Fixture only",
    insufficient_real_evidence: "Needs runtime",
    needs_calibration: "Needs calibration",
    needs_attention: "Needs attention",
    validated: "Validated"
  }[status];
}

function summaryTone(
  status: ModelValidationStatus
): "neutral" | "teal" | "amber" | "rose" | "violet" {
  if (status === "validated") return "teal";
  if (status === "needs_calibration") return "violet";
  if (status === "needs_attention") return "amber";
  if (status === "insufficient_real_evidence") return "rose";
  return "neutral";
}

function jobTone(
  status: AgentExecutionJob["status"]
): "neutral" | "teal" | "amber" | "rose" {
  if (status === "completed") return "teal";
  if (status === "failed" || status === "cancelled") return "rose";
  if (status === "running" || status === "leased") return "amber";
  return "neutral";
}

function formatRate(value: number | null): string {
  return value === null ? "n/a" : `${(value * 100).toFixed(1)}%`;
}

function formatMs(value: number | null): string {
  return value === null ? "n/a" : `${Math.round(value)} ms`;
}

function formatNumber(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(2);
}

function formatSigned(value: number | null, suffix = ""): string {
  if (value === null) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(4)}${suffix}`;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function responseError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string | Array<{ msg?: string }> }
    | null;
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.find((item) => item.msg)?.msg ?? "Request failed";
  }
  return `Request failed with status ${response.status}.`;
}
