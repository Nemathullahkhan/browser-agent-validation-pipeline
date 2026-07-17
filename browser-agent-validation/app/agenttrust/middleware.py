from __future__ import annotations

from app.agenttrust.exceptions import BlockedError, EscalationError
from app.agenttrust.interfaces import TrustMiddleware
from app.agenttrust.validation import ValidationContext
from app.models.base import BrowserResult, TrustDecision, ValidationResult


class AgentTrustMiddleware(TrustMiddleware):
    """Stateless AgentTrust middleware — validates and enforces governance decisions."""

    def validate(self, query: str, result: BrowserResult) -> ValidationResult:
        ctx = ValidationContext()
        ctx.check_query(query)
        ctx.check_result(result)
        return ctx.finalize()

    def wrap(self, query: str, result: BrowserResult) -> BrowserResult:
        """Validate the result and enforce the decision.

        Raises BlockedError on BLOCK, EscalationError on HUMAN_REVIEW.
        Returns a BrowserResult annotated with governance metadata on ALLOW.
        """
        vr = self.validate(query, result)

        if vr.decision == TrustDecision.BLOCK:
            raise BlockedError(vr.reason, vr)

        if vr.decision == TrustDecision.HUMAN_REVIEW:
            raise EscalationError(vr.reason, vr)

        return result.model_copy(
            update={
                "metadata": {
                    **result.metadata,
                    "agentrust": {
                        "decision": vr.decision.value,
                        "confidence": round(vr.confidence, 1),
                        "policy_score": round(vr.policy_score, 1),
                        "risk_level": vr.risk_level.value,
                        "envelope_id": vr.envelope_id,
                    },
                }
            }
        )
