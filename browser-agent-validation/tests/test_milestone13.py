from __future__ import annotations

import pytest

from app.models.base import BrowserResult, RiskLevel, TrustDecision, ValidationResult
from app.retry.engine import RetryEngine
from app.retry.models import RetryAttempt, RetryConfig, RetryResult


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0, score=55.0) -> ValidationResult:
    return ValidationResult(
        decision=decision,
        confidence=confidence,
        risk_level=risk,
        policy_score=score,
        violations=[],
        reason="test",
    )


def _good_result() -> BrowserResult:
    return BrowserResult(
        summary="A " * 60,
        sources=["Source A", "Source B"],
        urls=["https://example.com"],
        latency_ms=100.0,
    )


def _bad_result() -> BrowserResult:
    return BrowserResult(summary="", sources=[], urls=[], latency_ms=0.0)


# ── RetryConfig ───────────────────────────────────────────────────────────────


class TestRetryConfig:
    def test_default_max_attempts(self):
        assert RetryConfig().max_attempts == 3

    def test_default_initial_delay_ms(self):
        assert RetryConfig().initial_delay_ms == pytest.approx(500.0)

    def test_default_backoff_factor(self):
        assert RetryConfig().backoff_factor == pytest.approx(2.0)

    def test_default_jitter(self):
        assert RetryConfig().jitter is True

    def test_default_max_delay_ms(self):
        assert RetryConfig().max_delay_ms == pytest.approx(10_000.0)

    def test_default_retryable_risk_levels(self):
        levels = RetryConfig().retryable_risk_levels
        assert "HIGH" in levels
        assert "MEDIUM" in levels

    def test_default_retryable_not_critical(self):
        assert "CRITICAL" not in RetryConfig().retryable_risk_levels

    def test_custom_max_attempts(self):
        assert RetryConfig(max_attempts=5).max_attempts == 5

    def test_custom_delay(self):
        assert RetryConfig(initial_delay_ms=100.0).initial_delay_ms == pytest.approx(100.0)

    def test_model_dump_roundtrip(self):
        cfg = RetryConfig(max_attempts=2, initial_delay_ms=250.0)
        data = cfg.model_dump()
        restored = RetryConfig.model_validate(data)
        assert restored.max_attempts == 2
        assert restored.initial_delay_ms == pytest.approx(250.0)


# ── RetryAttempt ──────────────────────────────────────────────────────────────


class TestRetryAttempt:
    def test_construction(self):
        a = RetryAttempt(attempt=1, decision="BLOCK", confidence=40.0, policy_score=55.0, risk_level="HIGH")
        assert a.attempt == 1
        assert a.decision == "BLOCK"

    def test_default_delay_ms_after(self):
        a = RetryAttempt(attempt=1, decision="BLOCK", confidence=40.0, policy_score=55.0, risk_level="HIGH")
        assert a.delay_ms_after == 0.0

    def test_custom_delay_ms_after(self):
        a = RetryAttempt(attempt=1, decision="BLOCK", confidence=40.0, policy_score=55.0, risk_level="HIGH", delay_ms_after=500.0)
        assert a.delay_ms_after == pytest.approx(500.0)

    def test_serialization(self):
        a = RetryAttempt(attempt=2, decision="ALLOW", confidence=85.0, policy_score=90.0, risk_level="LOW")
        data = a.model_dump()
        assert data["attempt"] == 2
        assert data["decision"] == "ALLOW"


# ── RetryResult ───────────────────────────────────────────────────────────────


class TestRetryResult:
    def test_construction(self):
        rr = RetryResult(total_attempts=2, final_decision="ALLOW", final_confidence=85.0, final_policy_score=90.0, retried=True)
        assert rr.total_attempts == 2
        assert rr.retried is True

    def test_retried_false(self):
        rr = RetryResult(total_attempts=1, final_decision="BLOCK", final_confidence=40.0, final_policy_score=55.0, retried=False)
        assert rr.retried is False

    def test_attempts_default_empty(self):
        rr = RetryResult(total_attempts=1, final_decision="BLOCK", final_confidence=40.0, final_policy_score=55.0, retried=False)
        assert rr.attempts == []

    def test_attempts_list(self):
        a = RetryAttempt(attempt=1, decision="BLOCK", confidence=40.0, policy_score=55.0, risk_level="HIGH")
        rr = RetryResult(total_attempts=1, final_decision="BLOCK", final_confidence=40.0, final_policy_score=55.0, retried=False, attempts=[a])
        assert len(rr.attempts) == 1


# ── RetryEngine — delay math ──────────────────────────────────────────────────


