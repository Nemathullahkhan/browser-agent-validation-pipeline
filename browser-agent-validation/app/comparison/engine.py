from __future__ import annotations

import time
import uuid
from pathlib import Path

from app.agenttrust.exceptions import BlockedError, EscalationError
from app.agenttrust.governed_agent import GovernedBrowserAgent
from app.browser_agent.interfaces import BrowserAgentBase
from app.comparison.interfaces import ComparisonRunner
from app.models.base import (
    BrowserResult,
    ComparisonResult,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTrace,
)


def _empty_trace(query: str) -> ExecutionTrace:
    return ExecutionTrace(
        execution_id=str(uuid.uuid4()),
        query=query,
        status=ExecutionStatus.PENDING,
    )


class ComparisonEngine(ComparisonRunner):
    """Runs the same query through a raw agent and a governed agent, then compares."""

    def __init__(
        self,
        raw_agent: BrowserAgentBase,
        governed_agent: GovernedBrowserAgent,
    ) -> None:
        self._raw = raw_agent
        self._governed = governed_agent

    def run_without_trust(self, query: str) -> tuple[BrowserResult, ExecutionTrace]:
        result = self._raw.run(query)
        trace = getattr(self._raw, "last_trace", None) or _empty_trace(query)
        return result, trace

    def run_with_trust(self, query: str) -> tuple[BrowserResult, ExecutionTrace]:
        result = self._governed.run(query)
        trace = getattr(self._governed, "last_trace", None) or _empty_trace(query)
        return result, trace

    def compare(self, query: str) -> ComparisonResult:
        # ── Raw run ───────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        raw_result, raw_trace = self.run_without_trust(query)
        raw_latency = (time.perf_counter() - t0) * 1000

        # ── Governed run ──────────────────────────────────────────────────────
        governed_result: BrowserResult | None = None
        governed_trace: ExecutionTrace | None = None
        governed_error: str | None = None

        t1 = time.perf_counter()
        try:
            governed_result, governed_trace = self.run_with_trust(query)
        except (BlockedError, EscalationError) as exc:
            governed_error = exc.reason
            governed_trace = getattr(self._governed, "last_trace", None)
        governed_latency = (time.perf_counter() - t1) * 1000

        return ComparisonResult(
            query=query,
            raw_result=raw_result,
            raw_trace=raw_trace,
            governed_result=governed_result,
            governed_trace=governed_trace,
            governed_decision=(
                self._governed.last_validation.decision.value
                if self._governed.last_validation
                else None
            ),
            input_validation=self._governed.last_input_validation,
            output_validation=self._governed.last_validation,
            governed_error=governed_error,
            raw_latency_ms=raw_latency,
            governed_latency_ms=governed_latency,
            governance_overhead_ms=governed_latency - raw_latency,
        )


def save_comparison(result: ComparisonResult, path: str | Path = "comparison.json") -> Path:
    p = Path(path)
    p.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_comparison(path: str | Path = "comparison.json") -> ComparisonResult:
    p = Path(path)
    return ComparisonResult.model_validate_json(p.read_text(encoding="utf-8"))
