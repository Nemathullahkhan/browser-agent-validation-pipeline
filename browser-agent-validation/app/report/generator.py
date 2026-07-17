from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.store import AuditEvent
from app.comparison.engine import ComparisonResult
from app.models.base import TrustDecision
from app.report.models import ReportConfig, ReportSummary, SessionReport
from app.review.models import ReviewItem


class ReportGenerator:
    """Aggregates data from all persistence stores into a SessionReport."""

    def __init__(self, config: ReportConfig | None = None) -> None:
        self._config = config or ReportConfig()

    @property
    def config(self) -> ReportConfig:
        return self._config

    def generate(
        self,
        audit_path: Path | str | None = None,
        metrics_path: Path | str | None = None,
        comparison_path: Path | str | None = None,
        review_path: Path | str | None = None,
    ) -> SessionReport:
        audit_events = self._load_audit(audit_path)
        metrics = self._load_metrics(metrics_path)
        comparison = self._load_comparison(comparison_path)
        review_items = self._load_review(review_path)
        summary = self._build_summary(audit_events)

        return SessionReport(
            title=self._config.title,
            generated_at=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            audit_events=audit_events[-self._config.max_audit_events :],
            metrics=metrics,
            comparison=comparison,
            review_items=review_items,
        )

    # ── loaders ───────────────────────────────────────────────────────────────

    def _load_audit(self, path: Path | str | None) -> list[AuditEvent]:
        if not self._config.include_audit or path is None:
            return []
        from app.audit.store import LocalAuditStore

        try:
            return LocalAuditStore(path).read_all()
        except Exception:
            return []

    def _load_metrics(self, path: Path | str | None) -> dict[str, Any]:
        if not self._config.include_metrics or path is None:
            return {}
        from app.metrics.engine import load_metrics

        try:
            return load_metrics(path)
        except Exception:
            return {}

    def _load_comparison(self, path: Path | str | None) -> ComparisonResult | None:
        if not self._config.include_comparison or path is None:
            return None
        from app.comparison.engine import load_comparison

        try:
            return load_comparison(path)
        except Exception:
            return None

    def _load_review(self, path: Path | str | None) -> list[ReviewItem]:
        if not self._config.include_review or path is None:
            return []
        from app.review.queue import ReviewQueue

        try:
            return ReviewQueue(path).read_all()
        except Exception:
            return []

    # ── summary builder ───────────────────────────────────────────────────────

    def _build_summary(self, events: list[AuditEvent]) -> ReportSummary:
        total = len(events)
        if total == 0:
            return ReportSummary()

        allowed = sum(1 for e in events if e.decision == TrustDecision.ALLOW)
        blocked = sum(1 for e in events if e.decision == TrustDecision.BLOCK)
        escalated = sum(1 for e in events if e.decision == TrustDecision.HUMAN_REVIEW)
        avg_conf = sum(e.confidence for e in events) / total
        avg_latency = sum(e.latency_ms for e in events) / total
        violation_count = sum(len(e.violations) for e in events)
        risk_counter: Counter[str] = Counter(e.risk.value for e in events)
        most_common_risk = risk_counter.most_common(1)[0][0] if risk_counter else "N/A"

        return ReportSummary(
            total_governed_runs=total,
            allowed=allowed,
            blocked=blocked,
            escalated=escalated,
            avg_confidence=round(avg_conf, 1),
            avg_latency_ms=round(avg_latency, 1),
            violation_count=violation_count,
            most_common_risk=most_common_risk,
        )