class TestRetryEngineDelay:
    def _engine(self, **kwargs) -> RetryEngine:
        return RetryEngine(RetryConfig(jitter=False, **kwargs))

    def test_delay_retry1_equals_initial(self):
        engine = self._engine(initial_delay_ms=500.0, backoff_factor=2.0)
        assert engine.delay_ms(1) == pytest.approx(500.0)

    def test_delay_retry2_doubles(self):
        engine = self._engine(initial_delay_ms=500.0, backoff_factor=2.0)
        assert engine.delay_ms(2) == pytest.approx(1000.0)

    def test_delay_retry3(self):
        engine = self._engine(initial_delay_ms=500.0, backoff_factor=2.0)
        assert engine.delay_ms(3) == pytest.approx(2000.0)

    def test_delay_capped_at_max(self):
        engine = self._engine(initial_delay_ms=500.0, backoff_factor=2.0, max_delay_ms=600.0)
        assert engine.delay_ms(2) == pytest.approx(600.0)

    def test_delay_with_jitter_in_range(self):
        engine = RetryEngine(RetryConfig(initial_delay_ms=500.0, jitter=True))
        d = engine.delay_ms(1)
        assert 375.0 <= d <= 625.0  # ±25% of 500

    def test_delay_custom_factor(self):
        engine = self._engine(initial_delay_ms=100.0, backoff_factor=3.0)
        assert engine.delay_ms(1) == pytest.approx(100.0)
        assert engine.delay_ms(2) == pytest.approx(300.0)
        assert engine.delay_ms(3) == pytest.approx(900.0)

    def test_delay_zero_initial(self):
        engine = self._engine(initial_delay_ms=0.0)
        assert engine.delay_ms(1) == pytest.approx(0.0)
        assert engine.delay_ms(2) == pytest.approx(0.0)


# ── RetryEngine — retryable checks ───────────────────────────────────────────


class TestRetryEngineRetryable:
    def _engine(self) -> RetryEngine:
        return RetryEngine(RetryConfig(jitter=False))

    def test_high_risk_is_retryable(self):
        engine = self._engine()
        assert engine.is_retryable(_vr(risk=RiskLevel.HIGH)) is True

    def test_medium_risk_is_retryable(self):
        engine = self._engine()
        assert engine.is_retryable(_vr(risk=RiskLevel.MEDIUM)) is True

    def test_critical_risk_not_retryable(self):
        engine = self._engine()
        assert engine.is_retryable(_vr(risk=RiskLevel.CRITICAL)) is False

    def test_low_risk_not_retryable_by_default(self):
        engine = self._engine()
        assert engine.is_retryable(_vr(risk=RiskLevel.LOW)) is False

    def test_custom_retryable_levels(self):
        engine = RetryEngine(RetryConfig(retryable_risk_levels=["LOW", "MEDIUM", "HIGH"]))
        assert engine.is_retryable(_vr(risk=RiskLevel.LOW)) is True
        assert engine.is_retryable(_vr(risk=RiskLevel.CRITICAL)) is False

    def test_should_retry_within_attempts(self):
        engine = RetryEngine(RetryConfig(max_attempts=3, jitter=False))
        assert engine.should_retry(1, _vr(risk=RiskLevel.HIGH)) is True
        assert engine.should_retry(2, _vr(risk=RiskLevel.HIGH)) is True

    def test_should_retry_at_max_returns_false(self):
        engine = RetryEngine(RetryConfig(max_attempts=3, jitter=False))
        assert engine.should_retry(3, _vr(risk=RiskLevel.HIGH)) is False

    def test_should_retry_not_retryable_returns_false(self):
        engine = RetryEngine(RetryConfig(max_attempts=3, jitter=False))
        assert engine.should_retry(1, _vr(risk=RiskLevel.CRITICAL)) is False

    def test_summary_has_all_keys(self):
        engine = self._engine()
        s = engine.summary()
        for k in ("max_attempts", "initial_delay_ms", "backoff_factor", "jitter", "max_delay_ms", "retryable_risk_levels"):
            assert k in s


# ── PolicyConfig now has retry field ─────────────────────────────────────────


class TestPolicyConfigRetry:
    def test_policy_has_retry_field(self):
        from app.policies.models import PolicyConfig
        cfg = PolicyConfig()
        assert hasattr(cfg, "retry")

    def test_policy_retry_is_retry_config(self):
        from app.policies.models import PolicyConfig
        cfg = PolicyConfig()
        assert isinstance(cfg.retry, RetryConfig)

    def test_policy_retry_default_max_attempts(self):
        from app.policies.models import PolicyConfig
        assert PolicyConfig().retry.max_attempts == 3

    def test_policy_custom_retry(self):
        from app.policies.models import PolicyConfig
        cfg = PolicyConfig(retry=RetryConfig(max_attempts=5, initial_delay_ms=100.0))
        assert cfg.retry.max_attempts == 5
        assert cfg.retry.initial_delay_ms == pytest.approx(100.0)

    def test_default_yaml_has_retry(self):
        from app.policies.loader import load_default_policy
        cfg = load_default_policy()
        assert cfg.retry.max_attempts == 3
        assert cfg.retry.initial_delay_ms == pytest.approx(500.0)


# ── GovernedBrowserAgent with RetryEngine ────────────────────────────────────


def _make_stub_middleware(results: list[ValidationResult]):
    """Stub middleware returning successive ValidationResults."""
    from app.agenttrust.interfaces import TrustMiddleware

    class _StubMW(TrustMiddleware):
        def __init__(self):
            self._idx = 0

        def validate(self, query, result):
            vr = results[min(self._idx, len(results) - 1)]
            self._idx += 1
            return vr

        def wrap(self, query, result):
            return result

    return _StubMW()


