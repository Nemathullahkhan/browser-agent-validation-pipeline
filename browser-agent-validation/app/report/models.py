from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.audit.store import AuditEvent
from app.comparison.engine import ComparisonResult
from app.models.base import TrustDecision
from app.review.models import ReviewItem


class ReportConfig(BaseModel):
    title: str = "AgentTrust Session Report"
    include_audit: bool = True
    include_metrics: bool = True
    include_comparison: bool = True
    include_review: bool = True
    max_audit_events: int = 50


class ReportSummary(BaseModel):
    total_governed_runs: int = 0
    allowed: int = 0
    blocked: int = 0
    escalated: int = 0
    avg_confidence: float = 0.0
    avg_latency_ms: float = 0.0
    violation_count: int = 0
    most_common_risk: str = "N/A"


class SessionReport(BaseModel):
    title: str
    generated_at: str
    summary: ReportSummary
    audit_events: list[AuditEvent] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    comparison: ComparisonResult | None = None
    review_items: list[ReviewItem] = Field(default_factory=list)
