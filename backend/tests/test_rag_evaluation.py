import json
from uuid import uuid4

from app.models import DeploymentConfiguration, EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS,
    DEFAULT_RAG_CORPUS_REGISTRY,
    attach_rag_evaluation,
    evaluate_rag_output,
    prepare_rag_execution,
    retrieve,
    summarize_rag_traces,
)


def _configuration(**retrieval_overrides: object) -> DeploymentConfiguration:
    retrieval_config = {
        "corpus_id": DEFAULT_RAG_CORPUS.corpus_id,
        "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
        "retriever_id": "lexical_overlap",
        "retriever_version": "lexical-overlap-v1",
        "top_k": 3,
        "min_score": 0.05,
        **retrieval_overrides,
    }
    return DeploymentConfiguration(
        name="RAG test configuration",
        workload_profile_id=uuid4(),
        hardware_profile_id=uuid4(),
        model_artifact_id=uuid4(),
        runtime_name="mock",
        runtime_version="test",
        runtime_config_json={},
        context_length=4096,
        generation_config_json={},
        prompt_bundle_json={},
        output_schema_version="rag-answer-v1",
        tool_schema_version=None,
        retrieval_config_json=retrieval_config,
        concurrency_target=1,
        configuration_hash="test-hash",
        status="ready",
        notes=None,
    )


def _case() -> EvaluationCase:
    return EvaluationCase(
        evaluation_suite_id=uuid4(),
        external_case_id="rag-case-001",
        category="rag_grounded_answer",
        title="Release requirement",
        input_payload_json={"query": "approved deployment gate baseline promotion"},
        expected_output_json={
            "type": "object",
            "required": ["answer", "citations", "claims"],
        },
        reference_context_json={
            "rag": {
                "corpus_id": DEFAULT_RAG_CORPUS.corpus_id,
                "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
                "relevant_chunk_ids": ["ops-release-001"],
                "expected_facts": [
                    "A release requires an approved deployment gate and verified evidence before "
                    "baseline promotion."
                ],
            }
        },
        expected_tool_schema_json=None,
        tags_json=["rag"],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="local_authored",
    )


def _adapter_result(output: dict | str) -> AdapterCaseResult:
    serialized = output if isinstance(output, str) else json.dumps(output)
    return AdapterCaseResult(
        raw_output=serialized,
        normalized_output=serialized,
        quality_score=None,
        exact_match=None,
        json_valid=isinstance(output, dict),
        tool_call_valid=False,
        groundedness_score=None,
        faithfulness_score=None,
        human_label=None,
        error_type=None,
        ttft_ms=10,
        end_to_end_latency_ms=20,
        prompt_tokens=20,
        completion_tokens=20,
        tokens_per_second=1000,
        gpu_vram_used_mb=None,
        gpu_utilization_pct=None,
        cpu_utilization_pct=None,
        peak_memory_mb=None,
        oom_occurred=False,
        retry_count=0,
    )


def test_default_corpus_has_stable_versioned_descriptor() -> None:
    descriptor = DEFAULT_RAG_CORPUS_REGISTRY.descriptor()

    assert descriptor["registry_version"] == "rag-corpus-registry-v1"
    assert descriptor["corpus_count"] == 1
    assert descriptor["corpora"][0]["corpus_version"] == "ops-handbook-v1"
    assert descriptor["corpora"][0]["chunk_count"] == 12
    assert len(descriptor["corpora"][0]["corpus_hash"]) == 64


def test_lexical_retriever_returns_relevant_chunk_and_recall() -> None:
    trace = retrieve(
        corpus=DEFAULT_RAG_CORPUS,
        query="approved deployment gate baseline promotion",
        relevant_chunk_ids=["ops-release-001"],
        top_k=3,
        min_score=0.05,
    )

    assert trace.status == "success"
    assert trace.retrieved_chunks[0].chunk_id == "ops-release-001"
    assert trace.retrieval_recall == 1.0
    assert trace.relevant_retrieved_chunk_ids == ["ops-release-001"]


