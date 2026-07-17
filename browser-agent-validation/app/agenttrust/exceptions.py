from __future__ import annotations

from app.models.base import ValidationResult


class BlockedError(Exception):
    """Raised when AgentTrust blocks a response."""

    def __init__(self, reason: str, validation: ValidationResult) -> None:
        super().__init__(reason)
        self.reason = reason
        self.validation = validation


class EscalationError(Exception):
    """Raised when AgentTrust escalates to human review."""

    def __init__(self, reason: str, validation: ValidationResult) -> None:
        super().__init__(reason)
        self.reason = reason
        self.validation = validation