def _make_stub_agent(results: list[BrowserResult] | None = None):
    from app.browser_agent.interfaces import BrowserAgentBase

    class _StubAgent(BrowserAgentBase):
        def __init__(self):
            self._idx = 0
            self._results = results or [_good_result()]

        def run(self, query):
            r = self._results[min(self._idx, len(self._results) - 1)]
            self._idx += 1
            return r

    return _StubAgent()


class TestGovernedAgentWithRetry:
    def _cfg(self) -> RetryConfig:
        return RetryConfig(max_attempts=3, initial_delay_ms=0.0, jitter=False)

    def test_no_retry_engine_no_retry_result(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        mw = _make_stub_middleware([_vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0)])
        gov = GovernedBrowserAgent(_make_stub_agent(), middleware=mw)
        gov.run("test query")
        assert gov.last_retry_result is None

    def test_retry_succeeds_on_second_attempt(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.agenttrust.exceptions import BlockedError
        mw = _make_stub_middleware([
            _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0, score=55.0),
            _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0),
        ])
        engine = RetryEngine(self._cfg())
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result(), _good_result()]), middleware=mw, retry_engine=engine)
        result = gov.run("test query")
        assert result is not None
        assert gov.last_retry_result is not None
        assert gov.last_retry_result.retried is True

    def test_retry_all_fail_raises_blocked(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.agenttrust.exceptions import BlockedError
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        mw = _make_stub_middleware([block_vr] * 10)
        engine = RetryEngine(RetryConfig(max_attempts=2, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 10), middleware=mw, retry_engine=engine)
        with pytest.raises(BlockedError):
            gov.run("test query")

    def test_retry_total_attempts_correct(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.agenttrust.exceptions import BlockedError
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        mw = _make_stub_middleware([block_vr] * 10)
        engine = RetryEngine(RetryConfig(max_attempts=3, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 10), middleware=mw, retry_engine=engine)
        with pytest.raises(BlockedError):
            gov.run("test query")
        assert gov.last_retry_result.total_attempts == 3

    def test_retry_not_retryable_critical_no_retry(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.agenttrust.exceptions import BlockedError
        crit_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.CRITICAL, confidence=0.0, score=0.0)
        mw = _make_stub_middleware([crit_vr])
        engine = RetryEngine(self._cfg())
        gov = GovernedBrowserAgent(_make_stub_agent(), middleware=mw, retry_engine=engine)
        with pytest.raises(BlockedError):
            gov.run("test query")
        assert gov.last_retry_result.total_attempts == 1
        assert gov.last_retry_result.retried is False

    def test_retry_result_cleared_between_runs(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        allow_vr = _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0)
        mw = _make_stub_middleware([block_vr, allow_vr, allow_vr])
        engine = RetryEngine(RetryConfig(max_attempts=2, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 10), middleware=mw, retry_engine=engine)
        # first run: block → retry → allow
        gov.run("q")
        rr1 = gov.last_retry_result
        assert rr1 is not None and rr1.retried
        # second run: allow immediately
        gov.run("q")
        assert gov.last_retry_result is None  # cleared because no BLOCK in second run

    def test_attempts_list_length_matches_total(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.agenttrust.exceptions import BlockedError
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        mw = _make_stub_middleware([block_vr] * 10)
        engine = RetryEngine(RetryConfig(max_attempts=3, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 10), middleware=mw, retry_engine=engine)
        with pytest.raises(BlockedError):
            gov.run("q")
        assert len(gov.last_retry_result.attempts) == gov.last_retry_result.total_attempts

    def test_last_attempt_delay_is_zero(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        from app.agenttrust.exceptions import BlockedError
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        mw = _make_stub_middleware([block_vr] * 10)
        engine = RetryEngine(RetryConfig(max_attempts=3, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 10), middleware=mw, retry_engine=engine)
        with pytest.raises(BlockedError):
            gov.run("q")
        assert gov.last_retry_result.attempts[-1].delay_ms_after == 0.0

    def test_retry_sets_last_validation_to_final_vr(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH, confidence=40.0, score=55.0)
        allow_vr = _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0)
        mw = _make_stub_middleware([block_vr, allow_vr])
        engine = RetryEngine(RetryConfig(max_attempts=2, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 5), middleware=mw, retry_engine=engine)
        gov.run("q")
        assert gov.last_validation.decision == TrustDecision.ALLOW

    def test_last_retry_result_final_decision_matches(self):
        from app.agenttrust.governed_agent import GovernedBrowserAgent
        block_vr = _vr(decision=TrustDecision.BLOCK, risk=RiskLevel.HIGH)
        allow_vr = _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0)
        mw = _make_stub_middleware([block_vr, allow_vr])
        engine = RetryEngine(RetryConfig(max_attempts=2, initial_delay_ms=0.0, jitter=False))
        gov = GovernedBrowserAgent(_make_stub_agent([_good_result()] * 5), middleware=mw, retry_engine=engine)
        gov.run("q")
        assert gov.last_retry_result.final_decision == "ALLOW"
