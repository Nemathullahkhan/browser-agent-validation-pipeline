from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.models.base import BrowserResult, RiskLevel, TrustDecision, ValidationResult
from app.policies.models import PolicyConfig

_INJECTION_RE = re.compile(
    r"ignore (previous|prior|above) instructions?"
    r"|system\s*:"
    r"|jailbreak"
    r"|act as (?:if )?you (are|were)"
    r"|<\s*/?system\s*>"
    r"|disregard (all|previous|prior)"
    r"|forget everything",
    re.IGNORECASE,
)

_VALID_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_DANGEROUS_SCHEME_RE = re.compile(r"^(javascript|data|vbscript):", re.IGNORECASE)

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b")


@dataclass
class _Violation:
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    message: str


class ValidationContext:
    """Accumulates violations and computes scores for one validation pass."""

    def __init__(self, policy: PolicyConfig | None = None) -> None:
        self._violations: list[_Violation] = []
        self._policy = policy or PolicyConfig()
        self._confidence: float = self._policy.confidence.initial

    # ── Input ─────────────────────────────────────────────────────────────────

    def check_query(self, query: str) -> None:
        if not query or not query.strip():
            self._violations.append(_Violation("CRITICAL", "Query is empty"))
            return

        if len(query) > self._policy.input.max_query_length:
            self._violations.append(
                _Violation("HIGH", f"Query exceeds {self._policy.input.max_query_length} characters")
            )

        if _INJECTION_RE.search(query):
            self._violations.append(_Violation("HIGH", "Potential prompt injection detected in query"))

    # ── Output ────────────────────────────────────────────────────────────────

    def check_result(self, result: BrowserResult) -> None:
        if not result.summary or not result.summary.strip():
            self._violations.append(_Violation("CRITICAL", "Response summary is empty"))
            return

        cfg_out = self._policy.output
        cfg_conf = self._policy.confidence

        if len(result.summary) < cfg_out.min_summary_length:
            self._violations.append(
                _Violation("LOW", f"Summary is very short (< {cfg_out.min_summary_length} chars)")
            )
            self._confidence -= cfg_conf.short_summary_penalty

        if not result.sources:
            self._violations.append(_Violation("MEDIUM", "No sources provided in response"))
            self._confidence -= cfg_conf.no_sources_penalty
        else:
            self._confidence += min(
                len(result.sources) * cfg_conf.per_source_bonus,
                cfg_conf.max_source_bonus,
            )

        if len(result.summary) > cfg_out.long_summary_threshold:
            self._confidence += cfg_conf.long_summary_bonus
        elif len(result.summary) > cfg_out.medium_summary_threshold:
            self._confidence += cfg_conf.medium_summary_bonus

        self._check_urls(result.urls)
        self._check_pii(result.summary)

    def _check_urls(self, urls: list[str]) -> None:
        if not urls:
            return
        critical = [u for u in urls if u and _DANGEROUS_SCHEME_RE.match(u)]
        invalid = [u for u in urls if u and not _VALID_URL_RE.match(u)]
        if critical:
            self._violations.append(
                _Violation("CRITICAL", f"Dangerous URL scheme detected in {len(critical)} URL(s)")
            )
        elif invalid:
            self._violations.append(
                _Violation("HIGH", f"Invalid URL scheme in {len(invalid)} of {len(urls)} URLs")
            )
            self._confidence -= self._policy.confidence.invalid_url_penalty

    def _check_pii(self, text: str) -> None:
        if _SSN_RE.search(text):
            self._violations.append(_Violation("CRITICAL", "Potential SSN detected in output"))
        if _CC_RE.search(text):
            self._violations.append(_Violation("CRITICAL", "Potential credit card number detected in output"))

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _policy_score(self) -> float:
        score = 100.0
        p = self._policy.penalties
        for v in self._violations:
            if v.severity == "CRITICAL":
                return 0.0
            elif v.severity == "HIGH":
                score -= p.high
            elif v.severity == "MEDIUM":
                score -= p.medium
            elif v.severity == "LOW":
                score -= p.low
        return max(score, 0.0)

    def _risk(self, policy_score: float, confidence: float) -> RiskLevel:
        t = self._policy.thresholds
        if any(v.severity == "CRITICAL" for v in self._violations):
            return RiskLevel.CRITICAL
        if policy_score < t.block_policy_score or confidence < t.block_confidence:
            return RiskLevel.HIGH
        if any(v.severity == "HIGH" for v in self._violations):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _decision(
        self, policy_score: float, confidence: float, risk: RiskLevel
    ) -> tuple[TrustDecision, str]:
        t = self._policy.thresholds
        if policy_score == 0.0:
            return TrustDecision.BLOCK, "Critical policy violation — blocked immediately"
        if risk == RiskLevel.CRITICAL:
            return TrustDecision.HUMAN_REVIEW, "Critical risk level — escalated for human review"
        if confidence < t.block_confidence:
            return TrustDecision.BLOCK, f"Confidence too low ({confidence:.0f}/100)"
        if policy_score < t.block_policy_score:
            return TrustDecision.BLOCK, f"Policy score too low ({policy_score:.0f}/100)"
        if confidence >= t.approve_confidence or (
            policy_score >= t.approve_combined_policy and confidence >= t.approve_combined_confidence
        ):
            return TrustDecision.ALLOW, "Meets confidence and policy thresholds — approved"
        return TrustDecision.ALLOW, "Approved with moderate confidence"

    def finalize(self) -> ValidationResult:
        confidence = max(0.0, min(100.0, self._confidence))
        policy_score = self._policy_score()
        risk = self._risk(policy_score, confidence)
        decision, reason = self._decision(policy_score, confidence, risk)

        return ValidationResult(
            decision=decision,
            confidence=confidence,
            risk_level=risk,
            policy_score=policy_score,
            violations=[v.message for v in self._violations],
            reason=reason,
            envelope_id=str(uuid.uuid4()),
        )
