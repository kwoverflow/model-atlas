export type AssistantEvidenceMetadata = {
  generation_error?: string;
  semantic_evidence?: {
    action_evidence?: { status?: string };
    content_evidence?: { status?: string };
  };
  release_explanation?: { policy?: string };
};

export function assistantEvidenceLabels(metadata: AssistantEvidenceMetadata) {
  if (metadata.generation_error) {
    return { action: "응답 검증 실패", content: "문서 의미 미검증", reason: "원문 검토 필요" };
  }
  const action = metadata.semantic_evidence?.action_evidence?.status;
  const content = metadata.semantic_evidence?.content_evidence?.status;
  const policy = metadata.release_explanation?.policy;
  return {
    action: action === "grounded" ? "요청 근거 확인됨" : "요청 근거 미확정",
    content: content === "verified" ? "문서 의미 확인됨"
      : content === "not_applicable" ? "문서 의미 해당 없음" : "문서 의미 미검증",
    reason: policy === "neutral_decision_only" ? "판정만 요약 · 의미 미검증"
      : policy === "source_bound" ? "근거 연결 설명" : "원본 설명 · 근거 미확인",
  };
}
