from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.health.models import ComponentCheck, HealthReport, HealthStatus


class HealthChecker:
    def check(
        self,
        audit_path: Path | str | None = None,
        metrics_path: Path | str | None = None,
        review_path: Path | str | None = None,
        policy_path: Path | str | None = None,
    ) -> HealthReport:
        components = [
            self._check_audit(audit_path),
            self._check_metrics(metrics_path),
            self._check_review(review_path),
            self._check_policy(policy_path),
            self._check_alert_engine(),
        ]

        statuses = {c.status for c in components}
        if HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        elif all(c.status == HealthStatus.HEALTHY for c in components):
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN

        return HealthReport(
            checked_at=datetime.now(timezone.utc).isoformat(),
            overall=overall,
            components=components,
        )

    # ── component checks ──────────────────────────────────────────────────────

    def _check_audit(self, path: Path | str | None) -> ComponentCheck:
        name = "Audit Store"
        if path is None:
            return ComponentCheck(name=name, status=HealthStatus.UNKNOWN,
                                  message="No audit path configured.")
        p = Path(path)
        if not p.exists():
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message=f"File not found: {p}")
        try:
            from app.audit.store import LocalAuditStore
            events = LocalAuditStore(p).read_all()
            return ComponentCheck(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"Readable. {len(events)} event(s) on record.",
            )
        except Exception as exc:
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message="Read failed.", detail=str(exc))

    def _check_metrics(self, path: Path | str | None) -> ComponentCheck:
        name = "Metrics Store"
        if path is None:
            return ComponentCheck(name=name, status=HealthStatus.UNKNOWN,
                                  message="No metrics path configured.")
        p = Path(path)
        if not p.exists():
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message=f"File not found: {p}")
        try:
            from app.metrics.engine import load_metrics
            data = load_metrics(p)
            return ComponentCheck(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"Readable. {len(data)} metric key(s).",
            )
        except Exception as exc:
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message="Read failed.", detail=str(exc))

    def _check_review(self, path: Path | str | None) -> ComponentCheck:
        name = "Review Queue"
        if path is None:
            return ComponentCheck(name=name, status=HealthStatus.UNKNOWN,
                                  message="No review queue path configured.")
        p = Path(path)
        if not p.exists():
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message=f"File not found: {p}")
        try:
            from app.review.queue import ReviewQueue
            from app.review.models import ReviewStatus
            items = ReviewQueue(p).read_all()
            pending = sum(1 for i in items if i.status == ReviewStatus.PENDING)
            return ComponentCheck(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"Readable. {len(items)} item(s), {pending} pending.",
            )
        except Exception as exc:
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message="Read failed.", detail=str(exc))

    def _check_policy(self, path: Path | str | None) -> ComponentCheck:
        name = "Policy Config"
        try:
            from app.policies.loader import load_policy
            cfg = load_policy(path)
            return ComponentCheck(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"Loaded '{cfg.name}' v{cfg.version}.",
            )
        except Exception as exc:
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message="Policy load failed.", detail=str(exc))

    def _check_alert_engine(self) -> ComponentCheck:
        name = "Alert Engine"
        try:
            from app.alerts.defaults import default_rules
            from app.alerts.engine import AlertEngine
            rules = default_rules()
            engine = AlertEngine(rules)
            return ComponentCheck(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"{len(engine.rules)} rule(s) loaded.",
            )
        except Exception as exc:
            return ComponentCheck(name=name, status=HealthStatus.DEGRADED,
                                  message="Alert engine init failed.", detail=str(exc))
