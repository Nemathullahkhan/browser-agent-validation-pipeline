from app.models.base import (
    AuditEvent,
    BrowserResult,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTrace,
    RiskLevel,
    TrustDecision,
    ValidationResult,
)
from app.browser_agent.interfaces import BrowserAgentBase, Summarizer
from app.execution.interfaces import ExecutionContext
from app.agenttrust.interfaces import TrustMiddleware, PolicyEngine, AuditLogger
from app.audit.interfaces import AuditStore
from app.metrics.interfaces import MetricsEngine
from app.comparison.interfaces import ComparisonRunner


def test_browser_result_model():
    r = BrowserResult(summary="test", sources=["http://a.com"], urls=["http://a.com"])
    assert r.summary == "test"
    assert r.sources == ["http://a.com"]


def test_execution_trace_model():
    trace = ExecutionTrace(execution_id="id-1", query="test query")
    assert trace.status == ExecutionStatus.PENDING
    assert trace.events == []


def test_validation_result_model():
    v = ValidationResult(decision=TrustDecision.ALLOW, confidence=95.0)
    assert v.decision == TrustDecision.ALLOW
    assert v.confidence == 95.0


def test_trust_decision_enum():
    assert TrustDecision.ALLOW == "ALLOW"
    assert TrustDecision.BLOCK == "BLOCK"
    assert TrustDecision.RETRY == "RETRY"
    assert TrustDecision.HUMAN_REVIEW == "HUMAN_REVIEW"


def test_risk_level_enum():
    assert RiskLevel.LOW == "LOW"
    assert RiskLevel.CRITICAL == "CRITICAL"


def test_execution_context():
    ctx = ExecutionContext(execution_id="exec-1", query="test")
    assert ctx.execution_id == "exec-1"
    assert ctx.trace.query == "test"


def test_interfaces_are_abstract():
    import inspect
    assert inspect.isabstract(BrowserAgentBase)
    assert inspect.isabstract(Summarizer)
    assert inspect.isabstract(TrustMiddleware)
    assert inspect.isabstract(PolicyEngine)
    assert inspect.isabstract(AuditLogger)
    assert inspect.isabstract(AuditStore)
    assert inspect.isabstract(MetricsEngine)
    assert inspect.isabstract(ComparisonRunner)
