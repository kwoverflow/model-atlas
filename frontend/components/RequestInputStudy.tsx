"use client";

import { Check, Download, Eye, Play, RotateCcw, Save } from "lucide-react";
import { useState } from "react";
import { RequestQueryDiff } from "@/components/RequestQueryDiff";
import {
  downloadScenarioJson,
  scenarioApi,
  scenarioButton as button,
  scenarioField as field,
} from "@/lib/requestScenarioApi";
import type {
  ScenarioTask,
  StudyAnswer,
  StudyAttempt,
} from "@/types/requestScenarios";

type AnswerForm = Omit<StudyAnswer, "priority"> & {
  priority: StudyAnswer["priority"] | { mode: "set"; value: "" };
};
const blank: AnswerForm = {
  decision: "confirm",
  query: "",
  priority: { mode: "unresolved" },
};
const sourceName = {
  automated_qa: "자동 QA",
  participant_self_report: "자가 보고 참여",
};

export function RequestInputStudy({
  tasks,
  attempts,
  onChange,
}: {
  tasks: ScenarioTask[];
  attempts: StudyAttempt[];
  onChange: (a: StudyAttempt) => void;
}) {
  const [taskId, setTaskId] = useState("");
  const [source, setSource] = useState<StudyAttempt["source"]>("automated_qa");
  const [attempt, setAttempt] = useState<StudyAttempt | null>(null);
  const [form, setForm] = useState<AnswerForm>(blank);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dirty =
    JSON.stringify(form) !== JSON.stringify(attempt?.answer ?? blank);
  const valid =
    form.decision === "clarify" ||
    (form.query.trim() &&
      form.priority.mode !== "unresolved" &&
      (form.priority.mode !== "set" || form.priority.value));

  function adopt(next: StudyAttempt) {
    setAttempt(next);
    setForm(next.answer ?? blank);
    setAck(false);
  }
  function change(next: AnswerForm) {
    setForm(next);
    setAck(false);
  }
  async function run(action: () => Promise<StudyAttempt>) {
    setBusy(true);
    setError("");
    try {
      const next = await action();
      adopt(next);
      onChange(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "요청 처리 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="grid min-w-0 gap-5">
      <div className="flex flex-wrap items-end gap-3 border-b border-line pb-5">
        <label className="grid w-40 gap-1 text-xs">
          시나리오
          <select
            aria-label="입력 검증 시나리오"
            className={field}
            value={taskId}
            disabled={busy || dirty}
            onChange={(e) => setTaskId(e.target.value)}
          >
            <option value="">선택</option>
            {tasks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.id}
              </option>
            ))}
          </select>
        </label>
        <label className="grid w-44 gap-1 text-xs">
          기록 출처
          <select
            aria-label="기록 출처"
            className={field}
            value={source}
            disabled={busy || dirty}
            onChange={(e) => setSource(e.target.value as typeof source)}
          >
            <option value="automated_qa">자동 QA</option>
            <option value="participant_self_report">자가 보고 참여</option>
          </select>
        </label>
        <button
          className={button}
          disabled={busy || dirty || !taskId}
          onClick={() =>
            void run(() =>
              scenarioApi<StudyAttempt>("/studies", "POST", {
                scenario_id: taskId,
                source,
              }),
            )
          }
        >
          <Play size={16} />
          입력 검증 시작
        </button>
      </div>
      {error && (
        <p
          role="alert"
          className="border-l-4 border-red-600 bg-red-50 p-3 text-sm text-red-900"
        >
          {error}
        </p>
      )}
      {attempt && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold">
              {attempt.task.id} · {sourceName[attempt.source]}
            </h2>
            <span role="status" className="text-xs text-neutral-600">
              {attempt.submitted_at
                ? "제출됨"
                : dirty
                  ? "저장되지 않은 입력"
                  : "입력 중"}{" "}
              · v{attempt.revision} · 수정 저장 {attempt.correction_count}회
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words border-l-4 border-neutral-300 bg-neutral-100 p-4 text-sm">
            {attempt.task.request}
          </p>
          <div className="grid min-w-0 gap-6 lg:grid-cols-2">
            <div className="grid content-start gap-4">
              <fieldset disabled={busy || Boolean(attempt.submitted_at)}>
                <legend className="mb-2 text-sm">입력 결정</legend>
                <div className="flex flex-wrap gap-4">
                  {(["confirm", "clarify"] as const).map((mode) => (
                    <label
                      key={mode}
                      className="flex min-h-10 items-center gap-2 text-sm"
                    >
                      <input
                        type="radio"
                        name="study-decision"
                        checked={form.decision === mode}
                        onChange={() =>
                          change(
                            mode === "clarify"
                              ? {
                                  decision: mode,
                                  query: "",
                                  priority: { mode: "unresolved" },
                                }
                              : blank,
                          )
                        }
                      />
                      {mode === "confirm" ? "값 확정" : "추가 확인 필요"}
                    </label>
                  ))}
                </div>
              </fieldset>
              {form.decision === "confirm" && (
                <>
                  <label className="grid gap-1 text-sm">
                    query
                    <textarea
                      aria-label="검증 query"
                      className={field}
                      rows={2}
                      maxLength={1000}
                      value={form.query}
                      disabled={busy || Boolean(attempt.submitted_at)}
                      onChange={(e) =>
                        change({ ...form, query: e.target.value })
                      }
                    />
                  </label>
                  <fieldset disabled={busy || Boolean(attempt.submitted_at)}>
                    <legend className="mb-2 text-sm">우선순위</legend>
                    <div className="flex flex-wrap gap-4">
                      {(["unresolved", "set", "omit"] as const).map((mode) => (
                        <label
                          key={mode}
                          className="flex min-h-10 items-center gap-2 text-sm"
                        >
                          <input
                            type="radio"
                            name="study-priority"
                            checked={form.priority.mode === mode}
                            onChange={() =>
                              change({
                                ...form,
                                priority:
                                  mode === "set"
                                    ? { mode, value: "" }
                                    : { mode },
                              })
                            }
                          />
                          {
                            {
                              unresolved: "미확정",
                              set: "값 지정",
                              omit: "생략",
                            }[mode]
                          }
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  {form.priority.mode === "set" && (
                    <label className="grid max-w-xs gap-1 text-sm">
                      우선순위 값
                      <select
                        aria-label="검증 우선순위 값"
                        className={field}
                        value={form.priority.value}
                        disabled={busy || Boolean(attempt.submitted_at)}
                        onChange={(e) =>
                          change({
                            ...form,
                            priority: {
                              mode: "set",
                              value: e.target.value as
                                "low" | "normal" | "high",
                            },
                          })
                        }
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
                </>
              )}
              <div className="flex gap-2">
                <button
                  className={button}
                  disabled={busy || !valid || Boolean(attempt.submitted_at)}
                  onClick={() =>
                    void run(() =>
                      scenarioApi<StudyAttempt>(
                        `/studies/${attempt.id}`,
                        "PUT",
                        {
                          expected_revision: attempt.revision,
                          answer: form,
                        },
                      ),
                    )
                  }
                >
                  <Save size={16} />
                  입력 저장
                </button>
                <button
                  className={button}
                  title="저장된 검증 입력으로 되돌리기"
                  aria-label="저장된 검증 입력으로 되돌리기"
                  disabled={busy || !dirty}
                  onClick={() => adopt(attempt)}
                >
                  <RotateCcw size={16} />
                </button>
              </div>
            </div>
            <div className="min-w-0 border-t border-line pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
              <h3 className="text-sm font-semibold">저장된 입력 검토</h3>
              <pre className="my-4 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
                {attempt.answer
                  ? JSON.stringify(attempt.answer, null, 2)
                  : "미저장"}
              </pre>
              <label className="flex items-start gap-2 text-sm">
                <input
                  aria-label="저장한 검증 입력을 확인했습니다"
                  className="mt-1"
                  type="checkbox"
                  checked={ack}
                  disabled={
                    busy ||
                    dirty ||
                    !attempt.answer ||
                    Boolean(attempt.submitted_at)
                  }
                  onChange={(e) => setAck(e.target.checked)}
                />
                저장한 입력을 확인했습니다
              </label>
              <button
                className={`${button} mt-4`}
                disabled={
                  busy ||
                  dirty ||
                  !ack ||
                  !attempt.answer ||
                  Boolean(attempt.submitted_at)
                }
                onClick={() =>
                  void run(() =>
                    scenarioApi<StudyAttempt>(
                      `/studies/${attempt.id}/submit`,
                      "POST",
                      {
                        expected_revision: attempt.revision,
                        expected_hash: attempt.answer_hash,
                        acknowledged: true,
                      },
                    ),
                  )
                }
              >
                <Check size={16} />
                결과 제출
              </button>
              <p className="mt-4 text-xs text-neutral-500">
                {attempt.actor.display_name} ·{" "}
                {attempt.actor.identity_verified ? "인증 계정" : "신원 미검증"}{" "}
                · 사람 검토 인증 없음
              </p>
            </div>
          </div>
          {attempt.result && (
            <div className="grid min-w-0 gap-3 border-y border-line py-5">
              <h3
                className={`text-base font-semibold ${attempt.result.matches_scenario_key ? "text-teal-800" : "text-red-800"}`}
              >
                {attempt.result.matches_scenario_key
                  ? "시나리오 기준 일치"
                  : "시나리오 기준 불일치"}
              </h3>
              <dl className="flex flex-wrap gap-8 text-sm">
                <div>
                  <dt className="text-xs text-neutral-500">
                    경과 시간 · 대기 포함
                  </dt>
                  <dd className="mt-1">{attempt.result.elapsed_seconds}초</dd>
                </div>
                <div>
                  <dt className="text-xs text-neutral-500">수정 저장 횟수</dt>
                  <dd className="mt-1">{attempt.result.correction_count}회</dd>
                </div>
                <div>
                  <dt className="text-xs text-neutral-500">불일치 항목</dt>
                  <dd className="mt-1">
                    {attempt.result.mismatches.join(", ") || "없음"}
                  </dd>
                </div>
              </dl>
              {attempt.submitted_at &&
                attempt.answer &&
                attempt.result.mismatches.includes("query") && (
                  <RequestQueryDiff
                    expected={attempt.result.expected.query}
                    submitted={attempt.answer.query}
                  />
                )}
              <details className="text-xs">
                <summary className="cursor-pointer">시나리오 기준 입력</summary>
                <pre className="mt-3 overflow-auto whitespace-pre-wrap break-all">
                  {JSON.stringify(attempt.result.expected, null, 2)}
                </pre>
              </details>
              <button
                className={`${button} justify-self-start`}
                title="입력 검증 JSON 다운로드"
                aria-label="입력 검증 JSON 다운로드"
                onClick={() =>
                  downloadScenarioJson(
                    attempt,
                    `request-study-${attempt.id}.json`,
                  )
                }
              >
                <Download size={16} />
              </button>
            </div>
          )}
        </>
      )}
      <section className="min-w-0 border-t border-line pt-4">
        <h2 className="mb-3 text-base font-semibold">최근 입력 기록</h2>
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full min-w-[650px] text-left text-sm">
            <thead className="border-b border-line text-xs text-neutral-500">
              <tr>
                <th className="py-3">시작</th>
                <th>시나리오</th>
                <th>출처</th>
                <th>결과</th>
                <th>열기</th>
              </tr>
            </thead>
            <tbody>
              {attempts.map((a) => (
                <tr key={a.id} className="border-b border-line">
                  <td className="py-3">
                    {new Date(a.started_at).toLocaleString("ko-KR")}
                  </td>
                  <td>{a.task.id}</td>
                  <td>{sourceName[a.source]}</td>
                  <td>
                    {a.result
                      ? a.result.matches_scenario_key
                        ? "기준 일치"
                        : "기준 불일치"
                      : "미제출"}
                  </td>
                  <td>
                    <button
                      className={button}
                      title={`${a.task.id} 기록 열기`}
                      aria-label={`${a.id} 기록 열기`}
                      disabled={busy || dirty}
                      onClick={() =>
                        void run(() =>
                          scenarioApi<StudyAttempt>(`/studies/${a.id}`),
                        )
                      }
                    >
                      <Eye size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!attempts.length && (
            <p className="py-5 text-sm text-neutral-500">입력 기록 없음</p>
          )}
        </div>
      </section>
    </section>
  );
}
