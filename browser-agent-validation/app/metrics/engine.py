from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.metrics.interfaces import MetricsEngine
from app.models.base import (
    ComparisonResult,
    ExecutionTrace,
    RiskLevel,
    TrustDecision,
    ValidationResult,
)

_RISK_NUMERIC = {
    RiskLevel.LOW: 0.0,
    RiskLevel.MEDIUM: 1.0,
    RiskLevel.HIGH: 2.0,
    RiskLevel.CRITICAL: 3.0,
}


@dataclass
class Metric:
    key: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class LocalMetricsEngine(MetricsEngine):
    """In-memory metrics accumulator that aggregates observations per key."""

    def __init__(self) -> None:
        self._metrics: list[Metric] = []

    # ── Core interface ────────────────────────────────────────────────────────

    def record(self, key: str, value: float | int, tags: dict[str, str] | None = None) -> None:
        self._metrics.append(Metric(key=key, value=float(value), tags=tags or {}))

    def summary(self) -> dict[str, Any]:
        grouped: dict[str, list[float]] = {}
        for m in self._metrics:
            grouped.setdefault(m.key, []).append(m.value)

        result: dict[str, Any] = {}
        for key, values in grouped.items():
            result[key] = {
                "count": len(values),
                "total": sum(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "last": values[-1],
            }
        return result

    def export(self, path: str) -> None:
        Path(path).write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")

    # ── High-level helpers ────────────────────────────────────────────────────

    def record_trace(self, trace: ExecutionTrace, mode: str = "raw") -> None:
        """Record step-level timings and total duration from an ExecutionTrace."""
        for event in trace.events:
            if event.duration_ms is not None:
                self.record(f"step.{event.step}.ms", event.duration_ms, tags={"mode": mode})
        if trace.total_duration_ms is not None:
            self.record("total_latency_ms", trace.total_duration_ms, tags={"mode": mode})

    def record_validation(self, vr: ValidationResult, prefix: str = "governance") -> None:
        """Record confidence, risk, policy score, and decision from a ValidationResult."""
        self.record(f"{prefix}.confidence", vr.confidence)
        self.record(f"{prefix}.policy_score", vr.policy_score)
        self.record(f"{prefix}.violations", float(len(vr.violations)))
        self.record(f"{prefix}.risk", _RISK_NUMERIC.get(vr.risk_level, 0.0))
        self.record(f"{prefix}.decision.allow", 1.0 if vr.decision == TrustDecision.ALLOW else 0.0)
        self.record(f"{prefix}.decision.block", 1.0 if vr.decision == TrustDecision.BLOCK else 0.0)
        self.record(
            f"{prefix}.decision.review",
            1.0 if vr.decision == TrustDecision.HUMAN_REVIEW else 0.0,
        )

    def record_comparison(self, cr: ComparisonResult) -> None:
        """Record metrics from both sides of a ComparisonResult."""
        self.record_trace(cr.raw_trace, mode="raw")
        if cr.governed_trace:
            self.record_trace(cr.governed_trace, mode="governed")
        if cr.input_validation:
            self.record_validation(cr.input_validation, prefix="governance.input")
        if cr.output_validation:
            self.record_validation(cr.output_validation, prefix="governance.output")
        self.record("governance.overhead_ms", cr.governance_overhead_ms)
        if cr.governed_error:
            self.record("run.blocked", 1.0)
        else:
            self.record("run.allowed", 1.0)


# ── Persistence helpers ───────────────────────────────────────────────────────

def save_metrics(engine: LocalMetricsEngine, path: str | Path = "metrics.json") -> Path:
    p = Path(path)
    p.write_text(json.dumps(engine.summary(), indent=2), encoding="utf-8")
    return p


def load_metrics(path: str | Path = "metrics.json") -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
