"use client";

import {
  Ban,
  Check,
  CheckCircle2,
  ClipboardCheck,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import { workflowApi } from "@/lib/requestWorkflowApi";
import type {
  ProposalRecord,
  RequestContract,
  TicketDraft,
} from "@/types/structuredRequests";

const blank: TicketDraft = {
  original_request: "",
  query: "",
  priority: { mode: "unresolved" },
};
type RequestForm = Omit<TicketDraft, "priority"> & {
  priority: TicketDraft["priority"] | { mode: "set"; value: "" };
};
const field =
  "w-full min-w-0 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-ink disabled:bg-neutral-100";
const command =
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-medium hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-40";
const reasons: Record<string, string> = {
  priority_mismatch: "확정한 우선순위와 다름",
  priority_must_be_absent: "생략하기로 한 우선순위가 포함됨",
  query_mismatch: "확정한 query와 다름",
  public_guard_rejected: "Tool 호출 형식 또는 인자가 유효하지 않음",
  priority_unresolved: "우선순위 미확정",
  request_not_confirmed: "요청 미확정",
  confirmation_expired: "확정 유효기간 만료",
  contract_already_executed: "이미 실행한 계약",
  stale_request_contract: "요청 버전이 변경됨. 새로고침이 필요합니다.",
  stale_proposal_check: "이전 버전의 제안",
  confirmed_unused_request_required:
    "미사용 상태의 유효한 확정 계약이 필요합니다.",
  local_proposal_generation_failed: "로컬 모델 응답 실패",
  only_drafts_can_be_confirmed: "저장된 초안만 확정할 수 있습니다.",
  operator_authentication_required: "운영자 로그인이 필요합니다.",
  operator_role_not_allowed: "이 작업에 필요한 운영자 권한이 없습니다.",
};
const eventNames: Record<string, string> = {
  draft_saved: "초안 저장",
  confirmed: "요청 확정",
  revoked: "확정 취소",
  proposal_checked: "제안 검증",
  execution_claimed: "실행 예약",
  simulated_execution: "모의 실행",
};
const date = (value: string) => new Date(value).toLocaleString("ko-KR");

async function api<T>(path = "", method = "GET", body?: unknown): Promise<T> {
  const response = await browserApiFetch(
    `${API_BASE_URL}/structured-requests${path}`,
    {
      method,
      cache: "no-store",
      headers: {
        "content-type": "application/json",
        "x-model-atlas-lab-action": "1",
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    },
  );
  const value = await response.json();
  if (!response.ok) {
    const detail = value.detail;
    const message =
      typeof detail === "string"
        ? (reasons[detail] ?? detail)
        : (detail?.reasons
            ?.map((code: string) => reasons[code] ?? code)
            .join(", ") ?? "요청을 처리하지 못했습니다.");
    throw new Error(message);
  }
  return value as T;
}

export function StructuredRequestLab({
  initialId,
  workflow,
}: {
  initialId?: string;
  workflow?: {
    id: string;
    revision: number;
    originalRequest: string;
    onStateChange: (state: { dirty: boolean; busy: boolean }) => void;
  };
}) {
  const router = useRouter();
  const [records, setRecords] = useState<RequestContract[]>([]);
  const [record, setRecord] = useState<RequestContract | null>(null);
  const [draft, setDraft] = useState<RequestForm>(blank);
  const [acknowledged, setAcknowledged] = useState(false);
  const [proposal, setProposal] = useState("");
  const [selectedCheck, setSelectedCheck] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const dirty =
    JSON.stringify(draft) !==
    JSON.stringify(
      record?.draft ??
        (workflow
          ? { ...blank, original_request: workflow.originalRequest }
          : blank),
    );
  const expired = record?.expires_at
    ? new Date(record.expires_at).getTime() <= now
    : false;
  const usable = Boolean(
    record?.status === "confirmed" &&
    !expired &&
    !record.executed_check_id &&
    !dirty,
  );
  const check =
    record?.checks.find((item) => item.id === selectedCheck) ?? null;
  const validDraft = Boolean(
    draft.query.trim() &&
    draft.original_request.trim() &&
    (draft.priority.mode !== "set" || draft.priority.value),
  );
  const binding = record
    ? {
        expected_revision: record.revision,
        expected_hash: record.contract_hash,
      }
    : null;

  const originalRequest = workflow?.originalRequest;
  const adopt = useCallback(
    (next: RequestContract | null) => {
      setNow(Date.now());
      setRecord(next);
      setDraft(
        next?.draft ??
          (originalRequest
            ? { ...blank, original_request: originalRequest }
            : blank),
      );
      setAcknowledged(false);
      setSelectedCheck(next?.checks[0]?.id ?? null);
      setProposal("");
    },
    [originalRequest],
  );

  const onWorkflowStateChange = workflow?.onStateChange;
  const workflowDirty = dirty || proposal !== "";
  useEffect(() => {
    onWorkflowStateChange?.({ dirty: workflowDirty, busy: Boolean(busy) });
  }, [workflowDirty, busy, onWorkflowStateChange]);

  useEffect(() => {
    let active = true;
    void api<RequestContract[]>()
      .then(async (list) => {
        const next = initialId
          ? await api<RequestContract>(`/${initialId}`)
          : null;
        if (active) {
          setRecords(list);
          adopt(next);
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(null);
      });
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [initialId, adopt]);

  async function run(name: string, action: () => Promise<void>) {
    setBusy(name);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "요청 처리 실패");
    } finally {
      setBusy(null);
      setNow(Date.now());
    }
  }

  async function reload(id = record?.id, focus?: string) {
    const list = await api<RequestContract[]>();
    setRecords(list);
    if (id) {
      const next = await api<RequestContract>(`/${id}`);
      adopt(next);
      if (focus) setSelectedCheck(focus);
    }
  }

  async function save() {
    if (!validDraft) return;
    const next = record
      ? await api<RequestContract>(`/${record.id}`, "PUT", {
          ...binding,
          draft,
        })
      : workflow
        ? await workflowApi<RequestContract>(
            `/attempts/${workflow.id}/request`,
            "POST",
            {
              expected_revision: workflow.revision,
              draft,
            },
          )
        : await api<RequestContract>("", "POST", draft);
    adopt(next);
    await reload(next.id);
    if (!workflow)
      router.replace(`/structured-requests?request_id=${next.id}`, {
        scroll: false,
      });
  }

  async function submitProposal(generate: boolean) {
    if (!record) return;
    const next = await api<ProposalRecord>(
      `/${record.id}/${generate ? "generate" : "checks"}`,
      "POST",
      { ...binding, ...(generate ? {} : { proposal }) },
    );
    await reload(record.id, next.id);
  }

  const state = !record
    ? "새 요청"
    : dirty
      ? "저장되지 않은 변경"
      : record.executed_check_id
        ? "모의 실행 완료"
        : expired && record.status === "confirmed"
          ? "확정 만료"
          : { draft: "초안", confirmed: "확정됨", revoked: "취소됨" }[
              record.status
            ];
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-5">
        <div>
          {workflow ? (
            <h2 className="text-lg font-semibold text-ink">요청 계약</h2>
          ) : (
            <h1 className="text-2xl font-semibold text-ink">요청 계약</h1>
          )}
          <div className="mt-2 flex flex-wrap gap-3 text-xs">
            <span className="font-medium text-teal-800">로컬 모의 실행</span>
            <span className="text-neutral-500">공식 Gate 미반영</span>
            <Link
              href="/structured-requests/validation"
              className="text-teal-800 underline"
            >
              시나리오 검증
            </Link>
          </div>
        </div>
        <div className="flex gap-2">
          {!workflow && (
            <button
              title="새 요청"
              aria-label="새 요청"
              className={command}
              disabled={Boolean(busy) || dirty}
              onClick={() => {
                adopt(null);
                router.replace("/structured-requests", { scroll: false });
              }}
            >
              <Plus size={18} />
            </button>
          )}
          <button
            title="새로고침"
            aria-label="새로고침"
            className={command}
            disabled={Boolean(busy) || dirty}
            onClick={() => void run("reload", () => reload())}
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </header>
      <div className="flex flex-wrap items-end justify-between gap-4">
        {!workflow && (
          <label className="grid w-full max-w-lg gap-1 text-xs font-medium">
            저장된 요청
            <select
              aria-label="저장된 요청"
              className={field}
              value={record?.id ?? ""}
              disabled={Boolean(busy) || dirty}
              onChange={(e) =>
                router.replace(
                  e.target.value
                    ? `/structured-requests?request_id=${e.target.value}`
                    : "/structured-requests",
                  { scroll: false },
                )
              }
            >
              <option value="">새 요청</option>
              {records.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.draft.query} · v{r.revision}
                </option>
              ))}
            </select>
          </label>
        )}
        <div role="status" className="flex items-center gap-2 text-sm">
          <span className="h-2 w-2 rounded-full bg-teal-600" />
          {state}
          {record && (
            <span className="text-neutral-500">v{record.revision}</span>
          )}
          {busy && (
            <LoaderCircle
              size={16}
              className="animate-spin"
              aria-label="처리 중"
            />
          )}
        </div>
      </div>
      {error && (
        <div
          role="alert"
          className="border-l-4 border-red-600 bg-red-50 px-4 py-3 text-sm text-red-900"
        >
          {error}
        </div>
      )}
      <div className="grid min-w-0 gap-6 lg:grid-cols-2">
        <section className="min-w-0 border-t border-line pt-5">
          <h2 className="mb-4 text-base font-semibold">요청 초안</h2>
          <div className="grid gap-4">
            <label className="grid gap-1.5 text-sm">
              원래 요청
              <textarea
                aria-label="원래 요청"
                className={field}
                rows={4}
                maxLength={4000}
                value={draft.original_request}
                readOnly={Boolean(workflow)}
                disabled={Boolean(busy)}
                onChange={(e) => {
                  setAcknowledged(false);
                  setDraft({ ...draft, original_request: e.target.value });
                }}
              />
            </label>
            <label className="grid gap-1.5 text-sm">
              확정할 query
              <textarea
                aria-label="확정할 query"
                className={field}
                rows={2}
                maxLength={1000}
                value={draft.query}
                disabled={Boolean(busy)}
                onChange={(e) => {
                  setAcknowledged(false);
                  setDraft({ ...draft, query: e.target.value });
                }}
              />
            </label>
            <fieldset disabled={Boolean(busy)}>
              <legend className="mb-2 text-sm">우선순위</legend>
              <div className="flex flex-wrap gap-4">
                {(["unresolved", "set", "omit"] as const).map((mode) => (
                  <label
                    key={mode}
                    className="flex min-h-10 items-center gap-2 text-sm"
                  >
                    <input
                      type="radio"
                      name="priority-mode"
                      value={mode}
                      checked={draft.priority.mode === mode}
                      onChange={() => {
                        setAcknowledged(false);
                        setDraft({
                          ...draft,
                          priority:
                            mode === "set" ? { mode, value: "" } : { mode },
                        });
                      }}
                    />
                    {
                      { unresolved: "미확정", set: "값 지정", omit: "생략" }[
                        mode
                      ]
                    }
                  </label>
                ))}
              </div>
            </fieldset>
            {draft.priority.mode === "set" && (
              <label className="grid max-w-xs gap-1.5 text-sm">
                우선순위 값
                <select
                  aria-label="우선순위 값"
                  className={field}
                  value={draft.priority.value}
                  disabled={Boolean(busy)}
                  onChange={(e) => {
                    const value = e.target.value as "low" | "normal" | "high";
                    setDraft({ ...draft, priority: { mode: "set", value } });
                    setAcknowledged(false);
                  }}
                >
                  <option value="" disabled>
                    선택
                  </option>
                  <option value="low">low</option>
                  <option value="normal">normal</option>
                  <option value="high">high</option>
                </select>
              </label>
            )}
            <div className="flex gap-2">
              <button
                className={command}
                disabled={Boolean(busy) || !validDraft}
                onClick={() => void run("save", save)}
              >
                <Save size={16} />
                초안 저장
              </button>
              <button
                title="저장된 값으로 되돌리기"
                aria-label="저장된 값으로 되돌리기"
                className={command}
                disabled={Boolean(busy) || !dirty}
                onClick={() => adopt(record)}
              >
                <RotateCcw size={16} />
              </button>
            </div>
          </div>
        </section>
        <section className="min-w-0 border-t border-line pt-5 lg:border-l lg:pl-6">
          <h2 className="mb-4 text-base font-semibold">확정 계약</h2>
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="text-xs text-neutral-500">Tool</dt>
              <dd className="mt-1 font-mono">create_ticket</dd>
            </div>
            <div>
              <dt className="text-xs text-neutral-500">저장된 query</dt>
              <dd className="mt-1 whitespace-pre-wrap break-words">
                {record?.draft.query || "미저장"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-neutral-500">저장된 우선순위</dt>
              <dd className="mt-1">
                {!record
                  ? "미저장"
                  : record.draft.priority.mode === "set"
                    ? record.draft.priority.value
                    : record.draft.priority.mode === "omit"
                      ? "인자 생략"
                      : "미확정"}
              </dd>
            </div>
            {record && (
              <div>
                <dt className="text-xs text-neutral-500">계약 SHA-256</dt>
                <dd className="mt-1 break-all font-mono text-xs">
                  {record.contract_hash}
                </dd>
              </div>
            )}
          </dl>
          <div className="mt-5 border-t border-line pt-4">
            <label className="flex items-start gap-2 text-sm">
              <input
                aria-label="저장된 query와 우선순위를 확인했습니다"
                type="checkbox"
                className="mt-1"
                checked={acknowledged}
                disabled={
                  Boolean(busy) ||
                  !record ||
                  dirty ||
                  record.status !== "draft" ||
                  record.draft.priority.mode === "unresolved"
                }
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
              저장된 query와 우선순위를 확인했습니다
            </label>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className={command}
                disabled={
                  Boolean(busy) ||
                  !record ||
                  dirty ||
                  !acknowledged ||
                  record.status !== "draft"
                }
                onClick={() =>
                  void run("confirm", async () => {
                    adopt(
                      await api<RequestContract>(
                        `/${record!.id}/confirm`,
                        "POST",
                        { ...binding, acknowledged: true },
                      ),
                    );
                  })
                }
              >
                <ShieldCheck size={16} />
                요청 확정
              </button>
              <button
                className={command}
                disabled={
                  Boolean(busy) ||
                  !record ||
                  record.status !== "confirmed" ||
                  dirty
                }
                onClick={() =>
                  void run("revoke", async () => {
                    adopt(
                      await api<RequestContract>(
                        `/${record!.id}/revoke`,
                        "POST",
                        binding,
                      ),
                    );
                  })
                }
              >
                <Ban size={16} />
                확정 취소
              </button>
            </div>
            {record?.confirmation && (
              <div className="mt-4 space-y-1 text-xs text-neutral-500">
                <p>
                  {record.confirmation.actor.display_name} ·{" "}
                  {record.confirmation.actor.identity_verified
                    ? "인증 운영자 입력"
                    : "로컬 입력 · 신원 미검증"}
                </p>
                <p>유효 기한 {record.expires_at && date(record.expires_at)}</p>
              </div>
            )}
          </div>
        </section>
      </div>
      <section className="min-w-0 border-t border-line pt-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">모델 제안 검증</h2>
          <button
            className={command}
            disabled={Boolean(busy) || !usable}
            onClick={() => void run("generate", () => submitProposal(true))}
          >
            <Play size={16} />
            {busy === "generate" ? "생성 중" : "로컬 모델 제안 생성"}
          </button>
        </div>
        <label className="grid gap-1.5 text-sm">
          제안 JSON
          <textarea
            aria-label="제안 JSON"
            className={`${field} font-mono`}
            rows={3}
            maxLength={16000}
            value={proposal}
            disabled={Boolean(busy)}
            onChange={(e) => setProposal(e.target.value)}
          />
        </label>
        <button
          className={`${command} mt-3`}
          disabled={Boolean(busy) || !usable || !proposal.trim()}
          onClick={() => void run("check", () => submitProposal(false))}
        >
          <ClipboardCheck size={16} />
          제안 검증
        </button>
        <div className="mt-5 min-w-0 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-line text-xs text-neutral-500">
              <tr>
                <th className="py-3">시각</th>
                <th>버전</th>
                <th>출처</th>
                <th>판정</th>
                <th>실행</th>
                <th>상세</th>
              </tr>
            </thead>
            <tbody>
              {record?.checks.map((r) => (
                <tr key={r.id} className="border-b border-line">
                  <td className="py-3">{date(r.created_at)}</td>
                  <td>v{r.revision}</td>
                  <td>
                    {r.source === "local_model_proposal"
                      ? "로컬 모델"
                      : "직접 입력"}
                  </td>
                  <td
                    className={
                      r.verdict.allowed ? "text-teal-800" : "text-red-800"
                    }
                  >
                    {r.verdict.allowed ? "일치" : "차단"}
                  </td>
                  <td>{r.execution ? "완료" : "미실행"}</td>
                  <td>
                    <button
                      aria-label={`검증 상세 ${r.id}`}
                      title="검증 상세"
                      className={command}
                      onClick={() => setSelectedCheck(r.id)}
                    >
                      <Check size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!record?.checks.length && (
            <p className="py-6 text-sm text-neutral-500">검증 기록 없음</p>
          )}
        </div>
        {check && (
          <div className="mt-5 grid min-w-0 gap-4 border-l-4 border-teal-600 bg-neutral-100 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-semibold">
                선택한 제안 · v{check.revision}
              </h3>
              <button
                className={command}
                disabled={
                  Boolean(busy) ||
                  !usable ||
                  check.revision !== record?.revision ||
                  !check.verdict.allowed ||
                  Boolean(check.execution)
                }
                onClick={() =>
                  void run("execute", async () => {
                    await api(
                      `/${record!.id}/checks/${check.id}/execute`,
                      "POST",
                    );
                    await reload(record!.id, check.id);
                  })
                }
              >
                <CheckCircle2 size={16} />
                모의 실행
              </button>
            </div>
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all text-xs">
              {check.proposal}
            </pre>
            {check.verdict.reasons.length > 0 && (
              <ul className="list-inside list-disc text-sm text-red-800">
                {check.verdict.reasons.map((code) => (
                  <li key={code}>{reasons[code] ?? code}</li>
                ))}
              </ul>
            )}
            {check.execution && (
              <div>
                <h4 className="mb-2 text-xs font-medium text-teal-800">
                  모의 실행 결과
                </h4>
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all text-xs">
                  {JSON.stringify(
                    check.execution.trace.steps[0]?.output,
                    null,
                    2,
                  )}
                </pre>
              </div>
            )}
          </div>
        )}
      </section>
      {record && (
        <section className="border-t border-line pt-5">
          <h2 className="mb-3 text-base font-semibold">변경 이력</h2>
          <ol className="grid gap-2 text-xs text-neutral-600">
            {record.events
              .slice()
              .reverse()
              .slice(0, 12)
              .map((e, i) => (
                <li
                  key={`${e.at}-${i}`}
                  className="flex flex-wrap gap-x-4 gap-y-1"
                >
                  <time>{date(e.at)}</time>
                  <span>v{e.revision}</span>
                  <span>{eventNames[e.event] ?? e.event}</span>
                  <span>{e.actor.display_name}</span>
                </li>
              ))}
          </ol>
        </section>
      )}
    </>
  );
}
