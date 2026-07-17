from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest

from app.metrics.engine import LocalMetricsEngine, load_metrics, save_metrics
from app.metrics.interfaces import MetricsEngine
from app.models.base import (
    BrowserResult,
    ComparisonResult,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTrace,
    RiskLevel,
    TrustDecision,
    ValidationResult,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_vr(
    decision: TrustDecision = TrustDecision.ALLOW,
    confidence: float = 92.0,
    policy_score: float = 100.0,
    risk: RiskLevel = RiskLevel.LOW,
    violations: list[str] | None = None,
) -> ValidationResult:
    return ValidationResult(
        decision=decision,
        confidence=confidence,
        risk_level=risk,
        policy_score=policy_score,
        violations=violations or [],
        reason="test",
        envelope_id=str(uuid.uuid4()),
    )


def _make_trace(
    query: str = "test",
    steps: dict[str, float] | None = None,
    total_ms: float | None = None,
) -> ExecutionTrace:
    default_steps = {
        "planning": 120.0,
        "search": 460.0,
        "browser": 700.0,
        "extraction": 410.0,
        "reasoning": 1800.0,
        "response": 10.0,
    }
    step_defs = steps if steps is not None else default_steps
    t = time.time()
    events = []
    for i, (name, dur) in enumerate(step_defs.items()):
        events.append(
            ExecutionEvent(
                step=name,
                status=ExecutionStatus.SUCCESS,
                start_time=t + i * 0.1,
                end_time=t + i * 0.1 + dur / 1000,
                duration_ms=dur,
            )
        )
    computed_total = total_ms if total_ms is not None else sum(step_defs.values())
    return ExecutionTrace(
        execution_id=str(uuid.uuid4()),
        query=query,
        events=events,
        total_duration_ms=computed_total,
        status=ExecutionStatus.SUCCESS,
    )


def _make_cr(
    governed_error: str | None = None,
    overhead_ms: float = 50.0,
    output_vr: ValidationResult | None = None,
    input_vr: ValidationResult | None = None,
) -> ComparisonResult:
    raw_result = BrowserResult(
        summary="The Model Context Protocol is an open standard.",
        sources=["Anthropic Blog"],
        urls=["https://anthropic.com/mcp"],
        latency_ms=3500.0,
    )
    gov_result = None if governed_error else raw_result
    return ComparisonResult(
        query="test",
        raw_result=raw_result,
        raw_trace=_make_trace(),
        governed_result=gov_result,
        governed_trace=None if governed_error else _make_trace(),
        governed_decision="ALLOW" if not governed_error else None,
        input_validation=input_vr or _make_vr(),
        output_validation=output_vr or (_make_vr() if not governed_error else None),
        governed_error=governed_error,
        raw_latency_ms=3500.0,
        governed_latency_ms=3550.0,
        governance_overhead_ms=overhead_ms,
    )


# ── MetricsEngine interface ───────────────────────────────────────────────────

class TestMetricsEngineInterface:
    def test_local_is_subclass(self):
        assert issubclass(LocalMetricsEngine, MetricsEngine)

    def test_has_record(self):
        e = LocalMetricsEngine()
        assert hasattr(e, "record")

    def test_has_summary(self):
        e = LocalMetricsEngine()
        assert hasattr(e, "summary")

    def test_has_export(self):
        e = LocalMetricsEngine()
        assert hasattr(e, "export")


# ── LocalMetricsEngine — record / summary ─────────────────────────────────────

class TestLocalMetricsEngine:
    def test_record_single_value(self):
        e = LocalMetricsEngine()
        e.record("latency", 1000.0)
        s = e.summary()
        assert "latency" in s

    def test_record_count_one(self):
        e = LocalMetricsEngine()
        e.record("latency", 1000.0)
        assert e.summary()["latency"]["count"] == 1

    def test_record_multiple_same_key(self):
        e = LocalMetricsEngine()
        e.record("latency", 1000.0)
        e.record("latency", 2000.0)
        assert e.summary()["latency"]["count"] == 2

    def test_record_different_keys(self):
        e = LocalMetricsEngine()
        e.record("a", 1.0)
        e.record("b", 2.0)
        s = e.summary()
        assert "a" in s
        assert "b" in s

    def test_record_with_tags(self):
        e = LocalMetricsEngine()
        e.record("latency", 500.0, tags={"mode": "raw"})
        assert e.summary()["latency"]["count"] == 1

    def test_record_integer_value(self):
        e = LocalMetricsEngine()
        e.record("count", 5)
        assert e.summary()["count"]["last"] == 5.0

    def test_summary_empty_returns_empty_dict(self):
        e = LocalMetricsEngine()
        assert e.summary() == {}

    def test_summary_avg_single(self):
        e = LocalMetricsEngine()
        e.record("x", 42.0)
        assert e.summary()["x"]["avg"] == 42.0

    def test_summary_avg_multiple(self):
        e = LocalMetricsEngine()
        e.record("x", 100.0)
        e.record("x", 200.0)
        assert e.summary()["x"]["avg"] == 150.0

    def test_summary_min(self):
        e = LocalMetricsEngine()
        for v in [300.0, 100.0, 200.0]:
            e.record("x", v)
        assert e.summary()["x"]["min"] == 100.0

    def test_summary_max(self):
        e = LocalMetricsEngine()
        for v in [300.0, 100.0, 200.0]:
            e.record("x", v)
        assert e.summary()["x"]["max"] == 300.0

    def test_summary_total(self):
        e = LocalMetricsEngine()
        e.record("x", 10.0)
        e.record("x", 20.0)
        e.record("x", 30.0)
        assert e.summary()["x"]["total"] == 60.0

    def test_summary_last_is_most_recent(self):
        e = LocalMetricsEngine()
        e.record("x", 1.0)
        e.record("x", 2.0)
        e.record("x", 3.0)
        assert e.summary()["x"]["last"] == 3.0


# ── record_trace ──────────────────────────────────────────────────────────────

class TestRecordTrace:
    def test_records_step_durations(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace())
        s = e.summary()
        assert "step.planning.ms" in s
        assert "step.search.ms" in s

    def test_records_all_six_steps(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace())
        s = e.summary()
        for step in ("planning", "search", "browser", "extraction", "reasoning", "response"):
            assert f"step.{step}.ms" in s, f"Missing step: {step}"

    def test_records_total_duration(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace(total_ms=3500.0))
        assert "total_latency_ms" in e.summary()

    def test_total_duration_value_correct(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace(total_ms=3500.0))
        assert e.summary()["total_latency_ms"]["last"] == 3500.0

    def test_step_duration_value_correct(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace(steps={"planning": 123.0}))
        assert e.summary()["step.planning.ms"]["last"] == 123.0

    def test_mode_tag_raw_by_default(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace())
        # Record a second run with different mode to confirm keys are the same key space
        e.record_trace(_make_trace(steps={"planning": 200.0}), mode="governed")
        s = e.summary()
        assert s["step.planning.ms"]["count"] == 2

    def test_skips_steps_without_duration(self):
        t = time.time()
        trace = ExecutionTrace(
            execution_id=str(uuid.uuid4()),
            query="q",
            events=[
                ExecutionEvent(
                    step="planning",
                    status=ExecutionStatus.RUNNING,
                    start_time=t,
                    duration_ms=None,  # no duration
                )
            ],
        )
        e = LocalMetricsEngine()
        e.record_trace(trace)
        # step.planning.ms should not be recorded
        assert "step.planning.ms" not in e.summary()

    def test_multiple_traces_accumulate(self):
        e = LocalMetricsEngine()
        e.record_trace(_make_trace())
        e.record_trace(_make_trace())
        assert e.summary()["step.planning.ms"]["count"] == 2


# ── record_validation ─────────────────────────────────────────────────────────

class TestRecordValidation:
    def test_records_confidence(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(confidence=88.0))
        assert e.summary()["governance.confidence"]["last"] == 88.0

    def test_records_policy_score(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(policy_score=75.0))
        assert e.summary()["governance.policy_score"]["last"] == 75.0

    def test_records_violation_count(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(violations=["a", "b"]))
        assert e.summary()["governance.violations"]["last"] == 2.0

    def test_records_zero_violations(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(violations=[]))
        assert e.summary()["governance.violations"]["last"] == 0.0

    def test_allow_decision_records_one(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(decision=TrustDecision.ALLOW))
        assert e.summary()["governance.decision.allow"]["last"] == 1.0
        assert e.summary()["governance.decision.block"]["last"] == 0.0

    def test_block_decision_records_one(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(decision=TrustDecision.BLOCK))
        assert e.summary()["governance.decision.block"]["last"] == 1.0
        assert e.summary()["governance.decision.allow"]["last"] == 0.0

    def test_human_review_decision_records_one(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(decision=TrustDecision.HUMAN_REVIEW))
        assert e.summary()["governance.decision.review"]["last"] == 1.0

    def test_low_risk_records_zero(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(risk=RiskLevel.LOW))
        assert e.summary()["governance.risk"]["last"] == 0.0

    def test_high_risk_records_two(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(risk=RiskLevel.HIGH))
        assert e.summary()["governance.risk"]["last"] == 2.0

    def test_critical_risk_records_three(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(risk=RiskLevel.CRITICAL))
        assert e.summary()["governance.risk"]["last"] == 3.0

    def test_custom_prefix(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr(), prefix="input")
        s = e.summary()
        assert "input.confidence" in s
        assert "governance.confidence" not in s

    def test_all_keys_present(self):
        e = LocalMetricsEngine()
        e.record_validation(_make_vr())
        s = e.summary()
        expected = [
            "governance.confidence",
            "governance.policy_score",
            "governance.violations",
            "governance.risk",
            "governance.decision.allow",
            "governance.decision.block",
            "governance.decision.review",
        ]
        for k in expected:
            assert k in s, f"Missing key: {k}"


# ── record_comparison ─────────────────────────────────────────────────────────

class TestRecordComparison:
    def test_records_raw_trace(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr())
        assert "step.planning.ms" in e.summary()

    def test_records_governed_trace(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr())
        # governed trace has same steps — count should be 2
        assert e.summary()["step.planning.ms"]["count"] == 2

    def test_records_overhead(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr(overhead_ms=75.0))
        assert e.summary()["governance.overhead_ms"]["last"] == 75.0

    def test_records_output_validation(self):
        vr = _make_vr(confidence=95.0)
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr(output_vr=vr))
        assert e.summary()["governance.output.confidence"]["last"] == 95.0

    def test_records_input_validation(self):
        vr = _make_vr(confidence=99.0)
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr(input_vr=vr))
        assert e.summary()["governance.input.confidence"]["last"] == 99.0

    def test_blocked_records_run_blocked(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr(governed_error="injection detected"))
        assert e.summary()["run.blocked"]["last"] == 1.0

    def test_allowed_records_run_allowed(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr())
        assert e.summary()["run.allowed"]["last"] == 1.0

    def test_blocked_no_governed_trace_still_records_raw(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr(governed_error="blocked"))
        s = e.summary()
        # raw trace should always be recorded
        assert "total_latency_ms" in s

    def test_blocked_governance_overhead_still_recorded(self):
        e = LocalMetricsEngine()
        e.record_comparison(_make_cr(governed_error="blocked", overhead_ms=30.0))
        assert e.summary()["governance.overhead_ms"]["last"] == 30.0


