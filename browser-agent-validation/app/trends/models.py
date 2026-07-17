from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    DEGRADING = "degrading"
    STABLE = "stable"


class TrendPoint(BaseModel):
    timestamp: str
    value: float


class MetricTrend(BaseModel):
    metric: str
    direction: TrendDirection
    first_value: float
    last_value: float
    change_pct: float
    data_points: list[TrendPoint] = Field(default_factory=list)


class TrendReport(BaseModel):
    analyzed_at: str
    event_count: int = 0
    trends: dict[str, MetricTrend] = Field(default_factory=dict)
