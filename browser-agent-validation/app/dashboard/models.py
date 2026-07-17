from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.audit.store import AuditEvent
from app.review.models import ReviewItem


class DashboardConfig(BaseModel):
    title: str = "AgentTrust Governance Dashboard"
    max_recent_events: int = 10
    max_review_items: int = 5


class DashboardState(BaseModel):
    collected_at: str
    total_governed_runs: int = 0
    allowed: int = 0
    blocked: int = 0
    escalated: int = 0
    avg_confidence: float = 0.0
    avg_latency_ms: float = 0.0
    violation_count: int = 0
    most_common_risk: str = "N/A"
    pending_review: int = 0
    recent_events: list[AuditEvent] = Field(default_factory=list)
    pending_review_items: list[ReviewItem] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    has_comparison: bool = False
