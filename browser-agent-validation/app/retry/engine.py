from __future__ import annotations

import random
from typing import Any

from app.models.base import ValidationResult
from app.retry.models import RetryConfig


class RetryEngine:
    """Pure-logic retry helper: delay computation and retryability checks."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self._config = config or RetryConfig()

    @property
    def config(self) -> RetryConfig:
        return self._config

    def delay_ms(self, retry_number: int) -> float:
        """Delay before the *retry_number*-th retry (1-indexed).

        retry_number=1 → initial_delay_ms
        retry_number=2 → initial_delay_ms * backoff_factor
        ...capped at max_delay_ms, optional jitter [0.75, 1.25].
        """
        base = self._config.initial_delay_ms * (
            self._config.backoff_factor ** (retry_number - 1)
        )
        base = min(base, self._config.max_delay_ms)
        if self._config.jitter:
            base *= random.uniform(0.75, 1.25)
        return base

    def is_retryable(self, vr: ValidationResult) -> bool:
        """True if the risk level of this validation result warrants a retry."""
        return vr.risk_level.value in self._config.retryable_risk_levels

    def should_retry(self, attempt: int, vr: ValidationResult) -> bool:
        """True if we have remaining attempts and the failure is retryable."""
        return attempt < self._config.max_attempts and self.is_retryable(vr)

    def summary(self) -> dict[str, Any]:
        c = self._config
        return {
            "max_attempts": c.max_attempts,
            "initial_delay_ms": c.initial_delay_ms,
            "backoff_factor": c.backoff_factor,
            "jitter": c.jitter,
            "max_delay_ms": c.max_delay_ms,
            "retryable_risk_levels": c.retryable_risk_levels,
        }