def test_any_of_evidence_contract_accepts_an_alternative_citation() -> None:
    trace = retrieve(
        corpus=DEFAULT_RAG_CORPUS,
        query="critical evaluation cases explicit review production readiness",
        relevant_chunk_ids=["ops-release-001"],
        acceptable_evidence_groups=[
            ["ops-release-001"],
            ["ops-review-001"],
        ],
        evidence_contract_version="rag-evidence-contract-v2",
        top_k=1,
        min_score=0.05,
    )
    claim = trace.retrieved_chunks[0].text
    evaluation = evaluate_rag_output(
        json.dumps(
            {
                "answer": claim,
                "citations": ["ops-review-001"],
                "claims": [claim],
            }
        ),
        trace,
    )

    assert trace.relevant_retrieved_chunk_ids == []
    assert trace.retrieval_contract_satisfied is True
    assert trace.satisfied_evidence_group_index == 1
    assert trace.retrieval_recall == 1.0
    assert evaluation.citation_contract_satisfied is True
    assert evaluation.satisfied_citation_group_index == 1
    assert evaluation.citation_precision == 1.0
    assert evaluation.citation_recall == 1.0
    assert evaluation.successful is True


def test_preparation_exposes_retrieved_context_but_not_ground_truth() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())

    assert preparation is not None
    rag_context = preparation.adapter_input_payload["rag_context"]
    assert rag_context["retrieved_chunks"]
    assert "relevant_chunk_ids" not in rag_context
    assert rag_context["evidence_selection"]["selected_count"] == 1
    assert "expected_relevant_chunk_ids" not in rag_context["evidence_selection"]
    assert rag_context["evidence_selection"]["applied_to_generation"] is False
    assert preparation.retrieval_trace.evidence_selection_recall == 1.0
    assert "expected_facts" not in preparation.adapter_reference_context
    assert preparation.retrieval_trace.retrieval_recall == 1.0


def test_perfect_citations_and_claims_produce_successful_trace() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text
    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": claim,
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
    )

    assert trace.successful is True
    assert trace.citation_precision == 1.0
    assert trace.citation_recall == 1.0
    assert trace.groundedness_score == 1.0
    assert trace.unsupported_claim_rate == 0.0
    assert trace.semantic_contract_declared is False
    assert trace.semantic_contract_satisfied is True


def test_grounded_refusal_satisfies_semantic_contract() -> None:
    case = _case()
    case.expected_output_json = {
        "must_refuse": True,
        "required_facts": ["verified evidence before baseline promotion"],
        "forbidden_claims": ["release can skip deployment gate"],
    }
    preparation = prepare_rag_execution(_configuration(), case)
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text

    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": (
                    "I cannot confirm an exception because verified evidence is required "
                    "before baseline promotion."
                ),
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        expected_output=case.expected_output_json,
    )

    assert trace.schema_version == "rag-evaluation-trace-v5"
    assert trace.successful is True
    assert trace.semantic_contract_declared is True
    assert trace.semantic_contract_satisfied is True
    assert trace.must_refuse is True
    assert trace.refusal_detected is True
    assert trace.refusal_requirement_satisfied is True
    assert trace.required_fact_coverage == 1.0
    assert trace.forbidden_claim_violation_count == 0


def test_grounded_answer_fails_when_required_refusal_is_missing() -> None:
    case = _case()
    case.expected_output_json = {
        "must_refuse": True,
        "required_facts": ["approved deployment gate and verified evidence"],
        "forbidden_claims": [],
    }
    preparation = prepare_rag_execution(_configuration(), case)
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text

    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": claim,
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        expected_output=case.expected_output_json,
    )

    assert trace.citation_precision == 1.0
    assert trace.groundedness_score == 1.0
    assert trace.refusal_detected is False
    assert trace.refusal_requirement_satisfied is False
    assert trace.semantic_contract_satisfied is False
    assert trace.successful is False


def test_any_of_required_fact_contract_accepts_a_reviewed_alternative() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text

    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": claim,
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        expected_output={
            "semantic_contract_version": "rag-semantic-contract-v2",
            "must_refuse": False,
            "required_facts": ["unrelated primary wording"],
            "acceptable_required_fact_groups": [
                ["unrelated primary wording"],
                ["approved deployment gate and verified evidence"],
            ],
            "forbidden_claims": [],
        },
    )

    assert trace.semantic_contract_version == "rag-semantic-contract-v2"
    assert trace.required_fact_contract_satisfied is True
    assert trace.satisfied_required_fact_group_index == 1
    assert trace.required_fact_coverage == 1.0
    assert trace.successful is True


