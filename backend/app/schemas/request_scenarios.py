from typing import Literal

from pydantic import Field, model_validator

from app.schemas.structured_requests import PriorityChoice, StrictInput


class StudyAnswer(StrictInput):
    decision: Literal["confirm", "clarify"]
    query: str = Field(default="", max_length=1000, strict=True)
    priority: PriorityChoice

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision == "confirm":
            if not self.query.strip() or self.priority.mode == "unresolved":
                raise ValueError("confirmation requires query and explicit priority choice")
        elif self.query != "" or self.priority.mode != "unresolved":
            raise ValueError("clarification must not include executable arguments")
        return self


class StartStudy(StrictInput):
    scenario_id: str
    source: Literal["automated_qa", "participant_self_report"]


class SaveStudy(StrictInput):
    expected_revision: int = Field(ge=0, strict=True)
    answer: StudyAnswer


class SubmitStudy(StrictInput):
    expected_revision: int = Field(ge=1, strict=True)
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledged: bool = Field(strict=True)

    @model_validator(mode="after")
    def require_acknowledgment(self):
        if not self.acknowledged:
            raise ValueError("explicit acknowledgment is required")
        return self
