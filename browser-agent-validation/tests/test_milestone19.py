from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.audit.store import LocalAuditStore, make_audit_event
from app.models.base import RiskLevel, TrustDecision, ValidationResult
from app.trends.analyzer import TrendAnalyzer
from app.trends.models import MetricTrend, TrendDirection, TrendPoint, TrendReport


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0):
    return ValidationResult(
        decision=decision, confidence=confidence,
        risk_level=risk, policy_score=score, violations=[],
    )


def _ev(exec_id="e", confidence=80.0, latency=200.0, decision=TrustDecision.ALLOW, risk=RiskLevel.LOW):
    return make_audit_event(exec_id, _vr(decision=decision, risk=risk, confidence=confidence), latency)


def _events_improving_confidence(n=6) -> list:
    """Confidence rises from 50 → 90 across n events."""
    step = (90.0 - 50.0) / max(n - 1, 1)
    return [_ev(exec_id=f"e{i}", confidence=50.0 + i * step) for i in range(n)]


def _events_degrading_confidence(n=6) -> list:
    """Confidence falls from 90 → 50."""
    step = (90.0 - 50.0) / max(n - 1, 1)
    return [_ev(exec_id=f"e{i}", confidence=90.0 - i * step) for i in range(n)]


def _events_stable_confidence(n=4) -> list:
    """Confidence stays at 80 throughout."""
    return [_ev(exec_id=f"e{i}", confidence=80.0) for i in range(n)]


def _events_improving_latency(n=6) -> list:
    """Latency falls from 1000 → 200 ms."""
    step = (1000.0 - 200.0) / max(n - 1, 1)
    return [_ev(exec_id=f"e{i}", latency=1000.0 - i * step) for i in range(n)]


def _events_degrading_latency(n=6) -> list:
    """Latency rises from 200 → 1000 ms."""
    step = (1000.0 - 200.0) / max(n - 1, 1)
    return [_ev(exec_id=f"e{i}", latency=200.0 + i * step) for i in range(n)]


