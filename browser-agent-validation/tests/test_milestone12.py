from __future__ import annotations

import pytest

from app.policies.engine import PolicyEngine
from app.policies.loader import (
    PolicyLoader,
    YamlPolicyLoader,
    load_default_policy,
    load_policy,
)
from app.policies.models import (
    ConfidenceAdjustments,
    DecisionThresholds,
    InputRules,
    OutputRules,
    PolicyConfig,
    ViolationPenalties,
)


# ── PolicyConfig — defaults ───────────────────────────────────────────────────


class TestPolicyConfigDefaults:
    def test_default_name(self):
        assert PolicyConfig().name == "default"

    def test_default_version(self):
        assert PolicyConfig().version == "1.0"

    def test_default_description_empty(self):
        assert PolicyConfig().description == ""

    def test_default_block_confidence(self):
        assert PolicyConfig().thresholds.block_confidence == 50.0

    def test_default_block_policy_score(self):
        assert PolicyConfig().thresholds.block_policy_score == 60.0

    def test_default_approve_confidence(self):
        assert PolicyConfig().thresholds.approve_confidence == 90.0

    def test_default_approve_combined_policy(self):
        assert PolicyConfig().thresholds.approve_combined_policy == 60.0

    def test_default_approve_combined_confidence(self):
        assert PolicyConfig().thresholds.approve_combined_confidence == 70.0

    def test_default_high_penalty(self):
        assert PolicyConfig().penalties.high == 25.0

    def test_default_medium_penalty(self):
        assert PolicyConfig().penalties.medium == 10.0

    def test_default_low_penalty(self):
        assert PolicyConfig().penalties.low == 5.0

    def test_default_initial_confidence(self):
        assert PolicyConfig().confidence.initial == 80.0

    def test_default_no_sources_penalty(self):
        assert PolicyConfig().confidence.no_sources_penalty == 20.0

    def test_default_invalid_url_penalty(self):
        assert PolicyConfig().confidence.invalid_url_penalty == 15.0

    def test_default_min_summary_length(self):
        assert PolicyConfig().output.min_summary_length == 50

    def test_default_max_query_length(self):
        assert PolicyConfig().input.max_query_length == 2000


class TestPolicyConfigCustom:
    def test_custom_name(self):
        cfg = PolicyConfig(name="strict")
        assert cfg.name == "strict"

    def test_custom_thresholds(self):
        cfg = PolicyConfig(thresholds=DecisionThresholds(block_confidence=40.0))
        assert cfg.thresholds.block_confidence == 40.0

    def test_custom_penalties(self):
        cfg = PolicyConfig(penalties=ViolationPenalties(high=50.0))
        assert cfg.penalties.high == 50.0

    def test_custom_input_max_length(self):
        cfg = PolicyConfig(input=InputRules(max_query_length=100))
        assert cfg.input.max_query_length == 100

    def test_custom_output_min_summary(self):
        cfg = PolicyConfig(output=OutputRules(min_summary_length=20))
        assert cfg.output.min_summary_length == 20

    def test_partial_thresholds_keep_defaults(self):
        cfg = PolicyConfig(thresholds=DecisionThresholds(block_confidence=40.0))
        assert cfg.thresholds.block_policy_score == 60.0  # default preserved

    def test_model_dump_round_trip(self):
        cfg = PolicyConfig(name="test", version="2.0")
        data = cfg.model_dump()
        restored = PolicyConfig.model_validate(data)
        assert restored.name == "test"
        assert restored.version == "2.0"


# ── YamlPolicyLoader ──────────────────────────────────────────────────────────


