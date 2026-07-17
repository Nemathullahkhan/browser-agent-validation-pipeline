from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.audit.store import LocalAuditStore, make_audit_event
from app.models.base import RiskLevel, TrustDecision, ValidationResult
from app.report.generator import ReportGenerator
from app.report.models import ReportConfig, ReportSummary, SessionReport
from app.report.renderer import MarkdownRenderer
from app.review.models import ReviewItem, ReviewStatus


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0) -> ValidationResult:
    return ValidationResult(
        decision=decision,
        confidence=confidence,
        risk_level=risk,
        policy_score=score,
        violations=[],
    )


def _audit_store(tmp_path, events: list) -> Path:
    """Write AuditEvents to a temp file and return its path."""
    p = tmp_path / "audit.jsonl"
    store = LocalAuditStore(p)
    for ev in events:
        store.append(ev)
    return p


def _sample_events(n: int = 3) -> list:
    vrs = [
        _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=88.0),
        _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0),
        _vr(decision=TrustDecision.HUMAN_REVIEW, risk=RiskLevel.CRITICAL, confidence=20.0),
    ]
    events = []
    for i in range(n):
        vr = vrs[i % len(vrs)]
        events.append(make_audit_event(f"exec-{i}", vr, 100.0 * (i + 1)))
    return events


def _review_item(query: str = "test", status: ReviewStatus = ReviewStatus.PENDING) -> ReviewItem:
    return ReviewItem(
        item_id="aabbccdd-1234-5678-abcd-aabbccddeeff",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
        validation=_vr(decision=TrustDecision.HUMAN_REVIEW),
        status=status,
    )


# ── ReportConfig ──────────────────────────────────────────────────────────────


class TestReportConfig:
    def test_default_title(self):
        assert ReportConfig().title == "AgentTrust Session Report"

    def test_default_include_audit(self):
        assert ReportConfig().include_audit is True

    def test_default_include_metrics(self):
        assert ReportConfig().include_metrics is True

    def test_default_include_comparison(self):
        assert ReportConfig().include_comparison is True

    def test_default_include_review(self):
        assert ReportConfig().include_review is True

    def test_default_max_audit_events(self):
        assert ReportConfig().max_audit_events == 50

    def test_custom_title(self):
        assert ReportConfig(title="My Report").title == "My Report"

    def test_custom_max_audit_events(self):
        assert ReportConfig(max_audit_events=10).max_audit_events == 10

    def test_disable_audit(self):
        assert ReportConfig(include_audit=False).include_audit is False


# ── ReportSummary ─────────────────────────────────────────────────────────────


class TestReportSummary:
    def test_defaults_all_zero(self):
        s = ReportSummary()
        assert s.total_governed_runs == 0
        assert s.allowed == 0
        assert s.blocked == 0
        assert s.escalated == 0

    def test_default_avg_zero(self):
        s = ReportSummary()
        assert s.avg_confidence == pytest.approx(0.0)
        assert s.avg_latency_ms == pytest.approx(0.0)

    def test_default_most_common_risk(self):
        assert ReportSummary().most_common_risk == "N/A"

    def test_custom_values(self):
        s = ReportSummary(total_governed_runs=5, allowed=3, blocked=2, avg_confidence=75.0)
        assert s.total_governed_runs == 5
        assert s.allowed == 3
        assert s.avg_confidence == pytest.approx(75.0)


# ── SessionReport ─────────────────────────────────────────────────────────────


class TestSessionReport:
    def test_construction(self):
        rpt = SessionReport(title="T", generated_at="2026-07-17T00:00:00Z", summary=ReportSummary())
        assert rpt.title == "T"

    def test_defaults_empty_collections(self):
        rpt = SessionReport(title="T", generated_at="ts", summary=ReportSummary())
        assert rpt.audit_events == []
        assert rpt.metrics == {}
        assert rpt.comparison is None
        assert rpt.review_items == []

    def test_generated_at_preserved(self):
        rpt = SessionReport(title="T", generated_at="2026-07-17T12:00:00Z", summary=ReportSummary())
        assert "2026-07-17" in rpt.generated_at


