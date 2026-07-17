from __future__ import annotations

from pydantic import BaseModel, Field
from app.retry.models import RetryConfig


class ViolationPenalties(BaseModel):
    high: float = 25.0
    medium: float = 10.0
    low: float = 5.0


class DecisionThresholds(BaseModel):
    block_confidence: float = 50.0
    block_policy_score: float = 60.0
    approve_confidence: float = 90.0
    approve_combined_policy: float = 60.0
    approve_combined_confidence: float = 70.0


class ConfidenceAdjustments(BaseModel):
    initial: float = 80.0
    short_summary_penalty: float = 5.0
    no_sources_penalty: float = 20.0
    invalid_url_penalty: float = 15.0
    per_source_bonus: float = 2.0
    max_source_bonus: float = 10.0
    long_summary_bonus: float = 5.0
    medium_summary_bonus: float = 2.0


class OutputRules(BaseModel):
    min_summary_length: int = 50
    long_summary_threshold: int = 500
    medium_summary_threshold: int = 200


class InputRules(BaseModel):
    max_query_length: int = 2000


class PolicyConfig(BaseModel):
    name: str = "default"
    version: str = "1.0"
    description: str = ""
    penalties: ViolationPenalties = Field(default_factory=ViolationPenalties)
    thresholds: DecisionThresholds = Field(default_factory=DecisionThresholds)
    confidence: ConfidenceAdjustments = Field(default_factory=ConfidenceAdjustments)
    output: OutputRules = Field(default_factory=OutputRules)
    input: InputRules = Field(default_factory=InputRules)
    retry: RetryConfig = Field(default_factory=RetryConfig)