class TestYamlPolicyLoader:
    def test_loads_default_yaml(self):
        from pathlib import Path
        default = Path(__file__).parent.parent / "app" / "policies" / "default.yaml"
        loader = YamlPolicyLoader(default)
        cfg = loader.load()
        assert isinstance(cfg, PolicyConfig)

    def test_default_yaml_name(self):
        from pathlib import Path
        default = Path(__file__).parent.parent / "app" / "policies" / "default.yaml"
        cfg = YamlPolicyLoader(default).load()
        assert cfg.name == "default"

    def test_default_yaml_thresholds_match_defaults(self):
        from pathlib import Path
        default = Path(__file__).parent.parent / "app" / "policies" / "default.yaml"
        cfg = YamlPolicyLoader(default).load()
        assert cfg.thresholds.block_confidence == pytest.approx(50.0)
        assert cfg.thresholds.block_policy_score == pytest.approx(60.0)

    def test_path_property(self, tmp_path):
        p = tmp_path / "policy.yaml"
        loader = YamlPolicyLoader(p)
        assert loader.path == p

    def test_missing_file_raises_file_not_found(self, tmp_path):
        loader = YamlPolicyLoader(tmp_path / "missing.yaml")
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_custom_yaml_overrides(self, tmp_path):
        import yaml
        p = tmp_path / "custom.yaml"
        data = {
            "name": "strict",
            "version": "2.0",
            "thresholds": {"block_confidence": 70.0},
        }
        p.write_text(yaml.dump(data))
        cfg = YamlPolicyLoader(p).load()
        assert cfg.name == "strict"
        assert cfg.thresholds.block_confidence == pytest.approx(70.0)
        assert cfg.thresholds.block_policy_score == pytest.approx(60.0)  # default

    def test_empty_yaml_uses_all_defaults(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        cfg = YamlPolicyLoader(p).load()
        assert cfg.thresholds.block_confidence == pytest.approx(50.0)

    def test_is_policy_loader_subclass(self, tmp_path):
        loader = YamlPolicyLoader(tmp_path / "p.yaml")
        assert isinstance(loader, PolicyLoader)

    def test_loader_is_abstract(self):
        with pytest.raises(TypeError):
            PolicyLoader()  # type: ignore[abstract]


# ── load_default_policy / load_policy ────────────────────────────────────────


class TestLoadFunctions:
    def test_load_default_returns_policy_config(self):
        cfg = load_default_policy()
        assert isinstance(cfg, PolicyConfig)

    def test_load_policy_none_returns_default(self):
        cfg = load_policy(None)
        assert isinstance(cfg, PolicyConfig)
        assert cfg.thresholds.block_confidence == pytest.approx(50.0)

    def test_load_policy_custom_path(self, tmp_path):
        import yaml
        p = tmp_path / "policy.yaml"
        p.write_text(yaml.dump({"name": "custom"}))
        cfg = load_policy(p)
        assert cfg.name == "custom"

    def test_load_policy_string_path(self, tmp_path):
        import yaml
        p = tmp_path / "policy.yaml"
        p.write_text(yaml.dump({"name": "from_str"}))
        cfg = load_policy(str(p))
        assert cfg.name == "from_str"


# ── PolicyEngine ──────────────────────────────────────────────────────────────


class TestPolicyEngine:
    def test_default_config(self):
        engine = PolicyEngine()
        assert isinstance(engine.config, PolicyConfig)

    def test_custom_config(self):
        cfg = PolicyConfig(name="custom")
        engine = PolicyEngine(cfg)
        assert engine.config.name == "custom"

    def test_penalty_high(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.penalty_for("HIGH") == pytest.approx(25.0)

    def test_penalty_medium(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.penalty_for("MEDIUM") == pytest.approx(10.0)

    def test_penalty_low(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.penalty_for("LOW") == pytest.approx(5.0)

    def test_penalty_critical_returns_zero(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.penalty_for("CRITICAL") == pytest.approx(0.0)

    def test_penalty_unknown_returns_zero(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.penalty_for("UNKNOWN") == pytest.approx(0.0)

    def test_is_block_confidence_below_threshold(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_block_confidence(49.9) is True

    def test_is_block_confidence_at_threshold(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_block_confidence(50.0) is False

    def test_is_block_confidence_above(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_block_confidence(80.0) is False

    def test_is_block_policy_score_below(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_block_policy_score(59.9) is True

    def test_is_block_policy_score_at_threshold(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_block_policy_score(60.0) is False

    def test_is_auto_approve_at_threshold(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_auto_approve_confidence(90.0) is True

    def test_is_auto_approve_below(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_auto_approve_confidence(89.9) is False

    def test_is_combined_approve_true(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_combined_approve(60.0, 70.0) is True

    def test_is_combined_approve_score_too_low(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_combined_approve(59.9, 70.0) is False

    def test_is_combined_approve_confidence_too_low(self):
        engine = PolicyEngine(PolicyConfig())
        assert engine.is_combined_approve(60.0, 69.9) is False

    def test_summary_has_all_keys(self):
        engine = PolicyEngine(PolicyConfig())
        s = engine.summary()
        for key in ("name", "version", "description", "thresholds", "penalties", "confidence", "input", "output"):
            assert key in s

    def test_summary_thresholds_is_dict(self):
        engine = PolicyEngine(PolicyConfig())
        assert isinstance(engine.summary()["thresholds"], dict)

    def test_custom_penalty_reflected_in_engine(self):
        cfg = PolicyConfig(penalties=ViolationPenalties(high=50.0))
        engine = PolicyEngine(cfg)
        assert engine.penalty_for("HIGH") == pytest.approx(50.0)


# ── ValidationContext respects custom PolicyConfig ───────────────────────────


class TestValidationContextWithPolicy:
    def test_default_policy_same_behavior(self):
        from app.agenttrust.validation import ValidationContext
        from app.models.base import BrowserResult, TrustDecision
        ctx = ValidationContext()
        ctx.check_result(BrowserResult(
            summary="A " * 30, sources=["S"], urls=["https://a.com"], latency_ms=0.0
        ))
        vr = ctx.finalize()
        assert vr.decision == TrustDecision.ALLOW

    def test_custom_block_confidence_threshold(self):
        from app.agenttrust.validation import ValidationContext
        from app.models.base import BrowserResult, TrustDecision
        # With default policy, confidence starts at 80 then -5 (short) -20 (no sources) -15 (file://) = 40 → BLOCK
        # With lower threshold (40), confidence=40 is NOT below 40, so should ALLOW
        cfg = PolicyConfig(thresholds=DecisionThresholds(block_confidence=30.0))
        ctx = ValidationContext(policy=cfg)
        ctx.check_result(BrowserResult(
            summary="See attached.",
            sources=[],
            urls=["file:///bad"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        # confidence = 80 - 5 - 20 - 15 = 40; with block_confidence=30 → not blocked by confidence
        assert vr.confidence == pytest.approx(40.0)
        assert vr.decision == TrustDecision.ALLOW

    def test_custom_high_penalty_blocks_result(self):
        from app.agenttrust.validation import ValidationContext
        from app.models.base import BrowserResult, TrustDecision
        # HIGH penalty=50 means one HIGH violation drops score from 100 to 50 → blocked (< 60)
        cfg = PolicyConfig(penalties=ViolationPenalties(high=50.0))
        ctx = ValidationContext(policy=cfg)
        ctx.check_result(BrowserResult(
            summary="A " * 30,
            sources=["S"],
            urls=["file:///bad"],  # HIGH violation
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert vr.policy_score == pytest.approx(50.0)
        assert vr.decision == TrustDecision.BLOCK

    def test_custom_max_query_length_enforced(self):
        from app.agenttrust.validation import ValidationContext
        cfg = PolicyConfig(input=InputRules(max_query_length=10))
        ctx = ValidationContext(policy=cfg)
        ctx.check_query("This query is way too long for the custom policy")
        vr = ctx.finalize()
        assert any("exceeds 10" in v for v in vr.violations)

    def test_custom_initial_confidence(self):
        from app.agenttrust.validation import ValidationContext
        from app.models.base import BrowserResult
        cfg = PolicyConfig(confidence=ConfidenceAdjustments(initial=60.0))
        ctx = ValidationContext(policy=cfg)
        ctx.check_result(BrowserResult(
            summary="A " * 30, sources=["S"], urls=["https://a.com"], latency_ms=0.0
        ))
        vr = ctx.finalize()
        # starts at 60, no penalties → 60 + source bonus
        assert vr.confidence > 60.0

    def test_custom_min_summary_length(self):
        from app.agenttrust.validation import ValidationContext
        from app.models.base import BrowserResult
        cfg = PolicyConfig(output=OutputRules(min_summary_length=200))
        ctx = ValidationContext(policy=cfg)
        ctx.check_result(BrowserResult(
            summary="Short summary here.",  # < 200 chars → LOW violation
            sources=["S"],
            urls=["https://a.com"],
            latency_ms=0.0,
        ))
        vr = ctx.finalize()
        assert any("200" in v for v in vr.violations)
