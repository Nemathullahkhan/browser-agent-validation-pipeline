from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ComponentCheck(BaseModel):
    name: str
    status: HealthStatus
    message: str = ""
    detail: str = ""


class HealthReport(BaseModel):
    checked_at: str
    overall: HealthStatus
    components: list[ComponentCheck] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.overall == HealthStatus.HEALTHY

    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.components if c.status == HealthStatus.HEALTHY)

    @property
    def degraded_count(self) -> int:
        return sum(1 for c in self.components if c.status == HealthStatus.DEGRADED)
