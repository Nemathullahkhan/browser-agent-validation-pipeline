from __future__ import annotations

import pytest

from app.agenttrust.validation import ValidationContext
from app.models.base import BrowserResult, RiskLevel, TrustDecision
from app.scenarios.base import ScenarioBase, ScenarioResult
from app.scenarios.scenarios import (
    SCENARIOS,
    EmptyResponseScenario,
    LowConfidenceScenario,
    PromptInjectionScenario,
    ScriptInjectionScenario,
    SensitiveDataLeakScenario,
    run_all_scenarios,
)


# ── ValidationContext — URL checks ─────────────────────────────────────────────

class TestUrlValidation:
    def test_valid_https_url_no_violation(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Source"],
            urls=["https://example.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        url_violations = [v for v in vr.violations if "url" in v.lower() or "scheme" in v.lower()]
        assert url_violations == []

    def test_valid_http_url_no_violation(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Source"],
            urls=["http://example.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        url_violations = [v for v in vr.violations if "url" in v.lower() or "scheme" in v.lower()]
        assert url_violations == []

    def test_javascript_url_is_critical(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Src"],
            urls=["javascript:alert(1)"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0
        assert vr.decision == TrustDecision.BLOCK
        assert any("dangerous" in v.lower() or "scheme" in v.lower() for v in vr.violations)

    def test_data_url_is_critical(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Src"],
            urls=["data:text/html,<script>xss</script>"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0

    def test_vbscript_url_is_critical(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Src"],
            urls=["vbscript:MsgBox(1)"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0

    def test_file_url_is_high_violation(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Src"],
            urls=["file:///etc/passwd"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        url_violations = [v for v in vr.violations if "url" in v.lower() or "scheme" in v.lower() or "invalid" in v.lower()]
        assert url_violations
        # Not CRITICAL, so policy score not zero
        assert vr.policy_score > 0.0

    def test_empty_urls_list_no_violation(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Src"],
            urls=[],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        url_violations = [v for v in vr.violations if "url" in v.lower() or "scheme" in v.lower()]
        assert url_violations == []

    def test_multiple_javascript_urls_reports_count(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["Src"],
            urls=["javascript:a()", "javascript:b()"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0
        assert any("2" in v for v in vr.violations)

    def test_file_url_drops_confidence(self):
        ctx_clean = ValidationContext()
        ctx_clean.check_result(BrowserResult(
            summary="A " * 30, sources=["S"], urls=["https://a.com"], latency_ms=0.0
        ))
        vr_clean = ctx_clean.finalize()

        ctx_bad = ValidationContext()
        ctx_bad.check_result(BrowserResult(
            summary="A " * 30, sources=["S"], urls=["file:///bad"], latency_ms=0.0
        ))
        vr_bad = ctx_bad.finalize()

        assert vr_bad.confidence < vr_clean.confidence


# ── ValidationContext — PII checks ─────────────────────────────────────────────

class TestPiiValidation:
    def test_ssn_in_summary_is_critical(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="Patient SSN: 523-87-4291 found in records. Additional details follow here.",
            sources=["EHR"],
            urls=["https://ehr.example.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0
        assert any("ssn" in v.lower() for v in vr.violations)

    def test_credit_card_in_summary_is_critical(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="Payment card on file: 4532 1234 5678 9012. Transaction approved successfully.",
            sources=["Payment System"],
            urls=["https://payments.example.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0
        assert any("credit card" in v.lower() for v in vr.violations)

    def test_credit_card_with_dashes(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="Card: 4532-1234-5678-9012. Please keep this confidential, it is sensitive data.",
            sources=["Billing"],
            urls=["https://billing.example.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0

    def test_clean_summary_no_pii_violation(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary=(
                "The Model Context Protocol is an open standard developed by Anthropic "
                "that enables AI models to connect to external data sources and tools."
            ),
            sources=["Anthropic"],
            urls=["https://anthropic.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        pii_violations = [v for v in vr.violations if "ssn" in v.lower() or "credit" in v.lower()]
        assert pii_violations == []

    def test_ssn_blocks_output(self):
        from app.agenttrust.middleware import AgentTrustMiddleware
        from app.agenttrust.exceptions import BlockedError
        mw = AgentTrustMiddleware()
        bad = BrowserResult(
            summary="Record: SSN 123-45-6789 located in the database. All other fields are normal.",
            sources=["DB"],
            urls=["https://db.example.com"],
            latency_ms=0.0,
        )
        with pytest.raises(BlockedError):
            mw.wrap("lookup", bad)


# ── ValidationContext — empty summary is now CRITICAL ────────────────────────

class TestEmptySummaryCritical:
    def test_empty_summary_policy_score_zero(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(summary="", sources=[], urls=[], latency_ms=0.0))
        vr = ctx.finalize()
        assert vr.policy_score == 0.0

    def test_empty_summary_blocks(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(summary="", sources=[], urls=[], latency_ms=0.0))
        vr = ctx.finalize()
        assert vr.decision == TrustDecision.BLOCK

    def test_empty_summary_violation_message(self):
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(summary="", sources=[], urls=[], latency_ms=0.0))
        vr = ctx.finalize()
        assert any("summary" in v.lower() or "empty" in v.lower() for v in vr.violations)


# ── ScenarioResult model ───────────────────────────────────────────────────────

class TestScenarioResult:
    def test_construction(self):
        r = ScenarioResult(
            scenario_name="Test",
            description="desc",
            query="q",
            raw_result=BrowserResult(summary="s", sources=[], urls=[], latency_ms=0.0),
            raw_passed=True,
        )
        assert r.scenario_name == "Test"
        assert r.raw_passed is True
        assert r.governed_blocked is False

    def test_defaults(self):
        r = ScenarioResult(
            scenario_name="X",
            description="d",
            query="q",
            raw_result=BrowserResult(summary="s", sources=[], urls=[], latency_ms=0.0),
            raw_passed=True,
        )
        assert r.governed_result is None
        assert r.governed_blocked is False
        assert r.input_blocked is False
        assert r.output_blocked is False
        assert r.governed_decision == ""
        assert r.governance_reason == ""

    def test_serialization(self):
        r = ScenarioResult(
            scenario_name="Test",
            description="d",
            query="q",
            raw_result=BrowserResult(summary="s", sources=[], urls=[], latency_ms=0.0),
            raw_passed=True,
            governed_blocked=True,
            governed_decision="BLOCK",
        )
        data = r.model_dump()
        assert data["governed_decision"] == "BLOCK"
        assert data["governed_blocked"] is True


# ── ScenarioBase is abstract ──────────────────────────────────────────────────

class TestScenarioBase:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            ScenarioBase()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        s = PromptInjectionScenario()
        assert s.name == "Prompt Injection"
        assert s.query


# ── Scenario 1: Prompt Injection ──────────────────────────────────────────────

_PI = PromptInjectionScenario().run()
_SI = ScriptInjectionScenario().run()
_ER = EmptyResponseScenario().run()
_SD = SensitiveDataLeakScenario().run()
_LC = LowConfidenceScenario().run()
_ALL = run_all_scenarios()


class TestPromptInjection:
    def test_returns_scenario_result(self):
        assert isinstance(_PI, ScenarioResult)

    def test_scenario_name(self):
        assert _PI.scenario_name == "Prompt Injection"

    def test_raw_passed(self):
        assert _PI.raw_passed is True

    def test_raw_result_has_summary(self):
        assert _PI.raw_result.summary

    def test_governed_is_blocked(self):
        assert _PI.governed_blocked is True

    def test_blocked_at_input_stage(self):
        assert _PI.input_blocked is True

    def test_output_not_blocked(self):
        assert _PI.output_blocked is False

    def test_governed_decision_is_block(self):
        assert _PI.governed_decision == "BLOCK"

    def test_governance_reason_set(self):
        assert _PI.governance_reason

    def test_governed_result_is_none(self):
        assert _PI.governed_result is None

    def test_query_contains_injection(self):
        assert "ignore" in _PI.query.lower() or "instructions" in _PI.query.lower()


# ── Scenario 2: Script Injection ──────────────────────────────────────────────

class TestScriptInjection:
    def test_raw_passed(self):
        assert _SI.raw_passed is True

    def test_raw_result_has_javascript_url(self):
        assert any("javascript" in u for u in _SI.raw_result.urls)

    def test_governed_is_blocked(self):
        assert _SI.governed_blocked is True

    def test_blocked_at_output_stage(self):
        assert _SI.output_blocked is True

    def test_input_not_blocked(self):
        assert _SI.input_blocked is False

    def test_governed_decision_is_block(self):
        assert _SI.governed_decision == "BLOCK"

    def test_governance_reason_set(self):
        assert _SI.governance_reason


# ── Scenario 3: Empty Response ────────────────────────────────────────────────

class TestEmptyResponse:
    def test_raw_passed(self):
        assert _ER.raw_passed is True

    def test_raw_result_summary_is_empty(self):
        assert _ER.raw_result.summary == ""

    def test_governed_is_blocked(self):
        assert _ER.governed_blocked is True

    def test_blocked_at_output_stage(self):
        assert _ER.output_blocked is True

    def test_input_not_blocked(self):
        assert _ER.input_blocked is False

    def test_governed_decision_is_block(self):
        assert _ER.governed_decision == "BLOCK"


# ── Scenario 4: Sensitive Data Leak ───────────────────────────────────────────

class TestSensitiveDataLeak:
    def test_raw_passed(self):
        assert _SD.raw_passed is True

    def test_raw_result_contains_ssn(self):
        import re
        assert re.search(r"\d{3}-\d{2}-\d{4}", _SD.raw_result.summary)

    def test_governed_is_blocked(self):
        assert _SD.governed_blocked is True

    def test_blocked_at_output_stage(self):
        assert _SD.output_blocked is True

    def test_input_not_blocked(self):
        assert _SD.input_blocked is False

    def test_governed_decision_is_block(self):
        assert _SD.governed_decision == "BLOCK"


# ── Scenario 5: Low Confidence ────────────────────────────────────────────────

class TestLowConfidence:
    def test_raw_passed(self):
        assert _LC.raw_passed is True

    def test_raw_result_has_short_summary(self):
        assert len(_LC.raw_result.summary) < 50

    def test_raw_result_has_no_sources(self):
        assert _LC.raw_result.sources == []

    def test_raw_result_has_invalid_url(self):
        assert any(u.startswith("file://") for u in _LC.raw_result.urls)

    def test_governed_is_blocked(self):
        assert _LC.governed_blocked is True

    def test_blocked_at_output_stage(self):
        assert _LC.output_blocked is True

    def test_input_not_blocked(self):
        assert _LC.input_blocked is False

    def test_governed_decision_is_block(self):
        assert _LC.governed_decision == "BLOCK"


# ── run_all_scenarios ─────────────────────────────────────────────────────────

class TestRunAllScenarios:
    def test_returns_five_results(self):
        assert len(_ALL) == 5

    def test_all_are_scenario_results(self):
        assert all(isinstance(r, ScenarioResult) for r in _ALL)

    def test_all_raw_passed(self):
        assert all(r.raw_passed for r in _ALL)

    def test_all_governed_blocked(self):
        assert all(r.governed_blocked for r in _ALL)

    def test_all_governed_decision_is_block(self):
        assert all(r.governed_decision == "BLOCK" for r in _ALL)

    def test_scenario_names_unique(self):
        names = [r.scenario_name for r in _ALL]
        assert len(names) == len(set(names))

    def test_scenarios_list_has_five(self):
        assert len(SCENARIOS) == 5

    def test_first_is_prompt_injection(self):
        assert _ALL[0].input_blocked is True

    def test_remaining_are_output_blocked(self):
        assert all(r.output_blocked for r in _ALL[1:])
