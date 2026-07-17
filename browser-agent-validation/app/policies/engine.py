from __future__ import annotations

from typing import Any

from app.policies.loader import load_policy
from app.policies.models import PolicyConfig


class PolicyEngine:
    """Evaluates governance decisions against a loaded policy configuration."""

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self._config = config or load_policy()

    @property
    def config(self) -> PolicyConfig:
        return self._config

    def penalty_for(self, severity: str) -> float:
        p = self._config.penalties
        return {"HIGH": p.high, "MEDIUM": p.medium, "LOW": p.low}.get(severity.upper(), 0.0)

    def is_block_confidence(self, confidence: float) -> bool:
        return confidence < self._config.thresholds.block_confidence

    def is_block_policy_score(self, score: float) -> bool:
        return score < self._config.thresholds.block_policy_score

    def is_auto_approve_confidence(self, confidence: float) -> bool:
        return confidence >= self._config.thresholds.approve_confidence

    def is_combined_approve(self, score: float, confidence: float) -> bool:
        t = self._config.thresholds
        return score >= t.approve_combined_policy and confidence >= t.approve_combined_confidence

    def summary(self) -> dict[str, Any]:
        c = self._config
        return {
            "name": c.name,
            "version": c.version,
            "description": c.description,
            "thresholds": c.thresholds.model_dump(),
            "penalties": c.penalties.model_dump(),
            "confidence": c.confidence.model_dump(),
            "input": c.input.model_dump(),
            "output": c.output.model_dump(),
        }
