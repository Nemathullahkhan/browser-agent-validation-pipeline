from __future__ import annotations

from app.alerts.models import Alert, AlertCondition, AlertRule, AlertSeverity

_DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        name="Low Average Confidence",
        metric="avg_confidence",
        condition=AlertCondition.BELOW,
        threshold=60.0,
        severity=AlertSeverity.WARNING,
        message="Average confidence has dropped below 60 — review recent outputs.",
    ),
    AlertRule(
        name="Critical Block Rate",
        metric="block_rate",
        condition=AlertCondition.ABOVE,
        threshold=80.0,
        severity=AlertSeverity.CRITICAL,
        message="Over 80% of governed runs are being blocked — policy may be misconfigured.",
    ),
    AlertRule(
        name="High Block Rate",
        metric="block_rate",
        condition=AlertCondition.ABOVE,
        threshold=50.0,
        severity=AlertSeverity.WARNING,
        message="More than half of governed runs are being blocked.",
    ),
    AlertRule(
        name="Review Queue Backlog",
        metric="pending_review",
        condition=AlertCondition.ABOVE,
        threshold=10.0,
        severity=AlertSeverity.INFO,
        message="Review queue has over 10 pending items — consider triaging.",
    ),
    AlertRule(
        name="High Escalation Rate",
        metric="escalation_rate",
        condition=AlertCondition.ABOVE,
        threshold=30.0,
        severity=AlertSeverity.WARNING,
        message="More than 30% of runs are being escalated for human review.",
    ),
]


def default_rules() -> list[AlertRule]:
    return list(_DEFAULT_RULES)