def test_bounded_answer_contract_rejects_answer_and_claim_contradiction() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text
    answer_contract = {
        "contract_version": "rag-bounded-answer-contract-v1",
        "strategy": "scope-boundary-v1",
        "answer": "Bounded source-derived answer.",
    }

    mismatched = evaluate_rag_output(
        json.dumps(
            {
                "answer": "Yes.",
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        answer_contract=answer_contract,
    )
    matched = evaluate_rag_output(
        json.dumps(
            {
                "answer": "Bounded source-derived answer.",
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        answer_contract=answer_contract,
    )

    assert mismatched.answer_contract_applied is True
    assert mismatched.answer_contract_satisfied is False
    assert mismatched.successful is False
    assert matched.answer_contract_satisfied is True
    assert matched.successful is True


def test_forbidden_claim_match_ignores_an_explicit_negation() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text

    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": "A release cannot skip the deployment gate.",
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        expected_output={
            "must_refuse": False,
            "required_facts": ["approved deployment gate"],
            "forbidden_claims": ["release can skip deployment gate"],
        },
    )

    assert trace.forbidden_claim_results[0]["score"] >= 0.75
    assert trace.forbidden_claim_results[0]["negated"] is True
    assert trace.forbidden_claim_violation_count == 0
    assert trace.semantic_contract_satisfied is True


def test_semantic_contract_normalizes_bilingual_status_tokens() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text

    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": (
                    "Gate APPROVED와 PRODUCTION_READINESS_NOT_PRODUCTION_READY는 별도입니다."
                ),
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        expected_output={
            "must_refuse": False,
            "required_facts": ["production readiness는 별도"],
            "forbidden_claims": ["APPROVED는 항상 production-ready"],
        },
    )

    assert trace.required_fact_coverage == 1.0
    assert trace.forbidden_claim_violation_count == 0
    assert trace.semantic_contract_satisfied is True


def test_forbidden_claim_match_recognizes_underscored_negation() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text

    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": "Gate APPROVED; Production Readiness: NOT_PRODUCTION_READY.",
                "citations": ["ops-release-001"],
                "claims": [claim],
            }
        ),
        preparation.retrieval_trace,
        expected_output={
            "must_refuse": False,
            "required_facts": [],
            "forbidden_claims": ["APPROVED는 항상 production-ready"],
        },
    )

    assert trace.forbidden_claim_results[0]["negated"] is True
    assert trace.forbidden_claim_violation_count == 0
    assert trace.semantic_contract_satisfied is True


def test_invalid_citation_and_unsupported_claim_fail_trace() -> None:
    preparation = prepare_rag_execution(_configuration(), _case())
    assert preparation is not None
    trace = evaluate_rag_output(
        json.dumps(
            {
                "answer": "The release can skip every gate.",
                "citations": ["missing-chunk"],
                "claims": ["The release can skip every gate."],
            }
        ),
        preparation.retrieval_trace,
    )

    assert trace.successful is False
    assert trace.invalid_citation_ids == ["missing-chunk"]
    assert trace.citation_precision == 0.0
    assert trace.groundedness_score == 0.0
    assert trace.unsupported_claim_rate == 1.0


def test_invalid_retrieval_configuration_is_preserved_as_evidence() -> None:
    preparation = prepare_rag_execution(
        _configuration(retriever_version="unknown-v9"),
        _case(),
    )

    assert preparation is not None
    assert preparation.retrieval_trace.status == "invalid_config"
    assert preparation.retrieval_trace.retrieved_chunks == []
    assert "retriever version unknown-v9 is not supported" in preparation.retrieval_trace.errors


def test_attachment_and_summary_preserve_rag_provenance() -> None:
    case = _case()
    preparation = prepare_rag_execution(_configuration(), case)
    assert preparation is not None
    claim = preparation.retrieval_trace.retrieved_chunks[0].text
    result = _adapter_result(
        {
            "answer": claim,
            "citations": ["ops-release-001"],
            "claims": [claim],
        }
    )

    attached = attach_rag_evaluation(case, result, preparation)
    trace = attached.metadata["rag_evaluation"]
    summary = summarize_rag_traces([trace])

    assert attached.exact_match is True
    assert attached.groundedness_score == 1.0
    assert attached.metadata["rag_corpus"]["corpus_version"] == "ops-handbook-v1"
    assert attached.metadata["retriever_descriptor"]["retriever_version"] == "lexical-overlap-v1"
    assert attached.logs[-1]["event_type"] == "rag_evaluation_completed"
    assert summary["rag_case_count"] == 1
    assert summary["average_retrieval_recall"] == 1.0
    assert summary["average_unsupported_claim_rate"] == 0.0
    assert summary["schema_version"] == "rag-evaluation-summary-v5"
    assert summary["average_evidence_selection_recall"] == 1.0
    assert summary["semantic_contract_case_count"] == 0
