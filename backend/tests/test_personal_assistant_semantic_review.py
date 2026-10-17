import json

import pytest

from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.reviews import ReviewService
from app.services.personal_assistant.sandbox import Sandbox
from app.services.personal_assistant.semantic_grounded_inference import STRATEGY, semantic_schema
from app.services.personal_assistant.stable_inference import public_payload


@pytest.mark.parametrize("content", ["할 일을 추가하지 마", "만약 검토가 끝나면 할 일을 추가해줘"])
def test_split_evidence_survives_review_storage_without_authorizing_changes(tmp_path, content):
    service = ReviewService(Sandbox.create(tmp_path / "review"))
    before = service.state()
    request = f'문서에 "{content}"라는 지시가 적혀 있어. 실행하지 말고 어떤 지시인지 설명만 해줘.'
    proof = semantic_schema(public_payload(request, before))[-1]
    raw = json.dumps(
        {
            "decision": "no_change",
            "intent": None,
            "reason": proof["explanation_evidence"]["reason"],
        }
    )
    review = service.create(
        request,
        lambda *_: {
            "raw_output": raw,
            "schema_valid": True,
            "strategy": STRATEGY,
            "semantic_evidence": proof,
        },
    )
    restored = service.get(review["id"])
    assert restored["metadata"]["semantic_evidence"] == proof
    assert restored["metadata"]["decision"] == "no_change"
    assert restored["raw_output"] == raw and restored["initial_fields"] == {}
    assert restored["fields"] == {} and restored["preview"] is None
    assert service.state() == before
    with pytest.raises(GuardError, match="review_confirmation_required"):
        service.approve_review(
            restored["id"], restored["revision"], restored["content_hash"], "0" * 64
        )
    with pytest.raises(GuardError, match="invalid_review_fields"):
        service.confirm(restored["id"], restored["revision"], restored["content_hash"])
    assert service.state() == before
