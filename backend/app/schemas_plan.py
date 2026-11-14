from __future__ import annotations

from datetime import datetime
from pydantic import AwareDatetime, BaseModel, Field, model_validator


class PlanTaskInput(BaseModel):
    id: str
    effort_min: int = Field(ge=5, le=600)
    deadline: AwareDatetime
    priority_score: float = Field(ge=0, le=100)
    blocked: bool = False


class BusyInput(BaseModel):
    start: AwareDatetime
    end: AwareDatetime


class PlanGenerateRequest(BaseModel):
    window_start: AwareDatetime
    window_end: AwareDatetime
    working_hours: list[tuple[int, int]] = [(9, 18)]
    busy: list[BusyInput] = Field(default_factory=list)
    tasks: list[PlanTaskInput] = Field(default_factory=list)


    @model_validator(mode='after')
    def unique_tasks(self):
        if len({task.id for task in self.tasks}) != len(self.tasks):
            raise ValueError('Task IDs must be unique')
        return self
