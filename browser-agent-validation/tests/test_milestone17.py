from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.alerts.defaults import default_rules
from app.alerts.engine import AlertEngine
from app.alerts.models import Alert, AlertCondition, AlertRule, AlertSeverity
from app.dashboard.models import DashboardState


# ── helpers ───────────────────────────────────────────────────────────────────


def _state(**kwargs) -> DashboardState:
    defaults = dict(
        collected_at=datetime.now(timezone.utc).isoformat(),
        total_governed_runs=10,
        allowed=7,
        blocked=2,
        escalated=1,
        avg_confidence=75.0,
        avg_latency_ms=200.0,
        violation_count=3,
        pending_review=2,
    )
    defaults.update(kwargs)
    return DashboardState(**defaults)


def _empty_state() -> DashboardState:
    return DashboardState(collected_at=datetime.now(timezone.utc).isoformat())


def _rule(
    name="Test Rule",
    metric="avg_confidence",
    condition=AlertCondition.BELOW,
    threshold=50.0,
    severity=AlertSeverity.WARNING,
    message="test message",
) -> AlertRule:
    return AlertRule(
        name=name,
        metric=metric,
        condition=condition,
        threshold=threshold,
        severity=severity,
        message=message,
    )


# ── AlertSeverity ─────────────────────────────────────────────────────────────


class TestAlertSeverity:
    def test_critical_value(self):
        assert AlertSeverity.CRITICAL == "critical"

    def test_warning_value(self):
        assert AlertSeverity.WARNING == "warning"

    def test_info_value(self):
        assert AlertSeverity.INFO == "info"

    def test_is_str_enum(self):
        assert isinstance(AlertSeverity.CRITICAL, str)


# ── AlertCondition ────────────────────────────────────────────────────────────


class TestAlertCondition:
    def test_below_value(self):
        assert AlertCondition.BELOW == "below"

    def test_above_value(self):
        assert AlertCondition.ABOVE == "above"

    def test_is_str_enum(self):
        assert isinstance(AlertCondition.BELOW, str)


# ── AlertRule ─────────────────────────────────────────────────────────────────


class TestAlertRule:
    def test_required_fields(self):
        r = _rule()
        assert r.name == "Test Rule"
        assert r.metric == "avg_confidence"
        assert r.condition == AlertCondition.BELOW
        assert r.threshold == pytest.approx(50.0)

    def test_default_severity_warning(self):
        r = AlertRule(name="r", metric="m", condition=AlertCondition.BELOW, threshold=1.0)
        assert r.severity == AlertSeverity.WARNING

    def test_default_message_empty(self):
        r = AlertRule(name="r", metric="m", condition=AlertCondition.BELOW, threshold=1.0)
        assert r.message == ""

    def test_custom_severity(self):
        r = _rule(severity=AlertSeverity.CRITICAL)
        assert r.severity == AlertSeverity.CRITICAL

    def test_serializes_to_dict(self):
        d = _rule().model_dump()
        assert "name" in d and "metric" in d and "threshold" in d

    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(AlertRule, BaseModel)


# ── Alert ─────────────────────────────────────────────────────────────────────


class TestAlert:
    def _alert(self) -> Alert:
        return Alert(
            rule_name="Low Confidence",
            severity=AlertSeverity.WARNING,
            metric="avg_confidence",
            actual_value=45.0,
            threshold=60.0,
            message="confidence low",
            fired_at="2026-07-17T12:00:00+00:00",
        )

    def test_fields_accessible(self):
        a = self._alert()
        assert a.rule_name == "Low Confidence"
        assert a.severity == AlertSeverity.WARNING
        assert a.actual_value == pytest.approx(45.0)

    def test_fired_at_preserved(self):
        assert "2026-07-17" in self._alert().fired_at

    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(Alert, BaseModel)

    def test_serializes_to_dict(self):
        d = self._alert().model_dump()
        assert "rule_name" in d and "severity" in d and "fired_at" in d


# ── AlertEngine ───────────────────────────────────────────────────────────────


