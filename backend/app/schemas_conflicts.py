from __future__ import annotations

from datetime import datetime
from pydantic import AwareDatetime, BaseModel, Field, model_validator


class ConflictCreate(BaseModel):
    deadline_at: AwareDatetime
    needed_min: int = Field(ge=0)
    free_min: int = Field(ge=0)
    task_ids: list[str] = Field(default_factory=list)
    options: list[dict] = Field(default_factory=list)

    @model_validator(mode='after')
    def require_shortfall(self):
        if self.free_min >= self.needed_min:
            raise ValueError('A conflict requires free_min < needed_min')
        return self


class ConflictResolve(BaseModel):
    option_type: str = Field(min_length=1, max_length=40)