# ── export ────────────────────────────────────────────────────────────────────

class TestExport:
    def test_export_creates_file(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("latency", 1000.0)
        e.export(str(tmp_path / "metrics.json"))
        assert (tmp_path / "metrics.json").exists()

    def test_export_valid_json(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("latency", 1000.0)
        p = tmp_path / "metrics.json"
        e.export(str(p))
        data = json.loads(p.read_text())
        assert isinstance(data, dict)

    def test_export_contains_recorded_keys(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("step.planning.ms", 120.0)
        e.record("governance.confidence", 92.0)
        p = tmp_path / "metrics.json"
        e.export(str(p))
        data = json.loads(p.read_text())
        assert "step.planning.ms" in data
        assert "governance.confidence" in data

    def test_export_aggregation_structure(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("x", 10.0)
        e.record("x", 20.0)
        p = tmp_path / "metrics.json"
        e.export(str(p))
        data = json.loads(p.read_text())
        assert data["x"]["count"] == 2
        assert data["x"]["avg"] == 15.0

    def test_export_empty_engine(self, tmp_path: Path):
        e = LocalMetricsEngine()
        p = tmp_path / "metrics.json"
        e.export(str(p))
        data = json.loads(p.read_text())
        assert data == {}


# ── save_metrics / load_metrics ───────────────────────────────────────────────

class TestSaveLoadMetrics:
    def test_save_creates_file(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("latency", 500.0)
        p = save_metrics(e, tmp_path / "metrics.json")
        assert p.exists()

    def test_load_returns_dict(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("latency", 500.0)
        p = save_metrics(e, tmp_path / "metrics.json")
        data = load_metrics(p)
        assert isinstance(data, dict)

    def test_save_load_roundtrip(self, tmp_path: Path):
        e = LocalMetricsEngine()
        e.record("step.planning.ms", 120.0)
        e.record("governance.confidence", 92.0)
        p = save_metrics(e, tmp_path / "metrics.json")
        data = load_metrics(p)
        assert "step.planning.ms" in data
        assert "governance.confidence" in data
        assert data["step.planning.ms"]["last"] == pytest.approx(120.0)

    def test_load_nonexistent_returns_empty(self, tmp_path: Path):
        data = load_metrics(tmp_path / "no_such_file.json")
        assert data == {}

    def test_save_default_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        e = LocalMetricsEngine()
        e.record("x", 1.0)
        p = save_metrics(e)
        assert p.name == "metrics.json"
        assert p.exists()
