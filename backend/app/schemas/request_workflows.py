from typing import Literal

from pydantic import Field, model_validator

from app.schemas.structured_requests import StrictInput, StructuredTicketInput


class StartWorkflow(StrictInput):
    task_id: str
    source: Literal["automated_qa", "participant_self_report"]


class WorkflowBinding(StrictInput):
    expected_revision: int = Field(ge=0, strict=True)


class WorkflowDraft(WorkflowBinding):
    draft: StructuredTicketInput


class FinishWorkflow(WorkflowBinding):
    request_state_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    disposition: Literal["finished", "clarification_requested", "abandoned"]
    assistance: Literal["none_reported", "received", "not_reported", "not_applicable"]
    difficulty: int | None = Field(default=None, ge=1, le=5, strict=True)
    note: str = Field(default="", max_length=2000, strict=True)
    acknowledged: bool = Field(strict=True)

    @model_validator(mode="after")
    def check_feedback(self):
        if not self.acknowledged:
            raise ValueError("explicit acknowledgment required")
        if self.disposition == "abandoned" and not self.note.strip():
            raise ValueError("abandonment reason required")
        return self
