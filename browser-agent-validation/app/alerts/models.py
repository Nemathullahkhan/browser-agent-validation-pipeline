from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertCondition(str, Enum):
    BELOW = "below"
    ABOVE = "above"


class AlertRule(BaseModel):
    name: str
    metric: str
    condition: AlertCondition
    threshold: float
    severity: AlertSeverity = AlertSeverity.WARNING
    message: str = ""


class Alert(BaseModel):
    rule_name: str
    severity: AlertSeverity
    metric: str
    actual_value: float
    threshold: float
    message: str
    fired_at: str
