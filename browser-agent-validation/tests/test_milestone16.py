from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.audit.store import LocalAuditStore, make_audit_event
from app.dashboard.collector import DashboardCollector
from app.dashboard.models import DashboardConfig, DashboardState
from app.dashboard.renderer import DashboardRenderer
from app.models.base import RiskLevel, TrustDecision, ValidationResult
from app.review.models import ReviewStatus


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0):
    return ValidationResult(
        decision=decision,
        confidence=confidence,
        risk_level=risk,
        policy_score=score,
        violations=[],
    )


def _audit_store(tmp_path, events) -> Path:
    p = tmp_path / "audit.jsonl"
    store = LocalAuditStore(p)
    for ev in events:
        store.append(ev)
    return p


def _sample_events(n: int = 3) -> list:
    vrs = [
        _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=88.0),
        _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0, score=50.0),
        _vr(decision=TrustDecision.HUMAN_REVIEW, risk=RiskLevel.CRITICAL, confidence=20.0, score=0.0),
    ]
    return [make_audit_event(f"exec-{i}", vrs[i % len(vrs)], 100.0 * (i + 1)) for i in range(n)]


def _review_queue_with_items(tmp_path, n: int = 2) -> Path:
    from app.review.queue import ReviewQueue
    p = tmp_path / "rq.jsonl"
    q = ReviewQueue(p)
    for i in range(n):
        q.enqueue(f"query {i}", _vr(decision=TrustDecision.HUMAN_REVIEW))
    return p


def _empty_state() -> DashboardState:
    return DashboardState(collected_at=datetime.now(timezone.utc).isoformat())


# ── DashboardConfig ───────────────────────────────────────────────────────────


class TestDashboardConfig:
    def test_default_title(self):
        assert DashboardConfig().title == "AgentTrust Governance Dashboard"

    def test_default_max_recent_events(self):
        assert DashboardConfig().max_recent_events == 10

    def test_default_max_review_items(self):
        assert DashboardConfig().max_review_items == 5

    def test_custom_title(self):
        assert DashboardConfig(title="My Dashboard").title == "My Dashboard"

    def test_custom_max_recent_events(self):
        assert DashboardConfig(max_recent_events=3).max_recent_events == 3

    def test_custom_max_review_items(self):
        assert DashboardConfig(max_review_items=2).max_review_items == 2

    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(DashboardConfig, BaseModel)

    def test_serializes_to_dict(self):
        d = DashboardConfig().model_dump()
        assert "title" in d
        assert "max_recent_events" in d


# ── DashboardState ────────────────────────────────────────────────────────────


class TestDashboardState:
    def test_requires_collected_at(self):
        s = DashboardState(collected_at="2026-07-17T00:00:00+00:00")
        assert s.collected_at == "2026-07-17T00:00:00+00:00"

    def test_defaults_all_zero(self):
        s = _empty_state()
        assert s.total_governed_runs == 0
        assert s.allowed == 0
        assert s.blocked == 0
        assert s.escalated == 0
        assert s.pending_review == 0
        assert s.violation_count == 0

    def test_default_floats_zero(self):
        s = _empty_state()
        assert s.avg_confidence == pytest.approx(0.0)
        assert s.avg_latency_ms == pytest.approx(0.0)

    def test_default_most_common_risk(self):
        assert _empty_state().most_common_risk == "N/A"

    def test_default_empty_collections(self):
        s = _empty_state()
        assert s.recent_events == []
        assert s.pending_review_items == []
        assert s.metrics == {}

    def test_default_has_comparison_false(self):
        assert _empty_state().has_comparison is False

    def test_custom_values(self):
        s = DashboardState(
            collected_at="ts",
            total_governed_runs=10,
            allowed=7,
            blocked=3,
            avg_confidence=82.5,
        )
        assert s.total_governed_runs == 10
        assert s.allowed == 7
        assert s.avg_confidence == pytest.approx(82.5)


