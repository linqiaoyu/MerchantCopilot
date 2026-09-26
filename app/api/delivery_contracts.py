"""Additive, bounded request types for the Android delivery API."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalysisContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal["gmv", "uv", "conversion", "refund_rate", "aov"]
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def ordered_window(self):
        if self.start_date > self.end_date:
            raise ValueError("start_date must not exceed end_date")
        return self


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=8000)
    context: AnalysisContext | None = None

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class MemoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int | None = Field(default=None, ge=1)
