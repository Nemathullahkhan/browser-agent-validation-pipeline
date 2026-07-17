from __future__ import annotations

import time

from app.agenttrust.exceptions import BlockedError, EscalationError
from app.agenttrust.input_validator import InputValidator
from app.agenttrust.interfaces import TrustMiddleware
from app.agenttrust.middleware import AgentTrustMiddleware
from app.browser_agent.interfaces import BrowserAgentBase
from app.models.base import BrowserResult, ExecutionTrace, TrustDecision, ValidationResult
from app.retry.engine import RetryEngine
from app.retry.models import RetryAttempt, RetryResult


class GovernedBrowserAgent:
    """Wraps a BrowserAgentBase with two-stage AgentTrust governance.

    Stage 1 (pre-run):  InputValidator gates the query before the agent runs.
    Stage 2 (post-run): AgentTrustMiddleware validates the result.
    Retry:              Optional RetryEngine retries on retryable BLOCK decisions.

    Architecture: User → InputValidator → BrowserAgent → Middleware → Response
    The inner agent is never modified.
    """

    def __init__(
        self,
        agent: BrowserAgentBase,
        middleware: TrustMiddleware | None = None,
        input_validator: InputValidator | None = None,
        retry_engine: RetryEngine | None = None,
    ) -> None:
        self._agent = agent
        self._middleware = middleware or AgentTrustMiddleware()
        self._input_validator = input_validator or InputValidator()
        self._retry_engine = retry_engine
        self._last_input_validation: ValidationResult | None = None
        self._last_validation: ValidationResult | None = None
        self._last_retry_result: RetryResult | None = None

    @property
    def last_trace(self) -> ExecutionTrace | None:
        return getattr(self._agent, "last_trace", None)

    @property
    def last_input_validation(self) -> ValidationResult | None:
        """ValidationResult from the pre-run input check."""
        return self._last_input_validation

    @property
    def last_validation(self) -> ValidationResult | None:
        """ValidationResult from the post-run output check."""
        return self._last_validation

    @property
    def last_retry_result(self) -> RetryResult | None:
        """RetryResult when a retry engine was involved in a BLOCK decision."""
        return self._last_retry_result

    def run(self, query: str) -> BrowserResult:
        self._last_retry_result = None

        # ── Stage 1: Input validation (pre-run) ──────────────────────────────
        input_vr = self._input_validator.validate(query)
        self._last_input_validation = input_vr

        if input_vr.decision == TrustDecision.BLOCK:
            raise BlockedError(input_vr.reason, input_vr)

        if input_vr.decision == TrustDecision.HUMAN_REVIEW:
            raise EscalationError(input_vr.reason, input_vr)

        # ── Agent runs only after input is approved ───────────────────────────
        result = self._agent.run(query)

        # ── Stage 2: Output validation (post-run) with optional retry ─────────
        output_vr = self._middleware.validate(query, result)
        self._last_validation = output_vr

        if self._retry_engine and output_vr.decision == TrustDecision.BLOCK:
            result, output_vr = self._run_retry_loop(query, result, output_vr)
            self._last_validation = output_vr

        if output_vr.decision == TrustDecision.BLOCK:
            raise BlockedError(output_vr.reason, output_vr)

        if output_vr.decision == TrustDecision.HUMAN_REVIEW:
            raise EscalationError(output_vr.reason, output_vr)

        return result.model_copy(
            update={
                "metadata": {
                    **result.metadata,
                    "agentrust": {
                        "decision": output_vr.decision.value,
                        "confidence": round(output_vr.confidence, 1),
                        "policy_score": round(output_vr.policy_score, 1),
                        "risk_level": output_vr.risk_level.value,
                        "envelope_id": output_vr.envelope_id,
                        "input_validation": {
                            "decision": input_vr.decision.value,
                            "confidence": round(input_vr.confidence, 1),
                            "policy_score": round(input_vr.policy_score, 1),
                            "checks_passed": input_vr.metadata.get("checks_passed"),
                            "checks_run": input_vr.metadata.get("checks_run"),
                        },
                    },
                }
            }
        )

    def _run_retry_loop(
        self,
        query: str,
        initial_result: BrowserResult,
        initial_vr: ValidationResult,
    ) -> tuple[BrowserResult, ValidationResult]:
        engine = self._retry_engine
        assert engine is not None

        attempts: list[RetryAttempt] = []
        attempt = 1
        current_result = initial_result
        current_vr = initial_vr

        while True:
            will_retry = (
                current_vr.decision == TrustDecision.BLOCK
                and engine.should_retry(attempt, current_vr)
            )
            delay = engine.delay_ms(attempt) if will_retry else 0.0
            attempts.append(RetryAttempt(
                attempt=attempt,
                decision=current_vr.decision.value,
                confidence=current_vr.confidence,
                policy_score=current_vr.policy_score,
                risk_level=current_vr.risk_level.value,
                delay_ms_after=delay,
            ))
            if not will_retry:
                break
            time.sleep(delay / 1000.0)
            attempt += 1
            current_result = self._agent.run(query)
            current_vr = self._middleware.validate(query, current_result)

        self._last_retry_result = RetryResult(
            total_attempts=len(attempts),
            final_decision=current_vr.decision.value,
            final_confidence=current_vr.confidence,
            final_policy_score=current_vr.policy_score,
            retried=len(attempts) > 1,
            attempts=attempts,
        )
        return current_result, current_vr
