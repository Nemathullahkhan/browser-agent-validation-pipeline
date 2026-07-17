from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.models.base import BrowserResult


class ScenarioResult(BaseModel):
    scenario_name: str
    description: str
    query: str
    raw_result: BrowserResult
    raw_passed: bool
    governed_result: BrowserResult | None = None
    governed_blocked: bool = False
    governed_decision: str = ""
    governance_reason: str = ""
    input_blocked: bool = False
    output_blocked: bool = False


class ScenarioBase(ABC):
    name: str = ""
    description: str = ""
    query: str = ""

    @abstractmethod
    def _raw_result(self) -> BrowserResult:
        ...

    def run(self) -> ScenarioResult:
        from app.agenttrust.exceptions import BlockedError, EscalationError
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.browser_agent.interfaces import BrowserAgentBase
        from app.models.base import TrustDecision

        class _Stub(BrowserAgentBase):
            def __init__(self, result: BrowserResult) -> None:
                self._r = result

            def run(self, query: str) -> BrowserResult:
                return self._r

        raw_result = self._raw_result()
        raw = _Stub(raw_result)
        inner = _Stub(raw_result)
        governed = GovernedBrowserAgent(inner)

        governed_result = None
        governed_blocked = False
        input_blocked = False
        output_blocked = False
        governed_decision = ""
        governance_reason = ""

        try:
            governed_result = governed.run(self.query)
            ov = governed.last_validation
            governed_decision = ov.decision.value if ov else "ALLOW"
        except BlockedError as exc:
            governed_blocked = True
            governance_reason = exc.reason
            governed_decision = "BLOCK"
            iv = governed.last_input_validation
            ov = governed.last_validation
            input_blocked = iv is not None and iv.decision == TrustDecision.BLOCK
            output_blocked = ov is not None and ov.decision == TrustDecision.BLOCK
        except EscalationError as exc:
            governed_blocked = True
            governance_reason = exc.reason
            governed_decision = "HUMAN_REVIEW"
            output_blocked = True

        return ScenarioResult(
            scenario_name=self.name,
            description=self.description,
            query=self.query,
            raw_result=raw.run(self.query),
            raw_passed=True,
            governed_result=governed_result,
            governed_blocked=governed_blocked,
            governed_decision=governed_decision,
            governance_reason=governance_reason,
            input_blocked=input_blocked,
            output_blocked=output_blocked,
        )
