from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TrustDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    RETRY = "RETRY"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class BrowserResult(BaseModel):
    summary: str
    sources: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_usage: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionEvent(BaseModel):
    step: str
    status: ExecutionStatus
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ExecutionTrace(BaseModel):
    execution_id: str
    query: str
    events: list[ExecutionEvent] = Field(default_factory=list)
    total_duration_ms: float | None = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    decision: TrustDecision
    confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    policy_score: float = 100.0
    violations: list[str] = Field(default_factory=list)
    reason: str = ""
    envelope_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    execution_id: str
    timestamp: str
    decision: TrustDecision
    confidence: float
    risk: RiskLevel
    latency_ms: float
    violations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
