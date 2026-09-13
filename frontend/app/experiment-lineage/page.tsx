import Link from "next/link";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import type { ExperimentLineageEvent, ExperimentLineageEventType } from "@/types/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  deployment_configuration_id?: string;
  evaluation_suite_id?: string;
  acceptance_policy_id?: string;
  prompt_version_id?: string;
  event_type?: ExperimentLineageEventType;
}>;

const eventTypes: Array<{ value: ExperimentLineageEventType; label: string }> = [
  { value: "prompt_version_created", label: "Prompt created" },
  { value: "benchmark_run_created", label: "Run created" },
  { value: "benchmark_run_completed", label: "Run completed" },
  { value: "benchmark_run_failed", label: "Run failed" },
  { value: "gate_evaluation_completed", label: "Gate completed" },
  { value: "baseline_promoted", label: "Baseline promoted" },
  { value: "baseline_superseded", label: "Baseline superseded" },
  { value: "release_decision_signed", label: "Release signed" }
];

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function toneForEvent(event: ExperimentLineageEvent): "teal" | "amber" | "rose" | "violet" {
  if (event.status === "failed" || event.event_type === "benchmark_run_failed") return "rose";
  if (event.event_type === "baseline_superseded") return "amber";
  if (event.event_type === "release_decision_signed") return "violet";
  if (event.event_type.includes("baseline")) return "violet";
  return "teal";
}

function eventLabel(value: ExperimentLineageEventType): string {
  return eventTypes.find((item) => item.value === value)?.label ?? value;
}

function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "none";
}