# ── ReportGenerator — no-data case ───────────────────────────────────────────


class TestReportGeneratorEmpty:
    def test_generate_no_paths(self):
        gen = ReportGenerator()
        rpt = gen.generate()
        assert isinstance(rpt, SessionReport)

    def test_generate_no_paths_empty_summary(self):
        gen = ReportGenerator()
        rpt = gen.generate()
        assert rpt.summary.total_governed_runs == 0

    def test_generate_missing_files_no_error(self, tmp_path):
        gen = ReportGenerator()
        rpt = gen.generate(
            audit_path=tmp_path / "nope.jsonl",
            metrics_path=tmp_path / "nope.json",
            comparison_path=tmp_path / "nope.json",
            review_path=tmp_path / "nope.jsonl",
        )
        assert rpt.audit_events == []
        assert rpt.metrics == {}
        assert rpt.comparison is None
        assert rpt.review_items == []

    def test_generate_title_from_config(self):
        gen = ReportGenerator(ReportConfig(title="Custom Title"))
        rpt = gen.generate()
        assert rpt.title == "Custom Title"

    def test_generate_timestamp_is_recent(self):
        before = datetime.now(timezone.utc)
        rpt = ReportGenerator().generate()
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(rpt.generated_at.replace("Z", "+00:00"))
        assert before <= ts <= after


# ── ReportGenerator — with audit data ────────────────────────────────────────


class TestReportGeneratorWithAudit:
    def test_loads_audit_events(self, tmp_path):
        p = _audit_store(tmp_path, _sample_events(3))
        rpt = ReportGenerator().generate(audit_path=p)
        assert len(rpt.audit_events) == 3

    def test_summary_total_matches_events(self, tmp_path):
        p = _audit_store(tmp_path, _sample_events(4))
        rpt = ReportGenerator().generate(audit_path=p)
        assert rpt.summary.total_governed_runs == 4

    def test_summary_allowed_count(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(decision=TrustDecision.ALLOW), 100.0),
            make_audit_event("e2", _vr(decision=TrustDecision.ALLOW), 200.0),
            make_audit_event("e3", _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=30.0), 50.0),
        ]
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator().generate(audit_path=p)
        assert rpt.summary.allowed == 2
        assert rpt.summary.blocked == 1

    def test_summary_avg_confidence(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(confidence=80.0), 0.0),
            make_audit_event("e2", _vr(confidence=60.0), 0.0),
        ]
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator().generate(audit_path=p)
        assert rpt.summary.avg_confidence == pytest.approx(70.0)

    def test_summary_avg_latency(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(), 100.0),
            make_audit_event("e2", _vr(), 300.0),
        ]
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator().generate(audit_path=p)
        assert rpt.summary.avg_latency_ms == pytest.approx(200.0)

    def test_summary_violation_count(self, tmp_path):
        vr1 = ValidationResult(decision=TrustDecision.BLOCK, confidence=40.0, risk_level=RiskLevel.HIGH,
                               policy_score=55.0, violations=["v1", "v2"])
        vr2 = ValidationResult(decision=TrustDecision.BLOCK, confidence=35.0, risk_level=RiskLevel.HIGH,
                               policy_score=50.0, violations=["v3"])
        events = [make_audit_event("e1", vr1, 0.0), make_audit_event("e2", vr2, 0.0)]
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator().generate(audit_path=p)
        assert rpt.summary.violation_count == 3

    def test_summary_most_common_risk(self, tmp_path):
        events = [
            make_audit_event("e1", _vr(risk=RiskLevel.HIGH, confidence=40.0), 0.0),
            make_audit_event("e2", _vr(risk=RiskLevel.HIGH, confidence=45.0), 0.0),
            make_audit_event("e3", _vr(risk=RiskLevel.LOW), 0.0),
        ]
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator().generate(audit_path=p)
        assert rpt.summary.most_common_risk == "HIGH"

    def test_max_audit_events_cap(self, tmp_path):
        events = _sample_events(10)
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator(ReportConfig(max_audit_events=5)).generate(audit_path=p)
        assert len(rpt.audit_events) == 5

    def test_audit_disabled_skips_load(self, tmp_path):
        p = _audit_store(tmp_path, _sample_events(3))
        rpt = ReportGenerator(ReportConfig(include_audit=False)).generate(audit_path=p)
        assert rpt.audit_events == []
        assert rpt.summary.total_governed_runs == 0


