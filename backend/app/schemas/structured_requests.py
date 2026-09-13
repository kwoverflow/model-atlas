from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssignedPriority(StrictInput):
    mode: Literal["set"]
    value: Literal["low", "normal", "high"]


class OmittedPriority(StrictInput):
    mode: Literal["omit"]


class UnresolvedPriority(StrictInput):
    mode: Literal["unresolved"]


PriorityChoice = Annotated[
    AssignedPriority | OmittedPriority | UnresolvedPriority, Field(discriminator="mode")
]


class StructuredTicketInput(StrictInput):
    original_request: str = Field(min_length=1, max_length=4000, strict=True)
    query: str = Field(min_length=1, max_length=1000, strict=True)
    priority: PriorityChoice

    @field_validator("original_request", "query")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request and query must not be blank")
        return value


class ContractBinding(StrictInput):
    expected_revision: int = Field(ge=1, strict=True)
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContractEdit(ContractBinding):
    draft: StructuredTicketInput


class ContractConfirmation(ContractBinding):
    acknowledged: Literal[True]

    @field_validator("acknowledged", mode="before")
    @classmethod
    def explicit_boolean(cls, value):
        if value is not True:
            raise ValueError("confirmation requires the boolean true")
        return value


class ProposalCheck(ContractBinding):
    proposal: str = Field(min_length=1, max_length=16000, strict=True)
