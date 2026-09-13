import { AgentJobTable } from "@/components/AgentJobTable";
import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { api } from "@/lib/api";
import { statusTone } from "@/lib/statusPresentation";

export const dynamic = "force-dynamic";

export default async function AgentJobsPage() {
  const [overview, jobs, trafficSources] = await Promise.all([
    api.agentJobOverview(),
    api.agentJobs(),
    api.agentTrafficSources()
  ]);

  return (
    <>
      <section className="rounded-lg border border-line bg-panel p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Agent Jobs</h1>
            <p className="mt-2 text-sm text-neutral-600">
              Durable queue, worker leases, retries, and dead-letter operations.
            </p>
          </div>
          <Badge tone={healthTone(overview.health)}>{overview.health}</Badge>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Queue depth"
          value={overview.queue_depth}
          detail={`${overview.retrying_count} retrying`}
        />
        <SummaryCard
          label="Active leases"
          value={overview.active_lease_count}
          detail={`${overview.expired_lease_count} expired`}
        />
        <SummaryCard
          label="Dead letter"
          value={overview.dead_letter_count}
          detail={`${overview.failed_last_24h} failed in 24h`}
        />
        <SummaryCard
          label="Online workers"
          value={overview.online_worker_count}
          detail={`${overview.completed_last_24h} completed in 24h`}
        />
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">Workers</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[760px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Worker</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Current job</th>
                <th className="px-4 py-3">Processed</th>
                <th className="px-4 py-3">Completed</th>
                <th className="px-4 py-3">Failed</th>
                <th className="px-4 py-3">Last seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {overview.workers.map((worker) => (
                <tr key={worker.worker_id}>
                  <td className="max-w-64 break-all px-4 py-3 font-mono text-xs">
                    {worker.worker_id}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(worker.status)}>
                      {worker.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                    {worker.current_job_id?.slice(0, 8) ?? "idle"}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{worker.processed_count}</td>
                  <td className="px-4 py-3 tabular-nums">{worker.completed_count}</td>
                  <td className="px-4 py-3 tabular-nums">{worker.failed_count}</td>
                  <td className="px-4 py-3 text-xs text-neutral-600">
                    {formatDate(worker.last_seen_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!overview.workers.length ? (
          <div className="px-4 py-10 text-center text-sm text-neutral-500">
            No registered workers.
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">Traffic sources</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-[840px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Health</th>
                <th className="px-4 py-3">Batches</th>
                <th className="px-4 py-3">Replays</th>
                <th className="px-4 py-3">Observed keys</th>
                <th className="px-4 py-3">Configured keys</th>
                <th className="px-4 py-3">Last received</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {trafficSources.map((source) => (
                <tr key={source.source_system}>
                  <td className="px-4 py-3 font-medium text-ink">
                    {source.source_system}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(source.health)}>
                      {source.health}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 tabular-nums">{source.batch_count}</td>
                  <td className="px-4 py-3 tabular-nums">{source.replay_count}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {source.observed_key_ids.join(", ") || "none"}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {source.configured_key_ids.join(", ") || "none"}
                  </td>
                  <td className="px-4 py-3 text-xs text-neutral-600">
                    {source.last_received_at
                      ? formatDate(source.last_received_at)
                      : "not received"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!trafficSources.length ? (
          <div className="px-4 py-10 text-center text-sm text-neutral-500">
            No configured traffic sources.
          </div>
        ) : null}
      </section>

      <AgentJobTable jobs={jobs} />
    </>
  );
}

function healthTone(
  value: "healthy" | "degraded" | "blocked" | "idle"
): "teal" | "amber" | "rose" | "neutral" {
  if (value === "healthy") return "teal";
  if (value === "degraded") return "amber";
  if (value === "blocked") return "rose";
  return "neutral";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}
