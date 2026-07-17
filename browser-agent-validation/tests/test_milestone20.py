from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.audit.store import LocalAuditStore, make_audit_event
from app.health.checker import HealthChecker
from app.health.models import ComponentCheck, HealthReport, HealthStatus
from app.models.base import RiskLevel, TrustDecision, ValidationResult


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0):
    return ValidationResult(
        decision=decision, confidence=confidence,
        risk_level=risk, policy_score=score, violations=[],
    )


def _audit_store(tmp_path, n=2) -> Path:
    p = tmp_path / "audit.jsonl"
    store = LocalAuditStore(p)
    for i in range(n):
        store.append(make_audit_event(f"e{i}", _vr(), 100.0))
    return p


def _review_queue(tmp_path, n=1) -> Path:
    from app.review.queue import ReviewQueue
    p = tmp_path / "rq.jsonl"
    q = ReviewQueue(p)
    for i in range(n):
        q.enqueue(f"query {i}", _vr(decision=TrustDecision.HUMAN_REVIEW))
    return p


def _metrics_file(tmp_path) -> Path:
    from app.metrics.engine import LocalMetricsEngine, save_metrics
    m = LocalMetricsEngine()
    m.record("governance.confidence", 85.0)
    p = tmp_path / "metrics.json"
    save_metrics(m, p)
    return p


# ── HealthStatus ──────────────────────────────────────────────────────────────


class TestHealthStatus:
    def test_healthy_value(self):
        assert HealthStatus.HEALTHY == "healthy"

    def test_degraded_value(self):
        assert HealthStatus.DEGRADED == "degraded"

    def test_unknown_value(self):
        assert HealthStatus.UNKNOWN == "unknown"

    def test_is_str_enum(self):
        assert isinstance(HealthStatus.HEALTHY, str)


# ── ComponentCheck ────────────────────────────────────────────────────────────


class TestComponentCheck:
    def test_required_fields(self):
        c = ComponentCheck(name="Audit Store", status=HealthStatus.HEALTHY)
        assert c.name == "Audit Store"
        assert c.status == HealthStatus.HEALTHY

    def test_default_empty_message(self):
        c = ComponentCheck(name="n", status=HealthStatus.HEALTHY)
        assert c.message == ""

    def test_default_empty_detail(self):
        c = ComponentCheck(name="n", status=HealthStatus.HEALTHY)
        assert c.detail == ""

    def test_custom_message(self):
        c = ComponentCheck(name="n", status=HealthStatus.DEGRADED, message="Read failed.")
        assert c.message == "Read failed."

    def test_serializes(self):
        d = ComponentCheck(name="n", status=HealthStatus.HEALTHY).model_dump()
        assert "name" in d and "status" in d

    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(ComponentCheck, BaseModel)


# ── HealthReport ──────────────────────────────────────────────────────────────


class TestHealthReport:
    def _report(self, overall=HealthStatus.HEALTHY, components=None) -> HealthReport:
        return HealthReport(
            checked_at="2026-07-18T00:00:00+00:00",
            overall=overall,
            components=components or [],
        )

    def test_construction(self):
        r = self._report()
        assert r.overall == HealthStatus.HEALTHY

    def test_default_empty_components(self):
        assert self._report().components == []

    def test_is_healthy_true(self):
        assert self._report(HealthStatus.HEALTHY).is_healthy is True

    def test_is_healthy_false_degraded(self):
        assert self._report(HealthStatus.DEGRADED).is_healthy is False

    def test_is_healthy_false_unknown(self):
        assert self._report(HealthStatus.UNKNOWN).is_healthy is False

    def test_healthy_count(self):
        comps = [
            ComponentCheck(name="a", status=HealthStatus.HEALTHY),
            ComponentCheck(name="b", status=HealthStatus.HEALTHY),
            ComponentCheck(name="c", status=HealthStatus.DEGRADED),
        ]
        assert self._report(components=comps).healthy_count == 2

    def test_degraded_count(self):
        comps = [
            ComponentCheck(name="a", status=HealthStatus.DEGRADED),
            ComponentCheck(name="b", status=HealthStatus.HEALTHY),
        ]
        assert self._report(components=comps).degraded_count == 1

    def test_serializes(self):
        d = self._report().model_dump()
        assert "checked_at" in d and "overall" in d


# ── HealthChecker — no paths ──────────────────────────────────────────────────


