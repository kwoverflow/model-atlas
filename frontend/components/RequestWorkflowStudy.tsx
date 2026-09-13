"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  Download,
  HelpCircle,
  LoaderCircle,
  Play,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StructuredRequestLab } from "@/components/StructuredRequestLab";
import { RequestQueryDiff } from "@/components/RequestQueryDiff";
import {
  downloadScenarioJson,
  scenarioButton as button,
  scenarioField as field,
} from "@/lib/requestScenarioApi";
import { workflowApi } from "@/lib/requestWorkflowApi";
import type {
  WorkflowAttempt,
  WorkflowFeedback,
  WorkflowSource,
  WorkflowSummary,
  WorkflowTask,
} from "@/types/requestWorkflows";

const sourceName = {
  participant_self_report: "참여자 자가 보고",
  automated_qa: "자동 QA",
};
const assistanceName: Record<string, string> = {
  none_reported: "도움 없음 · 자가 보고",
  received: "도움 받음",
  not_reported: "미보고",
  not_applicable: "해당 없음",
  pending: "종료 전",
};
const assessmentName = {
  matches_task: "과제 기준 일치",
  does_not_match_task: "과제 기준 불일치",
  abandoned: "중단",
};
const mismatchName: Record<string, string> = {
  original_request: "원래 요청 변경",
  query: "query 불일치",
  priority: "우선순위 불일치",
  decision: "종료 결정 불일치",
  successful_current_execution: "현재 버전의 성공한 모의 실행 없음",
  clarification_without_execution: "추가 확인 요청 또는 실행 보류 불일치",
  execution_arguments: "과제 기준과 다른 인자로 실행한 기록 있음",
};
const date = (value: string) => new Date(value).toLocaleString("ko-KR");

