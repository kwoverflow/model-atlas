import { useState } from "react";

import { type Workspace } from "@/lib/personalAssistant";

function text(value: unknown) {
  return value === null || value === undefined ? "" : String(value);
}

export function AssistantWorkspace({
  workspace,
}: {
  workspace: Workspace | null;
}) {
  const [tab, setTab] = useState("tasks");
  const state = workspace?.state;
  if (!workspace) {
    return (
      <p
        role="status"
        className="border-t border-line pt-5 text-sm text-neutral-500"
      >
        작업공간 상태 확인이 필요합니다.
      </p>
    );
  }
  return (
    <section
      className="min-w-0 border-t border-line pt-5"
      aria-label="작업공간 현황"
    >
      <div
        className="flex flex-wrap gap-1 border-b border-line"
        role="tablist"
        aria-label="작업공간"
      >
        {[
          ["tasks", "할 일"],
          ["events", "일정"],
          ["files", "파일"],
        ].map(([key, name]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`min-h-10 px-4 py-2 text-sm ${tab === key ? "border-b-2 border-teal font-semibold text-teal" : "text-neutral-500"}`}
            onClick={() => setTab(key)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto py-3" role="tabpanel">
        {tab === "files" ? (
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-neutral-500">
              <tr>
                <th className="py-2 font-medium">파일</th>
                <th className="py-2 text-right font-medium">크기</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(state?.files ?? {}).map(([name, value]) => (
                <tr key={name} className="border-t border-line">
                  <td className="break-all py-2 pr-4">{name}</td>
                  <td className="whitespace-nowrap py-2 text-right">
                    {value.size} B
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-neutral-500">
              <tr>
                <th className="py-2 font-medium">제목</th>
                <th className="py-2 font-medium">
                  {tab === "tasks" ? "상태" : "시각"}
                </th>
              </tr>
            </thead>
            <tbody>
              {(tab === "tasks" ? state?.tasks : state?.events)?.map((item) => (
                <tr
                  key={text(item.task_id ?? item.event_id)}
                  className="border-t border-line"
                >
                  <td className="break-words py-2 pr-4">
                    {text(item.title)}
                    <span className="mt-1 block break-all text-xs text-neutral-400">
                      {text(item.task_id ?? item.event_id)}
                    </span>
                  </td>
                  <td className="break-words py-2">
                    {tab === "tasks"
                      ? item.status === "complete"
                        ? "완료"
                        : "진행 중"
                      : `${text(item.start_at)} ~ ${text(item.end_at)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
