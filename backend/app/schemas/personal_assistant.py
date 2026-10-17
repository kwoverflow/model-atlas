from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request: str = Field(min_length=1, max_length=4000)


class ReviewBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)


class ReviewEdit(ReviewBinding):
    fields: dict[str, Any]


class ReviewConfirmation(ReviewBinding):
    acknowledged: Literal[True]


class ReviewApproval(ReviewBinding):
    plan_hash: str = Field(min_length=64, max_length=64)
