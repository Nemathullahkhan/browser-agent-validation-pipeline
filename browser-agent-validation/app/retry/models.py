from __future__ import annotations

from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    max_attempts: int = 3
    initial_delay_ms: float = 500.0
    backoff_factor: float = 2.0
    jitter: bool = True
    max_delay_ms: float = 10_000.0
    retryable_risk_levels: list[str] = Field(default_factory=lambda: ["HIGH", "MEDIUM"])


class RetryAttempt(BaseModel):
    attempt: int
    decision: str
    confidence: float
    policy_score: float
    risk_level: str
    delay_ms_after: float = 0.0


class RetryResult(BaseModel):
    total_attempts: int
    final_decision: str
    final_confidence: float
    final_policy_score: float
    retried: bool
    attempts: list[RetryAttempt] = Field(default_factory=list)
