import { API_BASE_URL } from "@/lib/apiBase";
import { browserApiFetch } from "@/lib/browserApi";
import type { AssistantEvidenceMetadata } from "@/lib/assistantEvidence";

export type Fields = Record<string, string | number | null>;
export type Review = {
  id: string;
  request: string;
  raw_output: string;
  initial_fields: Fields;
  fields: Fields;
  revision: number;
  content_hash: string;
  status: string;
  parent_id: string | null;
  created_at: number;
  metadata: AssistantEvidenceMetadata & {
    decision?: string;
    reason?: string;
    generation_error?: string;
    latency_ms?: number;
  };
  preview: {
    proposal_id: string;
    action: { tool: string; arguments: Record<string, string> };
    plan_hash: string;
    expires_at: number;
  } | null;
  receipt: Record<string, unknown> | null;
  events: {
    event: string;
    payload: Record<string, unknown>;
    created: number;
  }[];
};
export type Workspace = {
  mode: string;
  model: string;
  application_version?: string;
  draft_strategy?: string;
  state: {
    events: Fields[];
    tasks: Fields[];
    files: Record<string, { size: number; sha256: string }>;
  };
};

const errors: Record<string, string> = {
  assistant_workspace_not_configured: "검토 작업공간이 연결되지 않았습니다.",
  assistant_workspace_not_initialized: "검토 작업공간이 준비되지 않았습니다.",
  assistant_workspace_initializing:
    "작업공간을 준비 중입니다. 잠시 후 새로고침해 주세요.",
  assistant_workspace_unavailable: "작업공간을 열 수 없습니다. 초기화 상태를 확인해 주세요.",
  linked_initialization_lock: "작업공간 잠금 파일이 안전하지 않아 접근을 중단했습니다.",
  local_assistant_only: "로컬 작업공간에 접근할 수 없습니다.",
  invalid_review_fields: "필수 입력값과 형식을 확인해 주세요.",
  stale_review_revision:
    "다른 창에서 수정되었습니다. 최신 기록을 불러와 주세요.",
  calendar_conflict: "기존 일정과 시간이 겹칩니다.",
  duplicate_event: "같은 일정이 이미 있습니다.",
  duplicate_task: "같은 할 일이 이미 있습니다.",
  task_target_not_unique: "대상을 하나로 지정해 주세요.",
  task_target_required: "완료할 할 일을 지정해 주세요.",
  task_already_complete: "이미 완료한 할 일입니다.",
  time_needs_clarification: "정확한 현지 시작 시각이 필요합니다.",
  duration_needs_clarification: "일정의 길이를 입력해 주세요.",
  invalid_local_time_or_timezone:
    "현지 시각과 시간대를 확인해 주세요. 시각에는 offset을 넣지 않습니다.",
  nonexistent_or_ambiguous_local_time:
    "서머타임 전환으로 시각이 모호하거나 존재하지 않습니다.",
  invalid_relative_path: "작업공간 안의 상대 경로를 입력해 주세요.",
  parent_directory_missing: "대상 폴더가 없습니다.",
  source_file_missing: "원본 파일을 찾을 수 없습니다.",
  destination_exists: "대상 위치에 파일이 이미 있습니다.",
  approval_expired_or_state_changed:
    "승인 시간이 지났거나 작업공간이 변경되었습니다. 다시 확정해 주세요.",
  review_confirmation_required: "저장한 내용을 먼저 확정해 주세요.",
  approval_plan_hash_mismatch: "미리보기와 승인 내용이 다릅니다.",
  completed_review_cannot_be_edited:
    "실행되었거나 상태 확인이 필요한 기록입니다.",
  changed_file_cannot_be_undone: "파일이 수정되어 자동 복구할 수 없습니다.",
  recovery_state_ambiguous: "파일 상태가 기록과 달라 자동 복구를 중단했습니다.",
  interrupted_file_operation_required: "중단된 파일 작업이 아닙니다.",
  no_executed_change: "복구할 실행 기록이 없습니다.",
  hardlinked_file: "중단된 파일 작업의 상태 확인이 필요합니다.",
  workspace_execution_in_progress:
    "작업이 진행 중입니다. 잠시 후 상태를 새로고침해 주세요.",
};

export async function assistantApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await browserApiFetch(
    `${API_BASE_URL}/personal-assistant${path}`,
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
    const code =
      typeof value.detail === "string" ? value.detail : "invalid_review_fields";
    throw new Error(
      errors[code] ??
        (code.startsWith("execution_failed")
          ? "작업 실행에 실패했습니다. 상태를 확인해 주세요."
          : code),
    );
  }
  return value as T;
}

export function binding(review: Review) {
  return { revision: review.revision, content_hash: review.content_hash };
}

export const operationNames: Record<string, string> = {
  "calendar.create": "일정 추가",
  "todo.create": "할 일 추가",
  "todo.complete": "할 일 완료",
  "files.move": "파일 이동",
  "files.trash": "파일 보관",
  "files.restore": "파일 복구",
};
export const fieldNames: Record<string, string> = {
  operation: "작업",
  title: "제목",
  local_start: "현지 시작 시각",
  source_timezone: "시간대",
  duration_minutes: "길이(분)",
  local_due: "현지 마감 시각",
  priority: "우선순위",
  task_id: "할 일 ID",
  source: "원본 파일",
  destination: "대상 파일",
  path: "파일",
  start_at: "시작 시각",
  end_at: "종료 시각",
  due_at: "마감 시각",
  source_area: "원본 위치",
};
export const statusNames: Record<string, string> = {
  draft: "검토 중",
  pending: "승인 대기",
  executed: "실행 완료",
  cancelled: "취소됨",
  expired: "승인 만료",
  stale: "재확정 필요",
  executing: "상태 확인 필요",
  failed: "실행 실패",
  superseded: "이전 확정",
  confirmed: "확정됨",
};

export function reviewChanges(review: Review, fields = review.fields) {
  return [
    ...new Set([...Object.keys(review.initial_fields), ...Object.keys(fields)]),
  ]
    .filter(
      (key) => (review.initial_fields[key] ?? null) !== (fields[key] ?? null),
    )
    .map((key) => ({
      key,
      before: review.initial_fields[key] ?? null,
      after: fields[key] ?? null,
    }));
}