# ── DashboardCollector ────────────────────────────────────────────────────────


class TestDashboardCollector:
    def test_collect_no_paths_returns_state(self):
        state = DashboardCollector().collect()
        assert isinstance(state, DashboardState)

    def test_collect_no_paths_empty_kpis(self):
        state = DashboardCollector().collect()
        assert state.total_governed_runs == 0
        assert state.avg_confidence == pytest.approx(0.0)

    def test_collect_timestamp_is_recent(self):
        before = datetime.now(timezone.utc)
        state = DashboardCollector().collect()
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(state.collected_at)
        assert before <= ts <= after

    def test_collect_missing_files_no_error(self, tmp_path):
        state = DashboardCollector().collect(
            audit_path=tmp_path / "nope.jsonl",
            metrics_path=tmp_path / "nope.json",
            review_path=tmp_path / "nope.jsonl",
            comparison_path=tmp_path / "nope.json",
        )
        assert state.total_governed_runs == 0
        assert state.recent_events == []

    def test_collect_with_audit_events(self, tmp_path):
        p = _audit_store(tmp_path, _sample_events(3))
        state = DashboardCollector().collect(audit_path=p)
        assert state.total_governed_runs == 3

    def test_collect_counts_decisions(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(decision=TrustDecision.ALLOW), 100.0),
            make_audit_event("e2", _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0, score=50.0), 50.0),
            make_audit_event("e3", _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0, score=50.0), 50.0),
        ]
        p = _audit_store(tmp_path, events)
        state = DashboardCollector().collect(audit_path=p)
        assert state.allowed == 1
        assert state.blocked == 2

    def test_collect_avg_confidence(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(confidence=80.0), 0.0),
            make_audit_event("e2", _vr(confidence=60.0), 0.0),
        ]
        p = _audit_store(tmp_path, events)
        state = DashboardCollector().collect(audit_path=p)
        assert state.avg_confidence == pytest.approx(70.0)

    def test_collect_recent_events_capped(self, tmp_path):
        p = _audit_store(tmp_path, _sample_events(15))
        cfg = DashboardConfig(max_recent_events=5)
        state = DashboardCollector(cfg).collect(audit_path=p)
        assert len(state.recent_events) == 5

    def test_collect_pending_review_count(self, tmp_path):
        p = _review_queue_with_items(tmp_path, 3)
        state = DashboardCollector().collect(review_path=p)
        assert state.pending_review == 3

    def test_collect_pending_review_items_capped(self, tmp_path):
        p = _review_queue_with_items(tmp_path, 10)
        cfg = DashboardConfig(max_review_items=3)
        state = DashboardCollector(cfg).collect(review_path=p)
        assert len(state.pending_review_items) == 3

    def test_collect_pending_review_items_all_pending(self, tmp_path):
        p = _review_queue_with_items(tmp_path, 2)
        state = DashboardCollector().collect(review_path=p)
        for item in state.pending_review_items:
            assert item.status == ReviewStatus.PENDING

    def test_collect_has_comparison_true(self, tmp_path):
        comp_file = tmp_path / "comparison.json"
        comp_file.write_text("{}")
        state = DashboardCollector().collect(comparison_path=comp_file)
        assert state.has_comparison is True

    def test_collect_has_comparison_false_when_missing(self, tmp_path):
        state = DashboardCollector().collect(comparison_path=tmp_path / "nope.json")
        assert state.has_comparison is False

    def test_collect_with_metrics(self, tmp_path):
        from app.metrics.engine import LocalMetricsEngine, save_metrics
        m = LocalMetricsEngine()
        m.record("governance.confidence", 85.0)
        mp = tmp_path / "metrics.json"
        save_metrics(m, mp)
        state = DashboardCollector().collect(metrics_path=mp)
        assert isinstance(state.metrics, dict)
        assert len(state.metrics) > 0

    def test_collect_most_common_risk(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(risk=RiskLevel.HIGH, confidence=40.0, score=50.0), 0.0),
            make_audit_event("e2", _vr(risk=RiskLevel.HIGH, confidence=45.0, score=55.0), 0.0),
            make_audit_event("e3", _vr(risk=RiskLevel.LOW), 0.0),
        ]
        p = _audit_store(tmp_path, events)
        state = DashboardCollector().collect(audit_path=p)
        assert state.most_common_risk == "HIGH"

    def test_config_property(self):
        cfg = DashboardConfig(title="T")
        c = DashboardCollector(cfg)
        assert c.config is cfg