class TestAlertEngineBasic:
    def test_empty_rules_no_alerts(self):
        assert AlertEngine().evaluate(_state()) == []

    def test_rules_property_returns_copy(self):
        engine = AlertEngine([_rule()])
        r = engine.rules
        r.clear()
        assert len(engine.rules) == 1

    def test_add_rule(self):
        engine = AlertEngine()
        engine.add_rule(_rule())
        assert len(engine.rules) == 1

    def test_clear_rules(self):
        engine = AlertEngine([_rule(), _rule(name="r2")])
        engine.clear_rules()
        assert engine.rules == []

    def test_supported_metrics_returns_set(self):
        metrics = AlertEngine().supported_metrics()
        assert isinstance(metrics, set)
        assert "avg_confidence" in metrics

    def test_unknown_metric_silently_skipped(self):
        rule = _rule(metric="nonexistent_metric")
        alerts = AlertEngine([rule]).evaluate(_state())
        assert alerts == []


class TestAlertEngineBelow:
    def test_below_fires_when_value_under_threshold(self):
        rule = _rule(metric="avg_confidence", condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=70.0))
        assert len(alerts) == 1

    def test_below_does_not_fire_when_value_equal_threshold(self):
        rule = _rule(metric="avg_confidence", condition=AlertCondition.BELOW, threshold=75.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=75.0))
        assert alerts == []

    def test_below_does_not_fire_when_value_above_threshold(self):
        rule = _rule(metric="avg_confidence", condition=AlertCondition.BELOW, threshold=70.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=75.0))
        assert alerts == []

    def test_alert_carries_actual_value(self):
        rule = _rule(metric="avg_confidence", condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=55.0))
        assert alerts[0].actual_value == pytest.approx(55.0)

    def test_alert_carries_threshold(self):
        rule = _rule(metric="avg_confidence", condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=55.0))
        assert alerts[0].threshold == pytest.approx(80.0)


class TestAlertEngineAbove:
    def test_above_fires_when_value_over_threshold(self):
        rule = _rule(metric="pending_review", condition=AlertCondition.ABOVE, threshold=1.0)
        alerts = AlertEngine([rule]).evaluate(_state(pending_review=5))
        assert len(alerts) == 1

    def test_above_does_not_fire_when_value_equal_threshold(self):
        rule = _rule(metric="pending_review", condition=AlertCondition.ABOVE, threshold=5.0)
        alerts = AlertEngine([rule]).evaluate(_state(pending_review=5))
        assert alerts == []

    def test_above_does_not_fire_when_value_below_threshold(self):
        rule = _rule(metric="pending_review", condition=AlertCondition.ABOVE, threshold=10.0)
        alerts = AlertEngine([rule]).evaluate(_state(pending_review=5))
        assert alerts == []


class TestAlertEngineMetrics:
    def test_block_rate_computed_correctly(self):
        # 8 blocked out of 10 = 80%
        rule = _rule(metric="block_rate", condition=AlertCondition.ABOVE, threshold=70.0)
        state = _state(total_governed_runs=10, blocked=8, allowed=2, escalated=0)
        alerts = AlertEngine([rule]).evaluate(state)
        assert len(alerts) == 1
        assert alerts[0].actual_value == pytest.approx(80.0)

    def test_block_rate_zero_when_no_runs(self):
        rule = _rule(metric="block_rate", condition=AlertCondition.ABOVE, threshold=-1.0)
        alerts = AlertEngine([rule]).evaluate(_empty_state())
        assert alerts[0].actual_value == pytest.approx(0.0)

    def test_escalation_rate_computed(self):
        # 3 escalated out of 10 = 30%
        rule = _rule(metric="escalation_rate", condition=AlertCondition.ABOVE, threshold=20.0)
        state = _state(total_governed_runs=10, escalated=3, blocked=2, allowed=5)
        alerts = AlertEngine([rule]).evaluate(state)
        assert len(alerts) == 1
        assert alerts[0].actual_value == pytest.approx(30.0)

    def test_avg_latency_ms_metric(self):
        rule = _rule(metric="avg_latency_ms", condition=AlertCondition.ABOVE, threshold=100.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_latency_ms=500.0))
        assert len(alerts) == 1

    def test_violation_count_metric(self):
        rule = _rule(metric="violation_count", condition=AlertCondition.ABOVE, threshold=2.0)
        alerts = AlertEngine([rule]).evaluate(_state(violation_count=5))
        assert len(alerts) == 1

    def test_total_governed_runs_metric(self):
        rule = _rule(metric="total_governed_runs", condition=AlertCondition.ABOVE, threshold=5.0)
        alerts = AlertEngine([rule]).evaluate(_state(total_governed_runs=10))
        assert len(alerts) == 1