def _events_high_block_rate(n=6) -> list:
    """All BLOCK — block_rate window = 100%."""
    return [
        _ev(exec_id=f"e{i}", confidence=40.0, decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        for i in range(n)
    ]


def _events_no_blocks(n=4) -> list:
    """All ALLOW — block_rate = 0%."""
    return [_ev(exec_id=f"e{i}", decision=TrustDecision.ALLOW) for i in range(n)]


# ── TrendDirection ────────────────────────────────────────────────────────────


class TestTrendDirection:
    def test_improving_value(self):
        assert TrendDirection.IMPROVING == "improving"

    def test_degrading_value(self):
        assert TrendDirection.DEGRADING == "degrading"

    def test_stable_value(self):
        assert TrendDirection.STABLE == "stable"

    def test_is_str_enum(self):
        assert isinstance(TrendDirection.IMPROVING, str)


# ── TrendPoint ────────────────────────────────────────────────────────────────


class TestTrendPoint:
    def test_fields(self):
        p = TrendPoint(timestamp="2026-07-18T00:00:00Z", value=75.0)
        assert p.timestamp == "2026-07-18T00:00:00Z"
        assert p.value == pytest.approx(75.0)

    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(TrendPoint, BaseModel)

    def test_serializes(self):
        d = TrendPoint(timestamp="ts", value=1.0).model_dump()
        assert "timestamp" in d and "value" in d


# ── MetricTrend ───────────────────────────────────────────────────────────────


class TestMetricTrend:
    def _trend(self, direction=TrendDirection.STABLE) -> MetricTrend:
        return MetricTrend(
            metric="avg_confidence",
            direction=direction,
            first_value=80.0,
            last_value=85.0,
            change_pct=6.25,
        )

    def test_fields(self):
        t = self._trend(TrendDirection.IMPROVING)
        assert t.metric == "avg_confidence"
        assert t.direction == TrendDirection.IMPROVING
        assert t.first_value == pytest.approx(80.0)
        assert t.last_value == pytest.approx(85.0)

    def test_default_empty_data_points(self):
        assert self._trend().data_points == []

    def test_change_pct(self):
        assert self._trend().change_pct == pytest.approx(6.25)

    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(MetricTrend, BaseModel)

    def test_serializes(self):
        d = self._trend().model_dump()
        assert "metric" in d and "direction" in d


# ── TrendReport ───────────────────────────────────────────────────────────────


class TestTrendReport:
    def test_construction(self):
        r = TrendReport(analyzed_at="2026-07-18T00:00:00Z", event_count=5)
        assert r.event_count == 5

    def test_default_empty_trends(self):
        r = TrendReport(analyzed_at="ts")
        assert r.trends == {}

    def test_default_event_count_zero(self):
        assert TrendReport(analyzed_at="ts").event_count == 0

    def test_serializes(self):
        d = TrendReport(analyzed_at="ts").model_dump()
        assert "analyzed_at" in d and "trends" in d


# ── TrendAnalyzer — basics ────────────────────────────────────────────────────


class TestTrendAnalyzerBasics:
    def test_empty_events_returns_report(self):
        r = TrendAnalyzer().analyze([])
        assert isinstance(r, TrendReport)

    def test_empty_events_zero_count(self):
        assert TrendAnalyzer().analyze([]).event_count == 0

    def test_empty_events_no_trends(self):
        assert TrendAnalyzer().analyze([]).trends == {}

    def test_single_event_no_trends(self):
        r = TrendAnalyzer().analyze([_ev()])
        assert r.trends == {}

    def test_event_count_matches(self):
        events = _events_improving_confidence(5)
        r = TrendAnalyzer().analyze(events)
        assert r.event_count == 5

    def test_analyzed_at_is_recent(self):
        before = datetime.now(timezone.utc)
        r = TrendAnalyzer().analyze([])
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(r.analyzed_at)
        assert before <= ts <= after

    def test_supported_metrics_nonempty(self):
        metrics = TrendAnalyzer().supported_metrics()
        assert len(metrics) > 0
        assert "avg_confidence" in metrics

    def test_trends_keyed_by_metric_name(self):
        r = TrendAnalyzer().analyze(_events_improving_confidence())
        assert "avg_confidence" in r.trends


# ── TrendAnalyzer — confidence ────────────────────────────────────────────────


class TestTrendAnalyzerConfidence:
    def test_improving_confidence_detected(self):
        r = TrendAnalyzer().analyze(_events_improving_confidence())
        assert r.trends["avg_confidence"].direction == TrendDirection.IMPROVING

    def test_degrading_confidence_detected(self):
        r = TrendAnalyzer().analyze(_events_degrading_confidence())
        assert r.trends["avg_confidence"].direction == TrendDirection.DEGRADING

    def test_stable_confidence_detected(self):
        r = TrendAnalyzer().analyze(_events_stable_confidence())
        assert r.trends["avg_confidence"].direction == TrendDirection.STABLE

    def test_first_value_is_first_event_confidence(self):
        events = _events_improving_confidence(6)
        r = TrendAnalyzer().analyze(events)
        assert r.trends["avg_confidence"].first_value == pytest.approx(events[0].confidence, abs=0.5)

    def test_last_value_is_last_event_confidence(self):
        events = _events_improving_confidence(6)
        r = TrendAnalyzer().analyze(events)
        assert r.trends["avg_confidence"].last_value == pytest.approx(events[-1].confidence, abs=0.5)

    def test_data_points_count_matches_events(self):
        events = _events_improving_confidence(4)
        r = TrendAnalyzer().analyze(events)
        assert len(r.trends["avg_confidence"].data_points) == 4

    def test_change_pct_positive_for_improving(self):
        r = TrendAnalyzer().analyze(_events_improving_confidence())
        assert r.trends["avg_confidence"].change_pct > 0

    def test_change_pct_negative_for_degrading(self):
        r = TrendAnalyzer().analyze(_events_degrading_confidence())
        assert r.trends["avg_confidence"].change_pct < 0


# ── TrendAnalyzer — latency ───────────────────────────────────────────────────


class TestTrendAnalyzerLatency:
    def test_improving_latency_detected(self):
        r = TrendAnalyzer().analyze(_events_improving_latency())
        assert r.trends["avg_latency_ms"].direction == TrendDirection.IMPROVING

    def test_degrading_latency_detected(self):
        r = TrendAnalyzer().analyze(_events_degrading_latency())
        assert r.trends["avg_latency_ms"].direction == TrendDirection.DEGRADING

    def test_stable_latency_detected(self):
        events = [_ev(exec_id=f"e{i}", latency=300.0) for i in range(4)]
        r = TrendAnalyzer().analyze(events)
        assert r.trends["avg_latency_ms"].direction == TrendDirection.STABLE


# ── TrendAnalyzer — block rate ────────────────────────────────────────────────


class TestTrendAnalyzerBlockRate:
    def test_block_rate_trend_present(self):
        r = TrendAnalyzer().analyze(_events_high_block_rate())
        assert "block_rate" in r.trends

    def test_all_blocks_last_value_high(self):
        r = TrendAnalyzer().analyze(_events_high_block_rate(6))
        assert r.trends["block_rate"].last_value == pytest.approx(100.0)

    def test_no_blocks_last_value_zero(self):
        r = TrendAnalyzer().analyze(_events_no_blocks())
        assert r.trends["block_rate"].last_value == pytest.approx(0.0)

    def test_degrading_block_rate_when_blocks_increase(self):
        # Start with no blocks then switch to all blocks
        events = _events_no_blocks(3) + _events_high_block_rate(6)
        r = TrendAnalyzer().analyze(events)
        assert r.trends["block_rate"].direction == TrendDirection.DEGRADING

    def test_improving_block_rate_when_blocks_decrease(self):
        # Start with all blocks then switch to no blocks
        events = _events_high_block_rate(6) + _events_no_blocks(6)
        r = TrendAnalyzer().analyze(events)
        assert r.trends["block_rate"].direction == TrendDirection.IMPROVING