export function RequestWorkflowStudy({ initialId }: { initialId?: string }) {
  const router = useRouter();
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [attempts, setAttempts] = useState<WorkflowAttempt[]>([]);
  const [summary, setSummary] = useState<WorkflowSummary>({ groups: [] });
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState<WorkflowAttempt | null>(null);
  const [source, setSource] = useState<WorkflowSource>(
    "participant_self_report",
  );
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [labState, setLabState] = useState({ dirty: false, busy: true });
  const [prepared, setPrepared] = useState<WorkflowAttempt | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [disposition, setDisposition] = useState<
    "finished" | "clarification_requested" | "abandoned"
  >("finished");
  const [feedback, setFeedback] = useState<WorkflowFeedback>({
    assistance: "not_reported",
    difficulty: null,
    note: "",
  });

  const onLabStateChange = useCallback(
    (state: { dirty: boolean; busy: boolean }) => {
      setLabState(state);
      if (state.dirty || state.busy) {
        setPrepared(null);
        setAcknowledged(false);
      }
    },
    [],
  );

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        if (initialId) {
          const next = await workflowApi<WorkflowAttempt>(
            `/attempts/${initialId}`,
          );
          if (active) {
            setAttempt(next);
            setFeedback(
              next.result?.feedback ?? {
                assistance:
                  next.source === "automated_qa"
                    ? "not_applicable"
                    : "not_reported",
                difficulty: null,
                note: "",
              },
            );
          }
        } else {
          const catalog = await workflowApi<{ tasks: WorkflowTask[] }>(
            "/catalog",
          );
          const list = await workflowApi<WorkflowAttempt[]>(
            `/attempts?limit=20&offset=${offset}`,
          );
          const totals = await workflowApi<WorkflowSummary>("/summary");
          if (active) {
            setTasks(catalog.tasks);
            setAttempts(list);
            setSummary(totals);
          }
        }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "불러오기 실패");
      } finally {
        if (active) setBusy(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [initialId, offset]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : "요청 처리 실패");
    } finally {
      setBusy(false);
    }
  }

  function changeFeedback(next: WorkflowFeedback) {
    setFeedback(next);
    setAcknowledged(false);
  }

  const blocked = busy || labState.busy || labState.dirty;
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-5">
        <div>
          <h1 className="text-2xl font-semibold">
            전체 흐름 검증{attempt ? ` · ${attempt.task.id}` : ""}
          </h1>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500">
            <span>로컬 모의 실행</span>
            <span>공식 Gate 미반영</span>
            <span>신원·독립성 미검증</span>
            {attempt && (
              <span className="font-medium text-teal-800">
                {sourceName[attempt.source]}
              </span>
            )}
          </div>
        </div>
        {initialId ? (
          <button
            className={button}
            disabled={
              busy || (!attempt?.ended_at && (labState.dirty || labState.busy))
            }
            onClick={() => router.push("/structured-requests/workflow")}
          >
            <ArrowLeft size={16} />
            과제 목록
          </button>
        ) : (
          <Link
            href="/structured-requests/validation"
            className="inline-flex items-center gap-2 text-sm underline"
          >
            <ArrowLeft size={16} />
            시나리오 검증
          </Link>
        )}
      </header>
      {error && (
        <p
          role="alert"
          className="border-l-4 border-red-600 bg-red-50 p-4 text-sm text-red-900"
        >
          {error}
        </p>
      )}
      {busy && (
        <div role="status" className="flex items-center gap-2 text-sm">
          <LoaderCircle size={16} className="animate-spin" />
          처리 중
        </div>
      )}
      {!initialId && (
        <>
          <section className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 className="text-base font-semibold">과제 10개</h2>
              <label className="grid w-full max-w-xs gap-1 text-sm">
                기록 출처
                <select
                  aria-label="기록 출처"
                  className={field}
                  value={source}
                  disabled={busy}
                  onChange={(e) => setSource(e.target.value as WorkflowSource)}
                >
                  <option value="participant_self_report">
                    참여자 자가 보고
                  </option>
                  <option value="automated_qa">자동 QA</option>
                </select>
              </label>
            </div>
            <ol className="divide-y divide-line border-y border-line">
              {tasks.map((task) => (
                <li
                  key={task.id}
                  className="grid min-w-0 gap-3 py-4 sm:grid-cols-[4rem_minmax(0,1fr)_auto] sm:items-start"
                >
                  <span className="font-mono text-xs text-neutral-500">
                    {task.id}
                  </span>
                  <p className="whitespace-pre-wrap break-words text-sm leading-6">
                    {task.request}
                  </p>
                  <button
                    aria-label={`${task.id} 시작`}
                    className={`${button} justify-self-end`}
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        const next = await workflowApi<WorkflowAttempt>(
                          "/attempts",
                          "POST",
                          { task_id: task.id, source },
                        );
                        router.push(
                          `/structured-requests/workflow?attempt_id=${next.id}`,
                        );
                      })
                    }
                  >
                    <Play size={16} />
                    시작
                  </button>
                </li>
              ))}
            </ol>
          </section>
          <section className="min-w-0 space-y-3 border-t border-line pt-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold">전체 시도 집계</h2>
              <button
                title="집계 JSON 다운로드"
                aria-label="집계 JSON 다운로드"
                className={button}
                onClick={() =>
                  downloadScenarioJson(summary, "request-workflow-summary.json")
                }
              >
                <Download size={16} />
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-line text-xs text-neutral-500">
                  <tr>
                    {[
                      "출처",
                      "도움 여부",
                      "전체",
                      "진행 중",
                      "일치",
                      "불일치",
                      "중단",
                      "과제 팩",
                    ].map((t) => (
                      <th key={t} className="py-3 pr-3">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {summary.groups.map((g) => (
                    <tr
                      key={`${g.pack_hash}-${g.source}-${g.assistance}`}
                      className="border-b border-line"
                    >
                      <td className="py-3 pr-3">{sourceName[g.source]}</td>
                      <td>{assistanceName[g.assistance]}</td>
                      {[
                        g.total,
                        g.open,
                        g.matches_task,
                        g.does_not_match_task,
                        g.abandoned,
                      ].map((v, i) => (
                        <td key={i}>{v}</td>
                      ))}
                      <td title={g.pack_hash} className="font-mono text-xs">
                        {g.pack_hash.slice(0, 8)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!summary.groups.length && (
              <p className="text-sm text-neutral-500">수행 기록 없음</p>
            )}
          </section>
          <section className="min-w-0 space-y-3 border-t border-line pt-5">
            <h2 className="text-base font-semibold">수행 기록</h2>
            <ul className="divide-y divide-line">
              {attempts.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
                >
                  <div>
                    <span className="font-medium">{item.task.id}</span> ·{" "}
                    {sourceName[item.source]} ·{" "}
                    {item.result
                      ? assessmentName[item.result.assessment]
                      : "진행 중"}
                    <time className="mt-1 block text-xs text-neutral-500">
                      {date(item.started_at)}
                    </time>
                  </div>
                  <Link
                    aria-label={`${item.id} 수행 기록 열기`}
                    href={`/structured-requests/workflow?attempt_id=${item.id}`}
                    className={button}
                  >
                    <ArrowRight size={16} />
                  </Link>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-end gap-3">
              <button
                title="이전 기록"
                aria-label="이전 기록"
                className={button}
                disabled={busy || offset === 0}
                onClick={() => {
                  setBusy(true);
                  setError("");
                  setOffset(offset - 20);
                }}
              >
                <ArrowLeft size={16} />
              </button>
              <span className="text-xs">
                {attempts.length
                  ? `${offset + 1}–${offset + attempts.length}`
                  : "기록 없음"}
              </span>
              <button
                title="다음 기록"
                aria-label="다음 기록"
                className={button}
                disabled={busy || attempts.length < 20}
                onClick={() => {
                  setBusy(true);
                  setError("");
                  setOffset(offset + 20);
                }}
              >
                <ArrowRight size={16} />
              </button>
            </div>
          </section>
        </>
      )}
      {attempt && !attempt.ended_at && (
        <>
          <fieldset
            disabled={busy || Boolean(prepared)}
            className="min-w-0 space-y-6"
          >
            <StructuredRequestLab
              key={attempt.id}
              initialId={attempt.request_id ?? undefined}
              workflow={{
                id: attempt.id,
                revision: attempt.revision,
                originalRequest: attempt.task.request,
                onStateChange: onLabStateChange,
              }}
            />
          </fieldset>
          <section
            aria-label="수행 종료"
            className="min-w-0 space-y-4 border-t border-line pt-5"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold">수행 종료</h2>
              <button
                className={button}
                disabled={blocked || Boolean(prepared)}
                onClick={() =>
                  void run(async () => {
                    const latest = await workflowApi<WorkflowAttempt>(
                      `/attempts/${attempt.id}`,
                    );
                    const next = await workflowApi<WorkflowAttempt>(
                      `/attempts/${attempt.id}/help`,
                      "POST",
                      { expected_revision: latest.revision },
                    );
                    setAttempt(next);
                    setAcknowledged(false);
                    if (next.source === "participant_self_report")
                      setFeedback((f) => ({ ...f, assistance: "received" }));
                  })
                }
              >
                <HelpCircle size={16} />
                도움 요청 기록 · {attempt.help_count}
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="grid gap-1 text-sm">
                종료 결정
                <select
                  aria-label="종료 결정"
                  className={field}
                  value={disposition}
                  disabled={busy}
                  onChange={(e) => {
                    setDisposition(e.target.value as typeof disposition);
                    setAcknowledged(false);
                  }}
                >
                  <option value="finished">수행 완료</option>
                  <option value="clarification_requested">
                    추가 확인 요청
                  </option>
                  <option value="abandoned">중도 중단</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                도움 여부
                <select
                  aria-label="도움 여부"
                  className={field}
                  value={feedback.assistance}
                  disabled={busy || attempt.source === "automated_qa"}
                  onChange={(e) =>
                    changeFeedback({
                      ...feedback,
                      assistance: e.target
                        .value as WorkflowFeedback["assistance"],
                    })
                  }
                >
                  {attempt.source === "automated_qa" ? (
                    <option value="not_applicable">해당 없음 · 자동 QA</option>
                  ) : (
                    <>
                      <option value="not_reported">미보고</option>
                      <option value="none_reported">
                        도움 없음 · 자가 보고
                      </option>
                      <option value="received">도움 받음</option>
                    </>
                  )}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                체감 난이도
                <select
                  aria-label="체감 난이도"
                  className={field}
                  disabled={busy}
                  value={feedback.difficulty ?? ""}
                  onChange={(e) =>
                    changeFeedback({
                      ...feedback,
                      difficulty: e.target.value
                        ? Number(e.target.value)
                        : null,
                    })
                  }
                >
                  <option value="">미보고</option>
                  {["매우 쉬움", "쉬움", "보통", "어려움", "매우 어려움"].map(
                    (t, i) => (
                      <option key={t} value={i + 1}>
                        {i + 1} · {t}
                      </option>
                    ),
                  )}
                </select>
              </label>
            </div>
            <label className="grid gap-1 text-sm">
              불편 사항·도움 내용·중단 사유
              <textarea
                aria-label="불편 사항·도움 내용·중단 사유"
                className={field}
                rows={3}
                maxLength={2000}
                value={feedback.note}
                disabled={busy}
                onChange={(e) =>
                  changeFeedback({ ...feedback, note: e.target.value })
                }
              />
            </label>
            {!prepared ? (
              <button
                className={button}
                disabled={blocked}
                onClick={() =>
                  void run(async () => {
                    const latest = await workflowApi<WorkflowAttempt>(
                      `/attempts/${attempt.id}`,
                    );
                    setPrepared(latest);
                    setAcknowledged(false);
                  })
                }
              >
                <RefreshCw size={16} />
                종료 전 기록 확인
              </button>
            ) : (
              <div className="space-y-4 border-l-4 border-teal-700 bg-neutral-50 p-4">
                <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                  <div>
                    <dt className="text-xs text-neutral-500">저장 버전</dt>
                    <dd>
                      {prepared.request
                        ? `v${prepared.request.revision}`
                        : "계약 없음"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-neutral-500">제안</dt>
                    <dd>{prepared.request?.checks.length ?? 0}건</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-neutral-500">모의 실행</dt>
                    <dd>
                      {prepared.request?.checks.filter((c) => c.execution)
                        .length ?? 0}
                      건
                    </dd>
                  </div>
                </dl>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    aria-label="종료 결정과 수행 기록을 확인했습니다"
                    className="mt-1"
                    checked={acknowledged}
                    disabled={busy}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                  />
                  종료 결정과 수행 기록을 확인했습니다
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    className={button}
                    disabled={
                      busy ||
                      !acknowledged ||
                      (disposition === "abandoned" && !feedback.note.trim())
                    }
                    onClick={() =>
                      void run(async () => {
                        const next = await workflowApi<WorkflowAttempt>(
                          `/attempts/${attempt.id}/finish`,
                          "POST",
                          {
                            expected_revision: prepared.revision,
                            request_state_hash: prepared.request_state_hash,
                            disposition,
                            ...feedback,
                            acknowledged: true,
                          },
                        );
                        setAttempt(next);
                        setPrepared(null);
                        setAcknowledged(false);
                      })
                    }
                  >
                    <Check size={16} />
                    수행 기록 제출
                  </button>
                  <button
                    className={button}
                    disabled={busy}
                    onClick={() => {
                      setPrepared(null);
                      setAcknowledged(false);
                    }}
                  >
                    계속 수정
                  </button>
                </div>
              </div>
            )}
          </section>
        </>
      )}
      {attempt?.result && (
        <section className="min-w-0 space-y-5 border-t border-line pt-5">
          {attempt.evidence && !attempt.evidence.verified && (
            <p
              role="alert"
              className="border-l-4 border-red-600 bg-red-50 p-4 text-sm text-red-900"
            >
              제출 증거의 무결성을 확인하지 못했습니다.
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2
              className={`text-lg font-semibold ${attempt.result.assessment === "matches_task" ? "text-teal-800" : "text-red-800"}`}
            >
              {assessmentName[attempt.result.assessment]}
            </h2>
            <button
              className={button}
              onClick={() =>
                downloadScenarioJson(
                  attempt,
                  `request-workflow-${attempt.id}.json`,
                )
              }
            >
              <Download size={16} />
              수행 기록 JSON
            </button>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm leading-6">
            {attempt.task.request}
          </p>
          <dl className="grid grid-cols-2 gap-4 border-y border-line py-4 sm:grid-cols-4">
            {[
              [
                "경과 시간 · 대기 포함",
                `${attempt.result.metrics.elapsed_seconds}초`,
              ],
              [
                "첫 저장 이후 재저장",
                attempt.result.metrics.saved_revision_count_after_first,
              ],
              ["모델 제안", attempt.result.metrics.model_proposal_count],
              ["직접 입력 제안", attempt.result.metrics.manual_proposal_count],
              ["차단 제안", attempt.result.metrics.blocked_proposal_count],
              ["모의 실행", attempt.result.metrics.execution_count],
              ["도움 요청 기록", attempt.result.metrics.help_request_count],
              ["도움 여부", assistanceName[attempt.result.feedback.assistance]],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-neutral-500">{label}</dt>
                <dd className="mt-1 break-words text-sm font-medium">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {attempt.result.mismatches.length > 0 && (
            <ul className="list-inside list-disc text-sm text-red-800">
              {attempt.result.mismatches.map((code) => (
                <li key={code}>{mismatchName[code] ?? code}</li>
              ))}
            </ul>
          )}
          {attempt.result.feedback.note && (
            <p className="whitespace-pre-wrap break-words text-sm">
              {attempt.result.feedback.note}
            </p>
          )}
          {attempt.result.mismatches.includes("query") &&
            attempt.result.expected.query !== null &&
            attempt.result.request_snapshot && (
              <RequestQueryDiff
                expected={attempt.result.expected.query}
                submitted={attempt.result.request_snapshot.draft.query}
              />
            )}
          <div className="text-xs">
            <span className="text-neutral-500">제출 증거 SHA-256</span>
            <p className="mt-1 break-all font-mono">
              {attempt.result.evidence_hash}
            </p>
          </div>
          <details>
            <summary className="cursor-pointer text-sm">
              제출 시점 계약 기록
            </summary>
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-all bg-neutral-50 p-4 text-xs">
              {JSON.stringify(attempt.result.request_snapshot, null, 2)}
            </pre>
          </details>
        </section>
      )}
    </>
  );
}