export default async function ExperimentLineagePage({
  searchParams
}: {
  searchParams: SearchParams;
}) {
  const resolvedSearchParams = await searchParams;
  const reportParams = new URLSearchParams({ limit: "200" });
  if (resolvedSearchParams.deployment_configuration_id) {
    reportParams.set(
      "deployment_configuration_id",
      resolvedSearchParams.deployment_configuration_id
    );
  }
  if (resolvedSearchParams.evaluation_suite_id) {
    reportParams.set("evaluation_suite_id", resolvedSearchParams.evaluation_suite_id);
  }
  if (resolvedSearchParams.acceptance_policy_id) {
    reportParams.set("acceptance_policy_id", resolvedSearchParams.acceptance_policy_id);
  }
  if (resolvedSearchParams.prompt_version_id) {
    reportParams.set("prompt_version_id", resolvedSearchParams.prompt_version_id);
  }
  if (resolvedSearchParams.event_type) {
    reportParams.set("event_type", resolvedSearchParams.event_type);
  }

  const [configs, suites, policies, prompts, report] = await Promise.all([
    api.deploymentConfigurations(),
    api.evaluationSuites(),
    api.acceptancePolicies(),
    api.promptVersions(),
    api.experimentLineageReport(reportParams)
  ]);

  const selectedConfig = configs.find(
    (item) => item.id === resolvedSearchParams.deployment_configuration_id
  );
  const selectedSuite = suites.find((item) => item.id === resolvedSearchParams.evaluation_suite_id);
  const selectedPolicy = policies.find(
    (item) => item.id === resolvedSearchParams.acceptance_policy_id
  );
  const selectedPrompt = prompts.find(
    (item) => item.id === resolvedSearchParams.prompt_version_id
  );

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Experiment Lineage</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Trace prompt changes, benchmark runs, gate decisions, baseline promotions, and
              release sign-offs as one experiment timeline.
            </p>
          </div>
          <Badge tone="violet">Append-only events</Badge>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-4 shadow-soft">
        <form className="grid gap-3 xl:grid-cols-6" action="/experiment-lineage">
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Deployment
            <select
              name="deployment_configuration_id"
              defaultValue={resolvedSearchParams.deployment_configuration_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All deployments</option>
              {configs.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Suite
            <select
              name="evaluation_suite_id"
              defaultValue={resolvedSearchParams.evaluation_suite_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All suites</option>
              {suites.map((suite) => (
                <option key={suite.id} value={suite.id}>
                  {suite.name} {suite.version_label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Policy
            <select
              name="acceptance_policy_id"
              defaultValue={resolvedSearchParams.acceptance_policy_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All policies</option>
              {policies.map((policy) => (
                <option key={policy.id} value={policy.id}>
                  {policy.name} {policy.version_label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Prompt
            <select
              name="prompt_version_id"
              defaultValue={resolvedSearchParams.prompt_version_id ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All prompts</option>
              {prompts.map((prompt) => (
                <option key={prompt.id} value={prompt.id}>
                  {prompt.name} {prompt.version_label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 text-sm font-medium text-neutral-700">
            Event
            <select
              name="event_type"
              defaultValue={resolvedSearchParams.event_type ?? ""}
              className="h-10 rounded-md border border-line bg-white px-3 text-sm"
            >
              <option value="">All events</option>
              {eventTypes.map((eventType) => (
                <option key={eventType.value} value={eventType.value}>
                  {eventType.label}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white"
            >
              Filter
            </button>
            <Link
              className="h-10 rounded-md border border-line px-4 py-2 text-sm font-medium"
              href="/experiment-lineage"
            >
              Reset
            </Link>
          </div>
        </form>
        <div className="mt-3 text-xs text-neutral-500">
          Scope: {selectedConfig?.name ?? "all deployments"} - {selectedSuite?.name ?? "all suites"}{" "}
          - {selectedPolicy?.name ?? "all policies"} - {selectedPrompt?.name ?? "all prompts"}
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-5">
        <SummaryCard label="Events" value={report.event_count} detail="visible timeline rows" />
        <SummaryCard
          label="Lineages"
          value={report.lineage_count}
          detail="unique experiment keys"
          tone="violet"
        />
        <SummaryCard
          label="Benchmark events"
          value={report.benchmark_run_event_count}
          detail="run records"
          tone="teal"
        />
        <SummaryCard
          label="Gate events"
          value={report.gate_event_count}
          detail="gate verdicts"
          tone="amber"
        />
        <SummaryCard
          label="Baselines"
          value={report.baseline_event_count}
          detail="promotion records"
          tone="violet"
        />
        <SummaryCard
          label="Sign-offs"
          value={report.release_decision_event_count}
          detail="release decisions"
          tone="violet"
        />
      </div>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3 text-sm font-semibold text-ink">
          Experiment Timeline
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3">Summary</th>
              <th className="px-4 py-3">Scope</th>
              <th className="px-4 py-3">Linked records</th>
            </tr>
          </thead>
          <tbody>
            {report.events.map((event) => (
              <tr key={event.id} className="border-t border-line align-top">
                <td className="px-4 py-3 text-xs text-neutral-600">
                  {formatDate(event.event_time)}
                </td>
                <td className="px-4 py-3">
                  <Badge tone={toneForEvent(event)}>{eventLabel(event.event_type)}</Badge>
                  <div className="mt-2 font-mono text-xs text-neutral-500">
                    {event.primary_entity_type}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{event.summary}</div>
                  <div className="mt-1 text-xs text-neutral-500">{event.data_source}</div>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-500">
                  <div>deployment {shortId(event.deployment_configuration_id)}</div>
                  <div>suite {shortId(event.evaluation_suite_id)}</div>
                  <div>policy {shortId(event.acceptance_policy_id)}</div>
                  <div>prompt {shortId(event.prompt_version_id)}</div>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-500">
                  <div>run {shortId(event.benchmark_run_id)}</div>
                  <div>
                    gate{" "}
                    {event.gate_evaluation_id ? (
                      <Link
                        className="font-medium text-teal"
                        href={`/deployment-gates/${event.gate_evaluation_id}`}
                      >
                        {shortId(event.gate_evaluation_id)}
                      </Link>
                    ) : (
                      "none"
                    )}
                  </div>
                  <div>baseline {shortId(event.deployment_baseline_id)}</div>
                  <div>
                    decision{" "}
                    {event.release_decision_id && event.gate_evaluation_id ? (
                      <Link
                        className="font-medium text-teal"
                        href={`/release-decisions/${event.release_decision_id}`}
                      >
                        {shortId(event.release_decision_id)}
                      </Link>
                    ) : (
                      shortId(event.release_decision_id)
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {!report.events.length ? (
              <tr className="border-t border-line">
                <td className="px-4 py-6 text-sm text-neutral-600" colSpan={5}>
                  No lineage events are available for this scope.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </>
  );
}
