from __future__ import annotations

from datetime import datetime, timezone

from app.alerts.models import Alert, AlertCondition, AlertRule
from app.dashboard.models import DashboardState


_SUPPORTED_METRICS = {
    "avg_confidence",
    "avg_latency_ms",
    "pending_review",
    "violation_count",
    "block_rate",
    "escalation_rate",
    "total_governed_runs",
}


class AlertEngine:
    def __init__(self, rules: list[AlertRule] | None = None) -> None:
        self._rules: list[AlertRule] = rules if rules is not None else []

    @property
    def rules(self) -> list[AlertRule]:
        return list(self._rules)

    def evaluate(self, state: DashboardState) -> list[Alert]:
        fired: list[Alert] = []
        now = datetime.now(timezone.utc).isoformat()
        for rule in self._rules:
            value = self._extract_metric(state, rule.metric)
            if value is None:
                continue
            triggered = (
                value < rule.threshold
                if rule.condition == AlertCondition.BELOW
                else value > rule.threshold
            )
            if triggered:
                fired.append(
                    Alert(
                        rule_name=rule.name,
                        severity=rule.severity,
                        metric=rule.metric,
                        actual_value=round(value, 2),
                        threshold=rule.threshold,
                        message=rule.message or f"{rule.metric} is {rule.condition.value} {rule.threshold}",
                        fired_at=now,
                    )
                )
        return fired

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def clear_rules(self) -> None:
        self._rules.clear()

    def supported_metrics(self) -> set[str]:
        return set(_SUPPORTED_METRICS)

    def _extract_metric(self, state: DashboardState, metric: str) -> float | None:
        total = state.total_governed_runs
        mapping: dict[str, float] = {
            "avg_confidence": state.avg_confidence,
            "avg_latency_ms": state.avg_latency_ms,
            "pending_review": float(state.pending_review),
            "violation_count": float(state.violation_count),
            "block_rate": (state.blocked / total * 100.0) if total else 0.0,
            "escalation_rate": (state.escalated / total * 100.0) if total else 0.0,
            "total_governed_runs": float(total),
        }
        return mapping.get(metric)
