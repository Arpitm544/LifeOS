from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class InsightsResponse(BaseModel):
    calibration_factors: dict[str, float] = Field(default_factory=dict)
    focus_windows: list[tuple[int, int]] = Field(default_factory=list)
    plan_adherence: float = 0
    overdue_rates: dict[str, float] = Field(default_factory=dict)
    snooze_rates: dict[str, float] = Field(default_factory=dict)
    cold_start: bool = True
    completed_14d: int = 0
    completion_rate: Optional[float] = None
    planned_blocks_14d: int = 0
    completion_chart: list[dict] = Field(default_factory=list)
    samples: int = 0
    suggestions: list[dict] = Field(default_factory=list)
