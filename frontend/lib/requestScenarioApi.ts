import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";

const messages: Record<string, string> = {
  stale_study_revision: "입력 버전이 변경되었습니다. 기록을 다시 불러오세요.",
  study_already_submitted: "이미 제출한 기록입니다.",
  study_answer_integrity_failed: "저장된 입력의 무결성을 확인하지 못했습니다.",
  operator_authentication_required: "운영자 로그인이 필요합니다.",
  operator_role_not_allowed: "이 작업에 필요한 권한이 없습니다.",
};

export async function scenarioApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await browserApiFetch(
    `${API_BASE_URL}/request-scenarios${path}`,
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
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      messages[data.detail] ??
        (typeof data.detail === "string"
          ? data.detail
          : "입력 형식을 확인해 주세요."),
    );
  return data as T;
}

export function downloadScenarioJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const scenarioField =
  "w-full min-w-0 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm disabled:bg-neutral-100";
export const scenarioButton =
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-medium hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-40";