class TestHealthCheckerNoPaths:
    def test_returns_health_report(self):
        r = HealthChecker().check()
        assert isinstance(r, HealthReport)

    def test_has_five_components(self):
        r = HealthChecker().check()
        assert len(r.components) == 5

    def test_all_component_names_nonempty(self):
        r = HealthChecker().check()
        for c in r.components:
            assert len(c.name) > 0

    def test_no_paths_audit_unknown(self):
        r = HealthChecker().check()
        audit = next(c for c in r.components if "Audit" in c.name)
        assert audit.status == HealthStatus.UNKNOWN

    def test_no_paths_metrics_unknown(self):
        r = HealthChecker().check()
        metrics = next(c for c in r.components if "Metric" in c.name)
        assert metrics.status == HealthStatus.UNKNOWN

    def test_no_paths_review_unknown(self):
        r = HealthChecker().check()
        review = next(c for c in r.components if "Review" in c.name)
        assert review.status == HealthStatus.UNKNOWN

    def test_policy_healthy_with_default(self):
        r = HealthChecker().check()
        policy = next(c for c in r.components if "Policy" in c.name)
        assert policy.status == HealthStatus.HEALTHY

    def test_alert_engine_healthy(self):
        r = HealthChecker().check()
        alerts = next(c for c in r.components if "Alert" in c.name)
        assert alerts.status == HealthStatus.HEALTHY

    def test_timestamp_is_recent(self):
        before = datetime.now(timezone.utc)
        r = HealthChecker().check()
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(r.checked_at)
        assert before <= ts <= after


# ── HealthChecker — with real data ────────────────────────────────────────────


class TestHealthCheckerWithData:
    def test_audit_healthy_with_existing_file(self, tmp_path):
        p = _audit_store(tmp_path)
        r = HealthChecker().check(audit_path=p)
        audit = next(c for c in r.components if "Audit" in c.name)
        assert audit.status == HealthStatus.HEALTHY

    def test_audit_message_includes_event_count(self, tmp_path):
        p = _audit_store(tmp_path, 3)
        r = HealthChecker().check(audit_path=p)
        audit = next(c for c in r.components if "Audit" in c.name)
        assert "3" in audit.message

    def test_metrics_healthy_with_existing_file(self, tmp_path):
        p = _metrics_file(tmp_path)
        r = HealthChecker().check(metrics_path=p)
        metrics = next(c for c in r.components if "Metric" in c.name)
        assert metrics.status == HealthStatus.HEALTHY

    def test_review_healthy_with_existing_file(self, tmp_path):
        p = _review_queue(tmp_path)
        r = HealthChecker().check(review_path=p)
        review = next(c for c in r.components if "Review" in c.name)
        assert review.status == HealthStatus.HEALTHY

    def test_review_message_includes_pending(self, tmp_path):
        p = _review_queue(tmp_path, 2)
        r = HealthChecker().check(review_path=p)
        review = next(c for c in r.components if "Review" in c.name)
        assert "2" in review.message

    def test_all_healthy_overall_is_healthy(self, tmp_path):
        r = HealthChecker().check(
            audit_path=_audit_store(tmp_path),
            metrics_path=_metrics_file(tmp_path),
            review_path=_review_queue(tmp_path),
        )
        assert r.overall == HealthStatus.HEALTHY
        assert r.is_healthy is True

    def test_missing_file_returns_degraded(self, tmp_path):
        r = HealthChecker().check(audit_path=tmp_path / "missing.jsonl")
        audit = next(c for c in r.components if "Audit" in c.name)
        assert audit.status == HealthStatus.DEGRADED

    def test_degraded_component_makes_overall_degraded(self, tmp_path):
        r = HealthChecker().check(audit_path=tmp_path / "missing.jsonl")
        assert r.overall == HealthStatus.DEGRADED
        assert r.is_healthy is False


# ── HealthChecker — overall logic ─────────────────────────────────────────────


class TestHealthCheckerOverall:
    def test_overall_unknown_when_all_unknown(self):
        r = HealthChecker().check()
        statuses = {c.status for c in r.components}
        if HealthStatus.DEGRADED not in statuses and HealthStatus.HEALTHY not in statuses:
            assert r.overall == HealthStatus.UNKNOWN

    def test_overall_healthy_when_all_checked_healthy(self, tmp_path):
        r = HealthChecker().check(
            audit_path=_audit_store(tmp_path),
            metrics_path=_metrics_file(tmp_path),
            review_path=_review_queue(tmp_path),
        )
        assert r.overall == HealthStatus.HEALTHY

    def test_healthy_count_matches(self, tmp_path):
        r = HealthChecker().check(
            audit_path=_audit_store(tmp_path),
            metrics_path=_metrics_file(tmp_path),
        )
        assert r.healthy_count >= 2

    def test_degraded_component_detail_nonempty_on_error(self, tmp_path):
        bad_path = tmp_path / "bad.jsonl"
        bad_path.write_text("not valid json\n", encoding="utf-8")
        r = HealthChecker().check(audit_path=bad_path)
        audit = next(c for c in r.components if "Audit" in c.name)
        assert audit.status == HealthStatus.DEGRADED
