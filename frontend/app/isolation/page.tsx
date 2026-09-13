import { Badge } from "@/components/Badge";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function IsolationPoliciesPage() {
  const registry = await api.isolationPolicies();

  return (
    <>
      <section className="border-b border-line pb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">Isolation Policies</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-600">
              Network, credential, filesystem, subprocess, and tool boundaries applied before
              Tool and RAG execution.
            </p>
          </div>
          <Badge tone="teal">{registry.policy_count} policies</Badge>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
              <tr>
                <th className="px-4 py-3">Policy</th>
                <th className="px-4 py-3">Workloads</th>
                <th className="px-4 py-3">Network</th>
                <th className="px-4 py-3">Credentials</th>
                <th className="px-4 py-3">Filesystem</th>
                <th className="px-4 py-3">Limits</th>
              </tr>
            </thead>
            <tbody>
              {registry.policies.map((policy) => (
                <tr key={policy.policy_id} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{policy.display_name}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">
                      {policy.policy_id}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {policy.workload_kinds.map((kind) => (
                        <Badge key={kind} tone="violet">{kind}</Badge>
                      ))}
                    </div>
                    <div className="mt-2 text-xs text-neutral-500">
                      {policy.allowed_tools.length} tools
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium">{policy.network_mode}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {policy.allowed_network_hosts.join(", ") || "No hosts"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium">{policy.credential_mode}</div>
                    <div className="mt-1 break-all font-mono text-xs text-neutral-500">
                      {policy.allowed_secret_envs.join(", ") || "No secret envs"}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium">{policy.filesystem_mode}</div>
                    <div className="mt-1 font-mono text-xs text-neutral-500">
                      write {policy.writable_paths.join(", ") || "none"}
                    </div>
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    <div>{policy.max_execution_seconds}s</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {(policy.max_output_bytes / 1_048_576).toFixed(1)} MiB output
                    </div>
                    <div className="mt-1 text-xs text-neutral-500">
                      subprocess {policy.subprocess_allowed ? "allowed" : "blocked"}
                    </div>
                  </td>
                </tr>
              ))}
              {!registry.policies.length ? (
                <tr className="border-t border-line">
                  <td className="px-4 py-6 text-neutral-600" colSpan={6}>
                    No isolation policies are available.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
