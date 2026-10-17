"use client";

import {
  Ban,
  Check,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AssistantWorkspace } from "@/components/personal-assistant/AssistantWorkspace";
import { assistantEvidenceLabels } from "@/lib/assistantEvidence";
import {
  assistantFieldClass as field,
  ReviewFields,
} from "@/components/personal-assistant/ReviewFields";
import {
  assistantApi,
  binding,
  fieldNames,
  operationNames,
  reviewChanges,
  statusNames,
  type Fields,
  type Review,
  type Workspace,
} from "@/lib/personalAssistant";

const buttonBase =
  "inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-40";
const button = `${buttonBase} border-neutral-300 bg-white hover:bg-neutral-50`;

function text(value: unknown) {
  return value === null || value === undefined ? "" : String(value);
}
function date(value: number) {
  return new Date(value * 1000).toLocaleString("ko-KR");
}
function valueLabel(value: unknown) {
  return text(value) || "생략";
}

function loadSnapshot() {
  return Promise.allSettled([
    assistantApi<Review[]>("/reviews"),
    assistantApi<Workspace>("/workspace"),
  ]);
}

export function PersonalAssistantReview() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [review, setReview] = useState<Review | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [fields, setFields] = useState<Fields>({});
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState<string | null>("load");
  const [error, setError] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [now, setNow] = useState(0);
  const dirty = Boolean(
    review && JSON.stringify(fields) !== JSON.stringify(review.fields),
  );
  const frozen = Boolean(
    review?.parent_id ||
      ["executed", "executing", "failed"].includes(review?.status ?? ""),
  );
  const operation = text(fields.operation) || "todo.create";
  const expired = Boolean(
    review?.preview && review.preview.expires_at * 1000 <= now,
  );
  const pending = review?.status === "pending" && !expired && !dirty;

  const adopt = useCallback((record: Review) => {
    setReview(record);
    setFields(record.fields);
    setAcknowledged(false);
    setNow(Date.now());
  }, []);

  const receiveSnapshot = useCallback(
    (results: Awaited<ReturnType<typeof loadSnapshot>>) => {
      if (results[0].status === "fulfilled") setReviews(results[0].value);
      if (results[1].status === "fulfilled") setWorkspace(results[1].value);
      else setWorkspace(null);
      const failed = results.find((result) => result.status === "rejected");
      if (failed?.status === "rejected")
        setError(
          failed.reason instanceof Error
            ? failed.reason.message
            : "기록을 불러오지 못했습니다.",
        );
    },
    [],
  );
  const refresh = useCallback(async () => {
    receiveSnapshot(await loadSnapshot());
  }, [receiveSnapshot]);

  useEffect(() => {
    let active = true;
    void loadSnapshot().then((results) => {
      if (active) {
        receiveSnapshot(results);
        setBusy(null);
      }
    });
    return () => {
      active = false;
    };
  }, [receiveSnapshot]);
  useEffect(() => {
    if (review?.status !== "pending") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [review?.status]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function act(name: string, execute: () => Promise<Review>) {
    setBusy(name);
    setError(null);
    try {
      adopt(await execute());
      await refresh();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "요청을 처리하지 못했습니다.",
      );
      if (review && !dirty) {
        try {
          adopt(await assistantApi<Review>(`/reviews/${review.id}`));
        } catch {
          /* Keep the visible record if the API is unavailable. */
        }
      }
    } finally {
      setBusy(null);
    }
  }

  function update(key: string, value: string | number | null) {
    setFields((current) => ({ ...current, [key]: value }));
    setAcknowledged(false);
  }

  function changeOperation(next: string) {
    setFields({ operation: next });
    setAcknowledged(false);
  }

  const changes = review ? reviewChanges(review, fields) : [];
  const evidence = review ? assistantEvidenceLabels(review.metadata) : null;

  return (
    <>
      <section className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex items-center gap-3">
          <ClipboardCheck size={24} className="text-teal" aria-hidden="true" />
          <div>
            <h1 className="text-2xl font-semibold">개인 비서 검토</h1>
            <p className="mt-1 text-sm text-neutral-500">
              {workspace?.application_version ? `Model Atlas ${workspace.application_version} · ` : ""}
              Qwen3.5 9B · 로컬 작업공간
            </p>
          </div>
        </div>
        <button
          className={button}
          title="새로고침"
          disabled={Boolean(busy) || dirty}
          onClick={() => {
            setBusy("load");
            setError(null);
            void refresh()
              .then(async () => {
                if (review)
                  adopt(await assistantApi<Review>(`/reviews/${review.id}`));
              })
              .catch((cause) => setError(String(cause)))
              .finally(() => setBusy(null));
          }}
        >
          <RefreshCw size={16} aria-hidden="true" />
          새로고침
        </button>
      </section>

      {error ? (
        <div
          role="alert"
          className="break-words border-l-4 border-rose bg-rose/5 px-4 py-3 text-sm text-rose"
        >
          {error}
        </div>
      ) : null}

      <section className="grid gap-3 border-b border-line pb-5">
        <label htmlFor="assistant-request" className="text-sm font-semibold">
          요청
        </label>
        <textarea
          id="assistant-request"
          className={`${field} min-h-24 resize-y`}
          value={request}
          maxLength={4000}
          disabled={Boolean(busy) || dirty}
          onChange={(event) => setRequest(event.target.value)}
        />
        <div className="flex justify-end">
          <button
            className={`${buttonBase} border-ink bg-ink text-white hover:bg-neutral-700`}
            disabled={Boolean(busy) || dirty || !request.trim()}
            onClick={() =>
              void act("generate", () =>
                assistantApi<Review>("/reviews", "POST", { request }),
              )
            }
          >
            {busy === "generate" ? (
              <LoaderCircle
                size={16}
                className="animate-spin"
                aria-hidden="true"
              />
            ) : (
              <Plus size={16} aria-hidden="true" />
            )}
            초안 생성
          </button>
        </div>
      </section>

      <div className="grid min-w-0 gap-6 xl:grid-cols-[260px_minmax(0,1fr)]">
        <section
          className="min-w-0 border-b border-line pb-4 xl:border-b-0 xl:border-r xl:pr-5"
          aria-label="검토 기록"
        >
          <h2 className="mb-3 text-base font-semibold">
            검토 기록{" "}
            <span className="font-normal text-neutral-500">
              {reviews.length}
            </span>
          </h2>
          <div className="grid max-h-80 overflow-y-auto xl:max-h-[700px]">
            {!reviews.length ? (
              <p className="py-5 text-sm text-neutral-500">
                검토 기록이 없습니다.
              </p>
            ) : (
              reviews.map((item) => (
                <button
                  key={item.id}
                  disabled={Boolean(busy) || dirty}
                  className={`min-w-0 border-b border-line px-3 py-3 text-left text-sm disabled:opacity-50 ${review?.id === item.id ? "border-l-2 border-l-teal bg-teal/5" : "hover:bg-white"}`}
                  onClick={() =>
                    void act("select", () =>
                      assistantApi<Review>(`/reviews/${item.id}`),
                    )
                  }
                >
                  <span className="block break-words font-medium">
                    {item.request}
                  </span>
                  <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-500">
                    <span>{statusNames[item.status] ?? item.status}</span>
                    <span>{date(item.created_at)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="min-w-0" aria-label="초안 편집">
          {!review ? (
            <div className="flex items-center gap-3 py-10 text-sm text-neutral-500">
              <FileText size={22} aria-hidden="true" />
              선택한 기록이 없습니다.
            </div>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-semibold">
                  {review.parent_id ? "파일 복구 검토" : "초안 검토"}
                </h2>
                <span className="text-sm font-medium text-teal">
                  {dirty
                    ? "저장하지 않은 수정"
                    : (statusNames[review.status] ?? review.status)}
                </span>
              </div>
              {evidence ? (
                <div className="mb-4 min-w-0 border-l-2 border-neutral-300 pl-3" data-testid="assistant-evidence">
                  <p className="mb-1 text-xs font-medium text-neutral-600">원본 초안 근거</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs leading-5 text-neutral-500">
                    <span>{evidence.action}</span>
                    <span>{evidence.content}</span>
                    <span>{evidence.reason}</span>
                  </div>
                  {review.metadata.reason && !review.metadata.generation_error ? (
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-neutral-600">
                      {review.metadata.reason}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {review.metadata.generation_error ? (
                <p className="mb-4 text-sm text-rose">
                  원본 모델 응답이 검증을 통과하지 못했습니다.
                </p>
              ) : null}
              {!review.parent_id ? (
                <ReviewFields
                  fields={fields}
                  disabled={Boolean(busy) || frozen}
                  onChange={update}
                  onOperation={changeOperation}
                />
              ) : null}
              {!frozen ? (
                <div className="mt-4 flex flex-wrap justify-end gap-2">
                  <button
                    className={button}
                    disabled={Boolean(busy) || !dirty}
                    title="저장하지 않은 수정 취소"
                    onClick={() => adopt(review)}
                  >
                    <RotateCcw size={16} aria-hidden="true" />
                    수정 취소
                  </button>
                  <button
                    className={button}
                    disabled={Boolean(busy) || !dirty}
                    onClick={() =>
                      void act("save", () =>
                        assistantApi<Review>(`/reviews/${review.id}`, "PUT", {
                          ...binding(review),
                          fields: { operation, ...fields },
                        }),
                      )
                    }
                  >
                    <Save size={16} aria-hidden="true" />
                    수정 저장
                  </button>
                </div>
              ) : null}

              <details className="mt-5 border-y border-line py-3">
                <summary className="cursor-pointer text-sm font-medium">
                  모델 원문 · 수정 내역
                </summary>
                <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs leading-5 text-neutral-600">
                  {review.raw_output || "모델 원문 없음"}
                </pre>
                {changes.length ? (
                  <dl className="mt-4 grid gap-2 text-sm">
                    {changes.map((change) => (
                      <div
                        className="grid gap-1 sm:grid-cols-[120px_minmax(0,1fr)]"
                        key={change.key}
                      >
                        <dt className="text-neutral-500">
                          {fieldNames[change.key] ?? change.key}
                        </dt>
                        <dd className="break-all">
                          <span className="text-neutral-500 line-through">
                            {valueLabel(change.before)}
                          </span>
                          <span className="mx-2">→</span>
                          {valueLabel(change.after)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : null}
              </details>

              {!frozen && !review.parent_id ? (
                <div className="mt-5 grid gap-3">
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={acknowledged}
                      disabled={Boolean(busy) || dirty}
                      onChange={(event) =>
                        setAcknowledged(event.target.checked)
                      }
                    />
                    수정한 내용과 실행 대상을 확인했습니다.
                  </label>
                  <div className="flex justify-end">
                    <button
                      className={`${button} border-teal text-teal`}
                      disabled={Boolean(busy) || dirty || !acknowledged}
                      onClick={() =>
                        void act("confirm", () =>
                          assistantApi<Review>(
                            `/reviews/${review.id}/confirm`,
                            "POST",
                            { ...binding(review), acknowledged },
                          ),
                        )
                      }
                    >
                      <Check size={16} aria-hidden="true" />
                      확정 및 미리보기
                    </button>
                  </div>
                </div>
              ) : null}

              {review.preview ? (
                <section
                  className="mt-6 border-t border-line pt-5"
                  aria-label="실행 미리보기"
                >
                  <h3 className="text-base font-semibold">
                    {operationNames[review.preview.action.tool] ?? "실행"}{" "}
                    미리보기
                  </h3>
                  <dl className="mt-3 grid gap-2 text-sm">
                    {Object.entries(review.preview.action.arguments).map(
                      ([key, value]) => (
                        <div
                          key={key}
                          className="grid min-w-0 gap-1 sm:grid-cols-[120px_minmax(0,1fr)]"
                        >
                          <dt className="text-neutral-500">
                            {fieldNames[key] ?? key}
                          </dt>
                          <dd className="break-all">{value}</dd>
                        </div>
                      ),
                    )}
                  </dl>
                  {review.status === "pending" ? (
                    <p className="mt-3 text-xs text-neutral-500">
                      {expired
                        ? "승인 만료"
                        : `승인 유효 시각: ${date(review.preview.expires_at)}`}
                    </p>
                  ) : null}
                  <div className="mt-4 flex flex-wrap justify-end gap-2">
                    {review.status === "pending" ? (
                      <button
                        className={button}
                        disabled={Boolean(busy) || dirty}
                        onClick={() =>
                          void act("cancel", () =>
                            assistantApi<Review>(
                              `/reviews/${review.id}/cancel`,
                              "POST",
                              binding(review),
                            ),
                          )
                        }
                      >
                        <Ban size={16} aria-hidden="true" />
                        취소
                      </button>
                    ) : null}
                    {pending ? (
                      <button
                        className={`${buttonBase} border-teal bg-teal text-white hover:bg-teal/90`}
                        disabled={Boolean(busy)}
                        onClick={() =>
                          void act("approve", () =>
                            assistantApi<Review>(
                              `/reviews/${review.id}/approve`,
                              "POST",
                              {
                                ...binding(review),
                                plan_hash: review.preview!.plan_hash,
                              },
                            ),
                          )
                        }
                      >
                        <Play size={16} aria-hidden="true" />
                        승인하고 실행
                      </button>
                    ) : null}
                    {review.status === "executed" &&
                    !review.parent_id &&
                    ["files.move", "files.trash"].includes(
                      review.preview.action.tool,
                    ) ? (
                      <button
                        className={button}
                        disabled={Boolean(busy)}
                        onClick={() =>
                          void act("restore", () =>
                            assistantApi<Review>(
                              `/reviews/${review.id}/restore`,
                              "POST",
                              binding(review),
                            ),
                          )
                        }
                      >
                        <RotateCcw size={16} aria-hidden="true" />
                        복구 미리보기
                      </button>
                    ) : null}
                    {["executing", "failed"].includes(review.status) ? (
                      <button
                        className={button}
                        disabled={Boolean(busy)}
                        onClick={() =>
                          void act("recover", () =>
                            assistantApi<Review>(
                              `/reviews/${review.id}/recover`,
                              "POST",
                              binding(review),
                            ),
                          )
                        }
                      >
                        <RefreshCw size={16} aria-hidden="true" />
                        상태 확인 및 복구
                      </button>
                    ) : null}
                  </div>
                </section>
              ) : null}
              {review.status === "executed" ? (
                <div
                  role="status"
                  className="mt-5 flex items-center gap-2 text-sm font-medium text-teal"
                >
                  <CheckCircle2 size={18} aria-hidden="true" />
                  {review.parent_id
                    ? "파일 복구 완료"
                    : "승인한 작업을 완료했습니다."}
                </div>
              ) : null}
              <section className="mt-6 border-t border-line pt-4">
                <h3 className="text-sm font-semibold">처리 기록</h3>
                <ol className="mt-3 grid gap-2 text-sm text-neutral-500">
                  {review.events.map((event, index) => (
                    <li
                      className="flex flex-wrap justify-between gap-2"
                      key={index}
                    >
                      <span>
                        {(
                          {
                            draft_created: "초안 생성",
                            user_edited: "사용자 수정",
                            user_confirmed: "내용 확정",
                            executed: "실행 완료",
                            execution_replayed: "기존 실행 결과 확인",
                            cancelled: "승인 취소",
                            restore_preview: "복구 미리보기",
                            execution_rejected: "실행 중단",
                            reconciled: "중단 작업 상태 확인",
                          } as Record<string, string>
                        )[event.event] ?? event.event}
                      </span>
                      <time>{date(event.created)}</time>
                    </li>
                  ))}
                </ol>
              </section>
            </>
          )}
        </section>
      </div>

      <AssistantWorkspace workspace={workspace} />
    </>
  );
}
