import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";

const messages: Record<string, string> = {
  workflow_not_found: "해당 수행 기록을 찾을 수 없습니다.",
  stale_workflow_revision: "수행 기록이 변경되었습니다. 새로고침해 주세요.",
  stale_workflow_request_state:
    "계약 또는 제안이 변경되었습니다. 종료 전 기록을 다시 확인해 주세요.",
  workflow_already_ended: "이미 종료한 기록입니다.",
  workflow_proposal_check_required: "계약과 제안 검증 기록이 필요합니다.",
  workflow_help_already_reported:
    "도움 요청 기록이 있습니다. 도움 여부를 확인해 주세요.",
  workflow_assistance_source_mismatch:
    "기록 출처와 도움 여부가 일치하지 않습니다.",
  workflow_request_already_linked:
    "이미 연결된 계약이 있습니다. 수행 기록을 다시 열어 주세요.",
  workflow_original_request_changed: "과제의 원래 요청이 변경되었습니다.",
};

export async function workflowApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await browserApiFetch(
    `${API_BASE_URL}/request-workflows${path}`,
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
  if (!response.ok)
    throw new Error(
      messages[value.detail] ??
        (typeof value.detail === "string"
          ? value.detail
          : "입력 형식을 확인해 주세요."),
    );
  return value as T;
}
