"use client";

import {
  Ban,
  History,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  Trash2,
  UsersRound,
  X
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/Badge";
import { SummaryCard } from "@/components/SummaryCard";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type {
  BrowserSession,
  BrowserSessionBulkAction,
  BrowserSessionEvent,
  BrowserSessionOverview,
  BrowserSessionStatus,
  OperatorIdentity
} from "@/types/api";

type ConsoleTab = "sessions" | "events";
type SessionAction =
  | { kind: "session"; session: BrowserSession }
  | { kind: "subject"; session: BrowserSession }
  | { kind: "provider"; session: BrowserSession }
  | { kind: "cleanup" };

export function SessionAdministrationConsole() {
  const [identity, setIdentity] = useState<OperatorIdentity | null>(null);
  const [overview, setOverview] = useState<BrowserSessionOverview | null>(null);
  const [sessions, setSessions] = useState<BrowserSession[]>([]);
  const [events, setEvents] = useState<BrowserSessionEvent[]>([]);
  const [tab, setTab] = useState<ConsoleTab>("sessions");
  const [statusFilter, setStatusFilter] = useState<BrowserSessionStatus | "">("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [appliedSubjectFilter, setAppliedSubjectFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [action, setAction] = useState<SessionAction | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const query = new URLSearchParams({ limit: "200" });
    if (statusFilter) query.set("status", statusFilter);
    if (appliedSubjectFilter) query.set("subject_id", appliedSubjectFilter);
    try {
      const [identityResponse, overviewResponse, sessionsResponse, eventsResponse] =
        await Promise.all([
          browserApiFetch(`${API_BASE_URL}/operator-identity/me`, {
            cache: "no-store"
          }),
          browserApiFetch(`${API_BASE_URL}/operator-identity/sessions/overview`, {
            cache: "no-store"
          }),
          browserApiFetch(
            `${API_BASE_URL}/operator-identity/sessions?${query.toString()}`,
            { cache: "no-store" }
          ),
          browserApiFetch(
            `${API_BASE_URL}/operator-identity/session-events?limit=200`,
            { cache: "no-store" }
          )
        ]);
      if (!identityResponse.ok) throw new Error("Operator identity is unavailable.");
      const nextIdentity = (await identityResponse.json()) as OperatorIdentity;
      setIdentity(nextIdentity);
      if (overviewResponse.status === 403) {
        setOverview(null);
        setSessions([]);
        setEvents([]);
        setError("A verified browser session auditor role is required.");
        return;
      }
      if (!overviewResponse.ok || !sessionsResponse.ok || !eventsResponse.ok) {
        throw new Error("Browser session administration data is unavailable.");
      }
      setOverview((await overviewResponse.json()) as BrowserSessionOverview);
      setSessions((await sessionsResponse.json()) as BrowserSession[]);
      setEvents((await eventsResponse.json()) as BrowserSessionEvent[]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Browser session data is unavailable.");
    } finally {
      setLoading(false);
    }
  }, [appliedSubjectFilter, statusFilter]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedSubjectFilter(subjectFilter.trim());
  }

  function openAction(nextAction: SessionAction) {
    setAction(nextAction);
    setReason(defaultReason(nextAction));
    setNotice(null);
  }

  async function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action || reason.trim().length < 8) return;
    setSubmitting(true);
    setError(null);
    try {
      const target = actionTarget(action);
      const response = await browserApiFetch(`${API_BASE_URL}${target}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() })
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: string }
          | null;
        throw new Error(payload?.detail ?? "Session action was rejected.");
      }
      if (action.kind === "cleanup") {
        const job = (await response.json()) as { id: string };
        setNotice(`Cleanup job ${job.id.slice(0, 8)} was queued.`);
      } else {
        const result = (await response.json()) as BrowserSessionBulkAction;
        setNotice(
          `${result.revoked_count} session${result.revoked_count === 1 ? "" : "s"} revoked.`
        );
      }
      setAction(null);
      setReason("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Session action failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const canAdminister = Boolean(overview?.permissions.can_administer);

  if (loading && !overview && !error) {
    return (
      <div className="flex min-h-48 items-center justify-center text-sm text-neutral-500">
        <LoaderCircle className="mr-2 animate-spin" size={17} aria-hidden="true" />
        Loading browser sessions
      </div>
    );
  }

  if (!overview) {
    return (
      <section className="border-y border-line py-8">
        <div className="flex items-start gap-3">
          <ShieldAlert className="mt-0.5 text-amber-600" size={20} aria-hidden="true" />
          <div>
            <div className="font-medium text-ink">Session audit access denied</div>
            <div className="mt-1 text-sm text-neutral-600">
              {error ?? "A verified browser session auditor role is required."}
            </div>
            <div className="mt-2 text-xs text-neutral-500">
              Current role: {identity?.role ?? "unverified"}
            </div>
          </div>
        </div>
      </section>
    );
  }

  return (
    <>
      <section
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
        aria-label="Browser session summary"
      >
        <SummaryCard label="Active" value={overview.active_count} detail="valid sessions" tone="teal" />
        <SummaryCard
          label="Expired"
          value={overview.expired_count}
          detail="retained for audit"
          tone={overview.expired_count ? "amber" : "teal"}
        />
        <SummaryCard
          label="Revoked"
          value={overview.revoked_count}
          detail="server-side blocks"
          tone="violet"
        />
        <SummaryCard
          label="Retention due"
          value={overview.retention_due_count}
          detail={`${overview.policy.retention_days}-day policy`}
          tone={overview.retention_due_count ? "rose" : "teal"}
        />
        <SummaryCard
          label="Audit events"
          value={overview.audit_event_count}
          detail="append-only lineage"
          tone="violet"
        />
      </section>

      <section className="border-y border-line py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-600">
            <Badge tone={overview.health === "healthy" ? "teal" : "amber"}>
              {overview.health}
            </Badge>
            <span>{overview.policy.retention_days}-day retention</span>
            <span>{overview.policy.cleanup_batch_size} rows per cleanup</span>
            <span>
              Last cleanup:{" "}
              {overview.last_cleanup_completed_at
                ? formatDate(overview.last_cleanup_completed_at)
                : "not completed"}
            </span>
          </div>
          <button
            type="button"
            onClick={() => openAction({ kind: "cleanup" })}
            disabled={!canAdminister || submitting}
            title={
              canAdminister
                ? "Queue retention cleanup"
                : "Admin or SRE Lead role required"
            }
            className="inline-flex h-9 items-center gap-2 rounded-md border border-line px-3 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 size={15} aria-hidden="true" />
            Queue cleanup
          </button>
        </div>
      </section>

      {error || notice ? (
        <div
          role="status"
          className={`border-l-2 px-3 py-2 text-sm ${
            error
              ? "border-rose-500 bg-rose-50 text-rose-800"
              : "border-teal-500 bg-teal-50 text-teal-800"
          }`}
        >
          {error ?? notice}
        </div>
      ) : null}

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div className="inline-flex rounded-md border border-line bg-neutral-50 p-1">
            <button
              type="button"
              onClick={() => setTab("sessions")}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                tab === "sessions" ? "bg-white text-ink shadow-sm" : "text-neutral-600"
              }`}
            >
              <KeyRound size={14} aria-hidden="true" />
              Sessions
            </button>
            <button
              type="button"
              onClick={() => setTab("events")}
              className={`inline-flex h-8 items-center gap-2 rounded px-3 text-xs font-medium ${
                tab === "events" ? "bg-white text-ink shadow-sm" : "text-neutral-600"
              }`}
            >
              <History size={14} aria-hidden="true" />
              Audit events
            </button>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            title="Refresh session data"
            className="grid h-9 w-9 place-items-center rounded-md border border-line text-neutral-600 hover:bg-neutral-50 disabled:opacity-50"
          >
            <RefreshCw
              className={loading ? "animate-spin" : ""}
              size={15}
              aria-hidden="true"
            />
          </button>
        </div>

        {tab === "sessions" ? (
          <>
            <form
              onSubmit={applyFilters}
              className="mb-3 grid gap-3 border-y border-line py-3 sm:grid-cols-[160px_minmax(220px,1fr)_auto]"
            >
              <label className="grid gap-1 text-xs font-medium text-neutral-600">
                Status
                <select
                  value={statusFilter}
                  onChange={(event) =>
                    setStatusFilter(event.target.value as BrowserSessionStatus | "")
                  }
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm text-ink"
                >
                  <option value="">All statuses</option>
                  <option value="active">Active</option>
                  <option value="expired">Expired</option>
                  <option value="revoked">Revoked</option>
                </select>
              </label>
              <label className="grid gap-1 text-xs font-medium text-neutral-600">
                Subject ID
                <input
                  value={subjectFilter}
                  onChange={(event) => setSubjectFilter(event.target.value)}
                  maxLength={240}
                  placeholder="Exact subject ID"
                  className="h-10 min-w-0 rounded-md border border-line px-3 text-sm text-ink"
                />
              </label>
              <button
                type="submit"
                className="h-10 self-end rounded-md bg-ink px-4 text-sm font-medium text-white hover:bg-neutral-800"
              >
                Apply
              </button>
            </form>
            <SessionTable
              sessions={sessions}
              canAdminister={canAdminister}
              onAction={openAction}
            />
          </>
        ) : (
          <EventTable events={events} />
        )}
      </section>

      {action ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/35 px-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !submitting) setAction(null);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="session-action-title"
            className="w-full max-w-lg rounded-lg border border-line bg-white shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 id="session-action-title" className="text-sm font-semibold text-ink">
                {actionTitle(action)}
              </h2>
              <button
                type="button"
                onClick={() => setAction(null)}
                disabled={submitting}
                title="Close"
                className="grid h-8 w-8 place-items-center rounded-md text-neutral-500 hover:bg-neutral-100"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
            <form onSubmit={submitAction} className="grid gap-4 p-4">
              <ActionScope action={action} overview={overview} />
              <label className="grid gap-1 text-xs font-medium text-neutral-600">
                Audit reason
                <textarea
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  minLength={8}
                  maxLength={160}
                  required
                  rows={3}
                  className="resize-none rounded-md border border-line px-3 py-2 text-sm text-ink"
                />
              </label>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setAction(null)}
                  disabled={submitting}
                  className="h-9 rounded-md border border-line px-3 text-xs font-medium text-neutral-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || reason.trim().length < 8}
                  className="inline-flex h-9 items-center gap-2 rounded-md bg-rose-700 px-3 text-xs font-medium text-white hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {submitting ? (
                    <LoaderCircle className="animate-spin" size={14} aria-hidden="true" />
                  ) : action.kind === "cleanup" ? (
                    <Trash2 size={14} aria-hidden="true" />
                  ) : (
                    <Ban size={14} aria-hidden="true" />
                  )}
                  Confirm
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}

