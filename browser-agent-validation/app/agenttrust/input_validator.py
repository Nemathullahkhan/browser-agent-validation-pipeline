from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.models.base import RiskLevel, TrustDecision, ValidationResult

# ── Limits ────────────────────────────────────────────────────────────────────
_MAX_LEN = 2_000
_WARN_LEN = 1_000
_MIN_ALPHA_RATIO = 0.30   # below this for queries >20 chars → suspicious

# ── Injection patterns — (regex, severity, human message) ────────────────────
_INJECTION_CHECKS: list[tuple[str, str, str]] = [
    (r"ignore\s+(?:\w+\s+){0,3}instructions?", "HIGH",
     "Prompt injection: ignore-instructions directive"),
    (r"system\s*:", "HIGH",
     "Prompt injection: system-role override"),
    (r"\bjailbreak\b", "HIGH",
     "Prompt injection: jailbreak keyword"),
    (r"act\s+as\s+(?:if\s+)?you\s+(are|were)", "HIGH",
     "Prompt injection: persona override"),
    (r"<\s*/?system\s*>", "HIGH",
     "Prompt injection: <system> tag"),
    (r"disregard\s+(all|previous|prior)", "HIGH",
     "Prompt injection: disregard directive"),
    (r"forget\s+everything", "HIGH",
     "Prompt injection: forget-everything directive"),
    (r"you\s+are\s+now\s+(?:a|an|the)?\s+\w", "HIGH",
     "Prompt injection: identity override"),
    (r"pretend\s+(you\s+are|you're|to\s+be)", "MEDIUM",
     "Prompt injection: pretend directive"),
    (r"do\s+not\s+follow", "MEDIUM",
     "Prompt injection: instruction-override directive"),
]

# ── HTML / code-execution patterns ────────────────────────────────────────────
_HTML_RE = re.compile(r"<\s*script|<\s*img\s+[^>]*onerror|javascript:", re.IGNORECASE)
_CODE_RE = re.compile(r"`[^`]+`|\$\([^)]+\)|__import__|eval\s*\(|exec\s*\(", re.IGNORECASE)


@dataclass
class _Check:
    name: str
    passed: bool
    severity: str = ""
    message: str = ""


@dataclass
class _Violation:
    severity: str
    message: str