class TestAlertEngineMultipleRules:
    def test_multiple_rules_all_can_fire(self):
        rules = [
            _rule(name="r1", metric="avg_confidence", condition=AlertCondition.BELOW, threshold=80.0),
            _rule(name="r2", metric="pending_review", condition=AlertCondition.ABOVE, threshold=1.0),
        ]
        state = _state(avg_confidence=70.0, pending_review=5)
        alerts = AlertEngine(rules).evaluate(state)
        assert len(alerts) == 2

    def test_only_matching_rules_fire(self):
        rules = [
            _rule(name="fires", metric="avg_confidence", condition=AlertCondition.BELOW, threshold=80.0),
            _rule(name="silent", metric="avg_confidence", condition=AlertCondition.BELOW, threshold=60.0),
        ]
        alerts = AlertEngine(rules).evaluate(_state(avg_confidence=70.0))
        assert len(alerts) == 1
        assert alerts[0].rule_name == "fires"

    def test_alert_severity_preserved(self):
        rule = _rule(severity=AlertSeverity.CRITICAL, metric="avg_confidence",
                     condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=50.0))
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_alert_message_from_rule(self):
        rule = _rule(message="custom alert text", metric="avg_confidence",
                     condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=50.0))
        assert alerts[0].message == "custom alert text"

    def test_alert_default_message_generated(self):
        rule = AlertRule(name="r", metric="avg_confidence",
                         condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=50.0))
        assert len(alerts[0].message) > 0

    def test_alert_fired_at_is_recent(self):
        before = datetime.now(timezone.utc)
        rule = _rule(metric="avg_confidence", condition=AlertCondition.BELOW, threshold=80.0)
        alerts = AlertEngine([rule]).evaluate(_state(avg_confidence=50.0))
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(alerts[0].fired_at)
        assert before <= ts <= after


# ── default_rules ─────────────────────────────────────────────────────────────


class TestDefaultRules:
    def test_returns_list(self):
        assert isinstance(default_rules(), list)

    def test_nonempty(self):
        assert len(default_rules()) > 0

    def test_all_are_alert_rules(self):
        for r in default_rules():
            assert isinstance(r, AlertRule)

    def test_returns_copy(self):
        r1 = default_rules()
        r2 = default_rules()
        r1.clear()
        assert len(r2) > 0

    def test_default_engine_fires_on_low_confidence(self):
        engine = AlertEngine(default_rules())
        state = _state(avg_confidence=40.0, total_governed_runs=5, blocked=1, escalated=0, allowed=4)
        alerts = engine.evaluate(state)
        names = {a.rule_name for a in alerts}
        assert any("Confidence" in n or "confidence" in n.lower() for n in names)

    def test_default_engine_fires_on_high_block_rate(self):
        engine = AlertEngine(default_rules())
        # 9 blocked out of 10 = 90%
        state = _state(total_governed_runs=10, blocked=9, allowed=1, escalated=0, avg_confidence=80.0)
        alerts = engine.evaluate(state)
        names = {a.rule_name for a in alerts}
        assert any("Block" in n or "block" in n.lower() for n in names)

    def test_default_engine_no_alerts_on_healthy_state(self):
        engine = AlertEngine(default_rules())
        state = _state(
            total_governed_runs=10, allowed=9, blocked=1, escalated=0,
            avg_confidence=85.0, pending_review=2, escalation_rate=0.0,
        )
        alerts = engine.evaluate(state)
        assert alerts == []