function SessionTable({
  sessions,
  canAdminister,
  onAction
}: {
  sessions: BrowserSession[];
  canAdminister: boolean;
  onAction: (action: SessionAction) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1040px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Session</th>
              <th className="px-4 py-3">Subject</th>
              <th className="px-4 py-3">Provider</th>
              <th className="px-4 py-3">Last seen</th>
              <th className="px-4 py-3">Token</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => (
              <tr key={session.id} className="border-t border-line align-top">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-ink">
                      {session.session_fingerprint}
                    </span>
                    {session.current_session ? <Badge tone="violet">current</Badge> : null}
                  </div>
                  <div className="mt-1">
                    <SessionStatusBadge status={session.status} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{session.display_name}</div>
                  <div className="mt-1 max-w-56 truncate font-mono text-xs text-neutral-500">
                    {session.subject_id}
                  </div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {session.role ?? "No role"}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-52 truncate text-xs text-neutral-600">
                    {shortProvider(session.identity_provider)}
                  </div>
                  <div className="mt-1 font-mono text-xs text-neutral-500">
                    SID {shortHash(session.provider_session_hash)}
                  </div>
                  <div className="mt-1 font-mono text-xs text-neutral-400">
                    Client {shortHash(session.client_fingerprint)}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-600">
                  <div>{formatDate(session.last_seen_at)}</div>
                  <div className="mt-1 text-neutral-400">
                    Expires {formatDate(session.expires_at)}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge
                    tone={
                      session.provider_token_state === "retained"
                        ? "amber"
                        : session.provider_token_state === "purged"
                          ? "teal"
                          : "neutral"
                    }
                  >
                    {session.provider_token_state.replace("_", " ")}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-1">
                    <ActionIconButton
                      title="Revoke this session"
                      disabled={
                        !canAdminister ||
                        session.current_session ||
                        session.status !== "active"
                      }
                      onClick={() => onAction({ kind: "session", session })}
                    >
                      <Ban size={15} aria-hidden="true" />
                    </ActionIconButton>
                    <ActionIconButton
                      title="Revoke active sessions for this subject"
                      disabled={!canAdminister}
                      onClick={() => onAction({ kind: "subject", session })}
                    >
                      <UsersRound size={15} aria-hidden="true" />
                    </ActionIconButton>
                    <ActionIconButton
                      title="Revoke active sessions for this provider SID"
                      disabled={!canAdminister || !session.provider_session_hash}
                      onClick={() => onAction({ kind: "provider", session })}
                    >
                      <KeyRound size={15} aria-hidden="true" />
                    </ActionIconButton>
                  </div>
                </td>
              </tr>
            ))}
            {!sessions.length ? (
              <tr className="border-t border-line">
                <td colSpan={6} className="px-4 py-8 text-center text-neutral-500">
                  No browser sessions match the current filter.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EventTable({ events }: { events: BrowserSessionEvent[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-soft">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[920px] text-left text-sm">
          <thead className="bg-neutral-50 text-xs uppercase text-neutral-500">
            <tr>
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3">Session</th>
              <th className="px-4 py-3">Subject</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Hash chain</th>
              <th className="px-4 py-3">Occurred</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id} className="border-t border-line align-top">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">
                    {event.event_type.replaceAll("_", " ")}
                  </div>
                  <div className="mt-1 max-w-56 text-xs text-neutral-500">
                    {event.reason ?? "No reason recorded"}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-600">
                  {event.session_fingerprint}
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-52 truncate font-mono text-xs text-neutral-600">
                    {event.subject_id}
                  </div>
                  <div className="mt-1 font-mono text-xs text-neutral-400">
                    SID {shortHash(event.provider_session_hash)}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-600">
                  <div>{stringValue(event.actor_identity_json.display_name)}</div>
                  <div className="mt-1 text-neutral-400">
                    {stringValue(event.actor_identity_json.role)}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-500">
                  <div>{event.event_hash.slice(0, 12)}</div>
                  <div className="mt-1 text-neutral-400">
                    prev {event.previous_event_hash?.slice(0, 12) ?? "root"}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-neutral-600">
                  {formatDate(event.occurred_at)}
                </td>
              </tr>
            ))}
            {!events.length ? (
              <tr className="border-t border-line">
                <td colSpan={6} className="px-4 py-8 text-center text-neutral-500">
                  No browser session audit events are recorded.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ActionIconButton({
  title,
  disabled,
  onClick,
  children
}: {
  title: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className="grid h-8 w-8 place-items-center rounded-md border border-line text-neutral-600 hover:border-neutral-300 hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-35"
    >
      {children}
    </button>
  );
}

function ActionScope({
  action,
  overview
}: {
  action: SessionAction;
  overview: BrowserSessionOverview;
}) {
  if (action.kind === "cleanup") {
    return (
      <div className="border-l-2 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        Delete inactive sessions older than {overview.policy.retention_days} days and purge token
        material from inactive sessions.
      </div>
    );
  }
  const scope =
    action.kind === "session"
      ? `Session ${action.session.session_fingerprint}`
      : action.kind === "subject"
        ? `Subject ${action.session.subject_id}`
        : `Provider SID ${shortHash(action.session.provider_session_hash)}`;
  return (
    <div className="border-l-2 border-rose-500 bg-rose-50 px-3 py-2 text-sm text-rose-900">
      {scope}. The current browser session is preserved for bulk actions.
    </div>
  );
}

function SessionStatusBadge({ status }: { status: BrowserSessionStatus }) {
  return (
    <Badge tone={status === "active" ? "teal" : status === "expired" ? "amber" : "rose"}>
      {status}
    </Badge>
  );
}

function actionTarget(action: SessionAction): string {
  if (action.kind === "cleanup") return "/operator-identity/sessions/cleanup";
  if (action.kind === "session") {
    return `/operator-identity/sessions/${action.session.id}/revoke`;
  }
  if (action.kind === "subject") {
    return `/operator-identity/subjects/${encodeURIComponent(action.session.subject_id)}/sessions/revoke`;
  }
  return `/operator-identity/provider-sessions/${action.session.provider_session_hash}/revoke`;
}

function actionTitle(action: SessionAction): string {
  if (action.kind === "cleanup") return "Queue retention cleanup";
  if (action.kind === "session") return "Revoke browser session";
  if (action.kind === "subject") return "Revoke subject sessions";
  return "Revoke provider sessions";
}

function defaultReason(action: SessionAction): string {
  if (action.kind === "cleanup") return "Operator requested browser session retention cleanup";
  if (action.kind === "session") return "Administrator revoked browser session";
  if (action.kind === "subject") return "Administrator revoked subject browser sessions";
  return "Administrator revoked provider browser sessions";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function shortHash(value: string | null): string {
  return value ? value.slice(0, 12) : "not recorded";
}

function shortProvider(value: string): string {
  try {
    return new URL(value).host;
  } catch {
    return value;
  }
}

function stringValue(value: unknown): string {
  return typeof value === "string" && value ? value : "not recorded";
}
