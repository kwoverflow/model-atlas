from app.models import EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.result_scoring import (
    ResultScorerRegistry,
    ScoringOutcome,
    TextPresenceScorer,
    score_case_result,
)


def _result(
    *,
    output: str,
    json_valid: bool = False,
    tool_call_valid: bool = False,
) -> AdapterCaseResult:
    return AdapterCaseResult(
        raw_output=output,
        normalized_output=output,
        quality_score=None,
        exact_match=None,
        json_valid=json_valid,
        tool_call_valid=tool_call_valid,
        groundedness_score=None,
        faithfulness_score=None,
        human_label="captured-needs-scoring",
        error_type=None,
        ttft_ms=1.0,
        end_to_end_latency_ms=1.0,
        prompt_tokens=1,
        completion_tokens=1,
        tokens_per_second=1.0,
        gpu_vram_used_mb=0.0,
        gpu_utilization_pct=None,
        cpu_utilization_pct=None,
        peak_memory_mb=None,
        oom_occurred=False,
        retry_count=0,
        metadata={"adapter": "test"},
    )


class AlwaysPassScorer:
    scorer_id = "always_pass"
    method = "test_override"

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        return True

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        return ScoringOutcome(
            quality=0.91,
            groundedness=0.92,
            faithfulness=0.93,
            method=self.method,
            scorer_id=self.scorer_id,
            details={"source": "custom_registry"},
        )


def test_scorer_fills_json_quality_from_schema_coverage() -> None:
    case = EvaluationCase(
        external_case_id="json-1",
        category="json_extraction",
        title="json",
        input_payload_json={"document": "answer evidence confidence"},
        expected_output_json={
            "type": "object",
            "required": ["answer", "confidence", "evidence"],
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"},
            },
        },
        reference_context_json={"required_keys": ["answer", "confidence", "evidence"]},
        expected_tool_schema_json=None,
        tags_json=[],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="captured_local",
    )

    scored = score_case_result(
        case,
        _result(
            output='{"answer":"완료","confidence":0.91,"evidence":"doc-1"}',
            json_valid=True,
        ),
    )

    assert scored.quality_score == 1.0
    assert scored.groundedness_score == 1.0
    assert scored.faithfulness_score == 1.0
    assert scored.human_label == "heuristic-pass"
    assert scored.metadata["scorer"]["method"] == "json_schema_coverage"


def test_scorer_penalizes_wrong_tool_name() -> None:
    case = EvaluationCase(
        external_case_id="tool-1",
        category="tool_selection",
        title="tool",
        input_payload_json={"request": "정책 확인"},
        expected_output_json=None,
        reference_context_json={"expected_tool": "lookup_policy"},
        expected_tool_schema_json={
            "tool_name": "lookup_policy",
            "arguments": {"required": ["query"]},
        },
        tags_json=[],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="captured_local",
    )

    scored = score_case_result(
        case,
        _result(
            output='{"tool_name":"create_ticket","arguments":{"query":"정책"}}',
            json_valid=True,
            tool_call_valid=True,
        ),
    )

    assert scored.quality_score == 0.65
    assert scored.human_label == "heuristic-fail"
    assert scored.metadata["scorer"]["details"]["tool_match"] == 0.0


def test_scorer_scores_grounded_answer_from_reference_facts() -> None:
    case = EvaluationCase(
        external_case_id="qa-1",
        category="grounded_answer",
        title="qa",
        input_payload_json={
            "document": "배포 영향 범위는 관리자 콘솔이고 담당자는 플랫폼 팀입니다."
        },
        expected_output_json=None,
        reference_context_json={"facts": ["관리자 콘솔", "플랫폼 팀"]},
        expected_tool_schema_json=None,
        tags_json=[],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="captured_local",
    )

    scored = score_case_result(
        case,
        _result(output="배포 영향 범위는 관리자 콘솔이며 담당자는 플랫폼 팀입니다."),
    )

    assert scored.quality_score >= 0.9
    assert scored.groundedness_score >= 0.9
    assert scored.faithfulness_score >= 0.9
    assert scored.human_label == "heuristic-pass"


def test_scorer_registry_supports_custom_scorers() -> None:
    case = EvaluationCase(
        external_case_id="custom-1",
        category="custom_eval",
        title="custom",
        input_payload_json={"input": "score through custom scorer"},
        expected_output_json=None,
        reference_context_json=None,
        expected_tool_schema_json=None,
        tags_json=[],
        criticality="standard",
        weight=1.0,
        is_active=True,
        data_source="captured_local",
    )
    registry = ResultScorerRegistry(
        scorers=[AlwaysPassScorer()],
        fallback_scorer=TextPresenceScorer(),
        registry_id="test_registry",
    )

    scored = score_case_result(case, _result(output="anything"), registry=registry)

    assert scored.quality_score == 0.91
    assert scored.groundedness_score == 0.92
    assert scored.faithfulness_score == 0.93
    assert scored.human_label == "heuristic-pass"
    assert scored.metadata["scorer"]["registry_id"] == "test_registry"
    assert scored.metadata["scorer"]["scorer_id"] == "always_pass"