class InputValidator:
    """Pre-run input validator — blocks bad queries before the agent is invoked.

    Checks performed (in order):
      1. Empty / blank
      2. Length (warn at 1 000, block at 2 000)
      3. Prompt-injection patterns
      4. HTML / script injection
      5. Code-execution patterns
      6. Alphabetic-ratio (encoding attacks / gibberish)
    """

    def validate(self, query: str) -> ValidationResult:
        violations: list[_Violation] = []
        checks: list[_Check] = []

        # 1. Empty
        if not query or not query.strip():
            violations.append(_Violation("CRITICAL", "Query is empty or blank"))
            checks.append(_Check("empty_check", False, "CRITICAL", "Query is empty or blank"))
            return self._build(checks, violations)

        checks.append(_Check("empty_check", True))

        # 2. Length
        qlen = len(query)
        if qlen > _MAX_LEN:
            msg = f"Query is too long ({qlen:,} chars; max {_MAX_LEN:,})"
            violations.append(_Violation("HIGH", msg))
            checks.append(_Check("length_check", False, "HIGH", msg))
        elif qlen > _WARN_LEN:
            msg = f"Query is long ({qlen:,} chars; recommended max {_WARN_LEN:,})"
            violations.append(_Violation("LOW", msg))
            checks.append(_Check("length_check", False, "LOW", msg))
        else:
            checks.append(_Check("length_check", True))

        # 3. Prompt injection
        injection_found = False
        for pattern, severity, msg in _INJECTION_CHECKS:
            if re.search(pattern, query, re.IGNORECASE):
                violations.append(_Violation(severity, msg))
                checks.append(_Check("injection_check", False, severity, msg))
                injection_found = True
                break
        if not injection_found:
            checks.append(_Check("injection_check", True))

        # 4. HTML / script injection
        if _HTML_RE.search(query):
            msg = "HTML or script-injection payload detected"
            violations.append(_Violation("HIGH", msg))
            checks.append(_Check("html_injection_check", False, "HIGH", msg))
        else:
            checks.append(_Check("html_injection_check", True))

        # 5. Code-execution patterns
        if _CODE_RE.search(query):
            msg = "Code-execution pattern detected"
            violations.append(_Violation("MEDIUM", msg))
            checks.append(_Check("code_injection_check", False, "MEDIUM", msg))
        else:
            checks.append(_Check("code_injection_check", True))

        # 6. Alphabetic-ratio
        if qlen > 20:
            alpha = sum(1 for c in query if c.isalpha())
            ratio = alpha / qlen
            if ratio < _MIN_ALPHA_RATIO:
                msg = f"Low alphabetic ratio ({ratio:.0%}) — possible encoding attack or gibberish"
                violations.append(_Violation("MEDIUM", msg))
                checks.append(_Check("content_check", False, "MEDIUM", msg))
            else:
                checks.append(_Check("content_check", True))
        else:
            checks.append(_Check("content_check", True))

        return self._build(checks, violations)

    # ── Private ───────────────────────────────────────────────────────────────

    def _build(
        self, checks: list[_Check], violations: list[_Violation]
    ) -> ValidationResult:
        policy_score = _score(violations)
        confidence = _confidence(violations)
        risk = _risk(violations, policy_score, confidence)
        decision, reason = _decide(policy_score, confidence, risk)

        return ValidationResult(
            decision=decision,
            confidence=confidence,
            risk_level=risk,
            policy_score=policy_score,
            violations=[v.message for v in violations],
            reason=reason,
            envelope_id=str(uuid.uuid4()),
            metadata={
                "stage": "input",
                "checks_run": len(checks),
                "checks_passed": sum(1 for c in checks if c.passed),
                "check_names": [c.name for c in checks],
            },
        )


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _score(violations: list[_Violation]) -> float:
    score = 100.0
    for v in violations:
        if v.severity == "CRITICAL":
            return 0.0
        elif v.severity == "HIGH":
            score -= 25.0
        elif v.severity == "MEDIUM":
            score -= 10.0
        elif v.severity == "LOW":
            score -= 5.0
    return max(score, 0.0)


def _confidence(violations: list[_Violation]) -> float:
    # Input validation is stricter than output validation: a single HIGH violation
    # drops confidence below the 50-point block threshold.
    conf = 95.0
    for v in violations:
        if v.severity == "CRITICAL":
            return 0.0
        elif v.severity == "HIGH":
            conf -= 50.0
        elif v.severity == "MEDIUM":
            conf -= 15.0
        elif v.severity == "LOW":
            conf -= 5.0
    return max(0.0, min(100.0, conf))


def _risk(violations: list[_Violation], policy_score: float, confidence: float) -> RiskLevel:
    sevs = {v.severity for v in violations}
    if "CRITICAL" in sevs:
        return RiskLevel.CRITICAL
    if "HIGH" in sevs or policy_score < 60 or confidence < 50:
        return RiskLevel.HIGH
    if "MEDIUM" in sevs:
        return RiskLevel.MEDIUM
    if "LOW" in sevs:
        return RiskLevel.LOW
    return RiskLevel.LOW


def _decide(
    policy_score: float, confidence: float, risk: RiskLevel
) -> tuple[TrustDecision, str]:
    if policy_score == 0.0:
        return TrustDecision.BLOCK, "Critical input violation — blocked immediately"
    if risk == RiskLevel.CRITICAL:
        return TrustDecision.HUMAN_REVIEW, "Critical risk — escalated for human review"
    if confidence < 50 or policy_score < 60:
        return (
            TrustDecision.BLOCK,
            f"Input validation failed — score: {policy_score:.0f}/100, confidence: {confidence:.0f}/100",
        )
    return TrustDecision.ALLOW, "Input validation passed"
