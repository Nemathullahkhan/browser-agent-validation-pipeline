from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.audit.store import AuditEvent
from app.dashboard.models import DashboardConfig, DashboardState
from app.models.base import TrustDecision
from app.review.models import ReviewItem, ReviewStatus


class DashboardCollector:
    def __init__(self, config: DashboardConfig | None = None) -> None:
        self._config = config or DashboardConfig()

    @property
    def config(self) -> DashboardConfig:
        return self._config

    def collect(
        self,
        audit_path: Path | str | None = None,
        metrics_path: Path | str | None = None,
        review_path: Path | str | None = None,
        comparison_path: Path | str | None = None,
    ) -> DashboardState:
        audit_events = self._load_audit(audit_path)
        metrics = self._load_metrics(metrics_path)
        review_items = self._load_review(review_path)
        has_comparison = self._check_comparison(comparison_path)

        kpis = self._compute_kpis(audit_events)
        pending_items = [i for i in review_items if i.status == ReviewStatus.PENDING]

        return DashboardState(
            collected_at=datetime.now(timezone.utc).isoformat(),
            **kpis,
            pending_review=len(pending_items),
            recent_events=audit_events[-self._config.max_recent_events :],
            pending_review_items=pending_items[: self._config.max_review_items],
            metrics=metrics,
            has_comparison=has_comparison,
        )

    # ── private loaders ───────────────────────────────────────────────────────

    def _load_audit(self, path: Path | str | None) -> list[AuditEvent]:
        if path is None:
            return []
        from app.audit.store import LocalAuditStore

        try:
            return LocalAuditStore(path).read_all()
        except Exception:
            return []

    def _load_metrics(self, path: Path | str | None) -> dict:
        if path is None:
            return {}
        from app.metrics.engine import load_metrics

        try:
            return load_metrics(path)
        except Exception:
            return {}

    def _load_review(self, path: Path | str | None) -> list[ReviewItem]:
        if path is None:
            return []
        from app.review.queue import ReviewQueue

        try:
            return ReviewQueue(path).read_all()
        except Exception:
            return []

    def _check_comparison(self, path: Path | str | None) -> bool:
        if path is None:
            return False
        try:
            return Path(path).exists()
        except Exception:
            return False

    def _compute_kpis(self, events: list[AuditEvent]) -> dict:
        total = len(events)
        if total == 0:
            return {
                "total_governed_runs": 0,
                "allowed": 0,
                "blocked": 0,
                "escalated": 0,
                "avg_confidence": 0.0,
                "avg_latency_ms": 0.0,
                "violation_count": 0,
                "most_common_risk": "N/A",
            }

        allowed = sum(1 for e in events if e.decision == TrustDecision.ALLOW)
        blocked = sum(1 for e in events if e.decision == TrustDecision.BLOCK)
        escalated = sum(1 for e in events if e.decision == TrustDecision.HUMAN_REVIEW)
        avg_conf = round(sum(e.confidence for e in events) / total, 1)
        avg_latency = round(sum(e.latency_ms for e in events) / total, 1)
        violation_count = sum(len(e.violations) for e in events)
        risk_counter: Counter[str] = Counter(e.risk.value for e in events)
        most_common_risk = risk_counter.most_common(1)[0][0] if risk_counter else "N/A"

        return {
            "total_governed_runs": total,
            "allowed": allowed,
            "blocked": blocked,
            "escalated": escalated,
            "avg_confidence": avg_conf,
            "avg_latency_ms": avg_latency,
            "violation_count": violation_count,
            "most_common_risk": most_common_risk,
        }
