import assert from "node:assert/strict";
import test from "node:test";
import { assistantEvidenceLabels } from "../lib/assistantEvidence.ts";

test("unverified source semantics are never promoted by a bounded reason", () => {
  const value = assistantEvidenceLabels({
    semantic_evidence: { action_evidence: { status: "insufficient" }, content_evidence: { status: "not_applicable" } },
    release_explanation: { policy: "neutral_decision_only" },
  });
  assert.equal(value.action, "요청 근거 미확정");
  assert.equal(value.reason, "판정만 요약 · 의미 미검증");
});

test("outer explanation-only grounding does not verify inner document meaning", () => {
  const value = assistantEvidenceLabels({
    semantic_evidence: { action_evidence: { status: "grounded" }, content_evidence: { status: "unverified" } },
    release_explanation: { policy: "source_bound" },
  });
  assert.equal(value.action, "요청 근거 확인됨");
  assert.equal(value.content, "문서 의미 미검증");
});

test("generation failures cannot display a verified status", () => {
  const value = assistantEvidenceLabels({
    generation_error: "failed",
    semantic_evidence: { action_evidence: { status: "grounded" }, content_evidence: { status: "verified" } },
  });
  assert.equal(value.action, "응답 검증 실패");
  assert.equal(value.content, "문서 의미 미검증");
});

test("legacy records remain explicitly unverified", () => {
  assert.equal(assistantEvidenceLabels({}).reason, "원본 설명 · 근거 미확인");
});
