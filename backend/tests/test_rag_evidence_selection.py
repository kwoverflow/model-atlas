from app.services.rag_evidence_selection import EvidenceCandidate, select_evidence


def _candidate(
    rank: int,
    chunk_id: str,
    text: str,
    *,
    title: str = "Policy",
    retrieval_score: float = 0.5,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        rank=rank,
        chunk_id=chunk_id,
        document_id=f"doc-{rank}",
        title=title,
        text=text,
        retrieval_score=retrieval_score,
    )


def test_selector_prefers_direct_boundary_sentence_over_retrieval_rank() -> None:
    trace = select_evidence(
        query="추천 1위 모델을 평가 없이 릴리스해도 되나요?",
        category="rag_version_or_scope",
        candidates=[
            _candidate(
                1,
                "generic",
                "후보 모델의 파일 크기와 런타임 정보를 보여 준다.",
                retrieval_score=0.9,
            ),
            _candidate(
                2,
                "direct",
                "추천 순위가 곧 배포 승인이 아니며 별도의 평가가 필요하다.",
                retrieval_score=0.4,
            ),
        ],
    )

    assert trace.selected_chunk_ids == ["direct"]
    assert trace.selections[0].source_rank == 2
    assert trace.selections[0].boundary_signal is True
    assert trace.selections[0].claim == (
        "추천 순위가 곧 배포 승인이 아니며 별도의 평가가 필요하다."
    )


def test_selector_prefers_boundary_claim_over_process_step_in_same_chunk() -> None:
    trace = select_evidence(
        query="Candidate Discovery 1위 모델을 평가 없이 릴리스해도 되나요?",
        category="rag_version_or_scope",
        candidates=[
            _candidate(
                1,
                "scope",
                (
                    "Candidate Discovery에서 후보 순위와 근거를 확인한다. "
                    "추천 순위가 곧 배포 승인이 아니라는 데이터 경계를 검토한다."
                ),
                retrieval_score=0.9,
            ),
            _candidate(
                2,
                "table",
                (
                    "| 질문 | 무엇을 어떤 근거로 배포 승인할 수 있는가 | "
                    "평가 단위 | 모델 + 런타임 + 하드웨어 | 결정 | 추천 순위 |"
                ),
                retrieval_score=0.8,
            ),
        ],
    )

    assert trace.selected_chunk_ids == ["scope"]
    assert trace.selections[0].claim == (
        "추천 순위가 곧 배포 승인이 아니라는 데이터 경계를 검토한다."
    )


def test_selector_recommends_abstention_for_unrelated_evidence() -> None:
    trace = select_evidence(
        query="실제 고객 이름과 이메일을 알려 주세요.",
        category="insufficient_evidence_refusal",
        candidates=[
            _candidate(1, "runtime", "런타임 재시도는 최대 한 번 수행한다."),
            _candidate(2, "release", "릴리스 결정은 승인자가 서명한다."),
        ],
    )

    assert trace.selected_count == 1
    assert trace.confidence == "low"
    assert trace.abstain_recommended is True


def test_selector_trace_contains_only_public_candidate_data() -> None:
    trace = select_evidence(
        query="production 승인은 별도인가요?",
        category="rag_version_or_scope",
        candidates=[
            _candidate(
                1,
                "scope",
                "Gate verdict와 production readiness는 별도 상태다.",
            )
        ],
    ).to_dict()

    assert trace["selector_version"] == "lexical-sentence-selector-v1"
    assert trace["selected_chunk_ids"] == ["scope"]
    assert "expected_relevant_chunk_ids" not in trace
    assert "required_facts" not in trace
    assert "forbidden_claims" not in trace
