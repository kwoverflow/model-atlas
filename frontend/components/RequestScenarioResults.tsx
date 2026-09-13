"use client";

import { Download, Eye, Play } from "lucide-react";
import { useState } from "react";
import {
  downloadScenarioJson,
  scenarioButton as button,
  scenarioField as field,
} from "@/lib/requestScenarioApi";
import type { ScenarioOutcome, ScenarioRun } from "@/types/requestScenarios";

const labels: Record<ScenarioOutcome, string> = {
  passed: "예상 동작",
  known_limitation: "알려진 한계",
  regression: "회귀 실패",
  error: "검사 오류",
};
const colors: Record<ScenarioOutcome, string> = {
  passed: "text-teal-800",
  known_limitation: "text-amber-800",
  regression: "text-red-800",
  error: "text-red-800",
};

export function RequestScenarioResults({
  runs,
  busy,
  onRun,
}: {
  runs: ScenarioRun[];
  busy: boolean;
  onRun: () => void;
}) {
  const [runId, setRunId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [filter, setFilter] = useState<"all" | ScenarioOutcome>("all");
  const selected = runs.find((r) => r.id === runId) ?? runs[0];
  const rows =
    selected?.report.rows.filter(
      (r) => filter === "all" || r.outcome === filter,
    ) ?? [];
  const detail = rows.find((r) => r.id === caseId) ?? rows[0];

  return (
    <section className="grid min-w-0 gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="grid w-full max-w-lg gap-1 text-xs">
          최근 실행
          <select
            aria-label="최근 실행"
            className={field}
            value={selected?.id ?? ""}
            onChange={(e) => setRunId(e.target.value)}
            disabled={busy || !runs.length}
          >
            {!runs.length && <option value="">실행 기록 없음</option>}
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleString("ko-KR")} ·{" "}
                {r.report.counts.regression + r.report.counts.error
                  ? "실패 포함"
                  : "한계 포함 완료"}
              </option>
            ))}
          </select>
        </label>
        <div className="flex gap-2">
          <button
            className={button}
            disabled={busy}
            onClick={() => {
              setRunId("");
              onRun();
            }}
          >
            <Play size={16} />
            {busy ? "검사 중" : "15개 자동 검사"}
          </button>
          <button
            className={button}
            title="검사 JSON 다운로드"
            aria-label="검사 JSON 다운로드"
            disabled={!selected || busy}
            onClick={() =>
              selected &&
              downloadScenarioJson(
                selected,
                `request-scenarios-${selected.id}.json`,
              )
            }
          >
            <Download size={17} />
          </button>
        </div>
      </div>
      {selected ? (
        <>
          <dl className="grid grid-cols-2 gap-4 border-y border-line py-4 md:grid-cols-4">
            {(Object.keys(labels) as ScenarioOutcome[]).map((key) => (
              <div key={key}>
                <dt className="text-xs text-neutral-500">{labels[key]}</dt>
                <dd className={`mt-1 text-2xl font-semibold ${colors[key]}`}>
                  {selected.report.counts[key]}
                </dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="text-xs text-neutral-600">
              {selected.report.version} · {selected.report.duration_ms} ms ·
              모델 호출 {selected.report.model_calls}회
            </div>
            <label className="grid w-40 gap-1 text-xs">
              판정 필터
              <select
                aria-label="판정 필터"
                className={field}
                value={filter}
                onChange={(e) => setFilter(e.target.value as typeof filter)}
              >
                <option value="all">전체</option>
                {(Object.keys(labels) as ScenarioOutcome[]).map((key) => (
                  <option key={key} value={key}>
                    {labels[key]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[690px] text-left text-sm">
              <thead className="border-b border-line text-xs text-neutral-500">
                <tr>
                  <th className="py-3">시나리오</th>
                  <th>판정</th>
                  <th>예상 / 관측 HTTP</th>
                  <th>핸들러 호출</th>
                  <th>상세</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-line">
                    <td className="py-3">
                      <span className="mr-2 font-mono text-xs text-neutral-500">
                        {row.id}
                      </span>
                      {row.title}
                    </td>
                    <td className={colors[row.outcome]}>
                      {labels[row.outcome]}
                    </td>
                    <td>
                      {row.expected?.status ?? "-"} /{" "}
                      {row.observed?.status ?? "-"}
                    </td>
                    <td>{row.observed?.handler_invocations ?? "-"}</td>
                    <td>
                      <button
                        className={button}
                        title={`${row.id} 상세`}
                        aria-label={`${row.id} 상세`}
                        onClick={() => setCaseId(row.id)}
                      >
                        <Eye size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && (
              <p className="py-5 text-sm text-neutral-500">해당 판정 없음</p>
            )}
          </div>
          {detail && (
            <div className="grid min-w-0 gap-3 border-l-4 border-neutral-300 bg-neutral-100 p-4">
              <h2
                className={`text-base font-semibold ${colors[detail.outcome]}`}
              >
                {detail.id} · {detail.title}
              </h2>
              {detail.outcome === "known_limitation" && (
                <p className="text-sm text-amber-900">
                  원래 요청은 low이지만 high로 잘못 확정한 계약과 제안이 일치해
                  실행됐습니다. 사용자 확정값의 의미적 오류는 탐지하지 못합니다.
                </p>
              )}
              <dl className="grid gap-2 text-sm">
                <div>
                  <dt className="text-xs text-neutral-500">원래 요청</dt>
                  <dd className="mt-1 break-words">
                    {detail.fixture.draft.original_request}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-neutral-500">
                    검사에 사용한 제안
                  </dt>
                  <dd>
                    <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all text-xs">
                      {detail.fixture.proposal}
                    </pre>
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-neutral-500">관측된 차단 사유</dt>
                  <dd className="mt-1 break-all font-mono text-xs">
                    {detail.observed?.reasons.join(", ") ||
                      detail.error_type ||
                      "없음"}
                  </dd>
                </div>
              </dl>
              {detail.expectations && (
                <ul className="grid gap-1 text-xs">
                  {Object.entries(detail.expectations)
                    .filter(([, matched]) => !matched)
                    .map(([name]) => (
                      <li key={name} className="text-red-800">
                        기대 조건 불일치: {name}
                      </li>
                    ))}
                </ul>
              )}
            </div>
          )}
          <details className="min-w-0 border-t border-line pt-3 text-xs">
            <summary className="cursor-pointer">실행 근거</summary>
            <p className="my-3 break-all font-mono">
              Pack SHA-256: {selected.report.pack_hash}
            </p>
            <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(selected.report.implementation_hashes, null, 2)}
            </pre>
          </details>
        </>
      ) : (
        <p className="border-t border-line py-8 text-sm text-neutral-500">
          자동 검사 기록 없음
        </p>
      )}
    </section>
  );
}