# ── DashboardRenderer ─────────────────────────────────────────────────────────


class TestDashboardRenderer:
    def _state(self) -> DashboardState:
        return DashboardState(
            collected_at="2026-07-17T12:00:00+00:00",
            total_governed_runs=5,
            allowed=3,
            blocked=2,
            escalated=1,
            avg_confidence=78.0,
            avg_latency_ms=300.0,
            violation_count=4,
            most_common_risk="HIGH",
            pending_review=1,
        )

    def test_render_returns_string(self):
        assert isinstance(DashboardRenderer().render(self._state()), str)

    def test_render_contains_title(self):
        md = DashboardRenderer().render(self._state())
        assert "# AgentTrust Governance Dashboard" in md

    def test_render_custom_title(self):
        cfg = DashboardConfig(title="My DB")
        md = DashboardRenderer().render(self._state(), cfg)
        assert "# My DB" in md

    def test_render_contains_collected_at(self):
        md = DashboardRenderer().render(self._state())
        assert "2026-07-17" in md

    def test_render_contains_kpis_section(self):
        md = DashboardRenderer().render(self._state())
        assert "## KPIs" in md

    def test_render_kpi_table_structure(self):
        md = DashboardRenderer().render(self._state())
        assert "|" in md
        assert "---" in md

    def test_render_contains_governed_runs(self):
        md = DashboardRenderer().render(self._state())
        assert "5" in md

    def test_render_no_audit_section_when_no_events(self):
        md = DashboardRenderer().render(self._state())
        assert "## Recent Audit Events" not in md

    def test_render_audit_section_when_events_present(self, tmp_path):
        from app.audit.store import LocalAuditStore, make_audit_event
        p = tmp_path / "a.jsonl"
        store = LocalAuditStore(p)
        store.append(make_audit_event("e1", _vr(), 100.0))
        from app.dashboard.collector import DashboardCollector
        state = DashboardCollector().collect(audit_path=p)
        md = DashboardRenderer().render(state)
        assert "## Recent Audit Events" in md

    def test_render_no_review_section_when_empty(self):
        md = DashboardRenderer().render(self._state())
        assert "## Pending Review" not in md

    def test_render_review_section_when_present(self, tmp_path):
        p = _review_queue_with_items(tmp_path, 1)
        state = DashboardCollector().collect(review_path=p)
        md = DashboardRenderer().render(state)
        assert "## Pending Review" in md

    def test_render_no_comparison_section_when_absent(self):
        md = DashboardRenderer().render(self._state())
        assert "## Comparison" not in md

    def test_render_comparison_section_when_present(self):
        state = self._state().model_copy(update={"has_comparison": True})
        md = DashboardRenderer().render(state)
        assert "## Comparison" in md

    def test_render_metrics_section_when_present(self, tmp_path):
        from app.metrics.engine import LocalMetricsEngine, save_metrics
        m = LocalMetricsEngine()
        m.record("governance.confidence", 85.0)
        mp = tmp_path / "metrics.json"
        save_metrics(m, mp)
        state = DashboardCollector().collect(metrics_path=mp)
        md = DashboardRenderer().render(state)
        assert "## Metrics Summary" in md

    def test_render_empty_state(self):
        state = _empty_state()
        md = DashboardRenderer().render(state)
        assert "0" in md
        assert "N/A" in md
