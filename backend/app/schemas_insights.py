from __future__ import annotations

from pydantic import BaseModel, Field


class InsightsResponse(BaseModel):
    calibration_factors: dict[str, float] = Field(default_factory=dict)
    focus_windows: list[tuple[int, int]] = Field(default_factory=list)
    plan_adherence: float = 0
    overdue_rates: dict[str, float] = Field(default_factory=dict)
    snooze_rates: dict[str, float] = Field(default_factory=dict)
    cold_start: bool = True
    suggestions: list[dict] = Field(default_factory=list)