# ── ReportGenerator — with review data ───────────────────────────────────────


class TestReportGeneratorWithReview:
    def test_loads_review_items(self, tmp_path):
        from app.review.queue import ReviewQueue
        q = ReviewQueue(tmp_path / "rq.jsonl")
        vr = _vr(decision=TrustDecision.HUMAN_REVIEW, risk=RiskLevel.CRITICAL)
        q.enqueue("test query", vr)
        rpt = ReportGenerator().generate(review_path=tmp_path / "rq.jsonl")
        assert len(rpt.review_items) == 1

    def test_review_disabled_skips_load(self, tmp_path):
        from app.review.queue import ReviewQueue
        q = ReviewQueue(tmp_path / "rq.jsonl")
        q.enqueue("q", _vr(decision=TrustDecision.HUMAN_REVIEW))
        rpt = ReportGenerator(ReportConfig(include_review=False)).generate(review_path=tmp_path / "rq.jsonl")
        assert rpt.review_items == []


# ── MarkdownRenderer ──────────────────────────────────────────────────────────


class TestMarkdownRenderer:
    def _make_report(self) -> SessionReport:
        return SessionReport(
            title="Test Report",
            generated_at="2026-07-17T12:00:00+00:00",
            summary=ReportSummary(
                total_governed_runs=3, allowed=2, blocked=1,
                avg_confidence=75.0, avg_latency_ms=500.0,
                violation_count=2, most_common_risk="HIGH",
            ),
        )

    def test_render_returns_string(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert isinstance(md, str)

    def test_render_contains_title(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "# Test Report" in md

    def test_render_contains_generated_at(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "2026-07-17" in md

    def test_render_contains_summary_section(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "## Executive Summary" in md

    def test_render_contains_governed_count(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "3" in md  # total_governed_runs

    def test_render_no_audit_section_when_empty(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "## Audit Log" not in md

    def test_render_audit_section_when_present(self, tmp_path):
        events = _sample_events(2)
        p = _audit_store(tmp_path, events)
        rpt = ReportGenerator().generate(audit_path=p)
        md = MarkdownRenderer().render(rpt)
        assert "## Audit Log" in md

    def test_render_no_review_section_when_empty(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "## Human Review Queue" not in md

    def test_render_review_section_when_present(self):
        rpt = self._make_report()
        rpt = rpt.model_copy(update={"review_items": [_review_item("my query")]})
        md = MarkdownRenderer().render(rpt)
        assert "## Human Review Queue" in md
        assert "my query" in md

    def test_render_markdown_table_structure(self):
        rpt = self._make_report()
        md = MarkdownRenderer().render(rpt)
        assert "|" in md
        assert "---" in md

    def test_save_creates_file(self, tmp_path):
        rpt = self._make_report()
        out = tmp_path / "report.md"
        saved = MarkdownRenderer().save(rpt, out)
        assert saved.exists()
        assert saved == out

    def test_save_creates_parent_dirs(self, tmp_path):
        rpt = self._make_report()
        out = tmp_path / "reports" / "session" / "report.md"
        MarkdownRenderer().save(rpt, out)
        assert out.exists()

    def test_save_content_matches_render(self, tmp_path):
        rpt = self._make_report()
        out = tmp_path / "report.md"
        renderer = MarkdownRenderer()
        renderer.save(rpt, out)
        assert out.read_text() == renderer.render(rpt)

    def test_render_metrics_section(self, tmp_path):
        from app.metrics.engine import LocalMetricsEngine, save_metrics
        m = LocalMetricsEngine()
        m.record("governance.output.confidence", 85.0)
        mp = tmp_path / "metrics.json"
        save_metrics(m, mp)
        rpt = ReportGenerator().generate(metrics_path=mp)
        md = MarkdownRenderer().render(rpt)
        assert "## Governance Metrics" in md
