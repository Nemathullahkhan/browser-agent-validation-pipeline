from __future__ import annotations

from datetime import datetime, timezone

from app.audit.store import AuditEvent
from app.models.base import TrustDecision
from app.trends.models import MetricTrend, TrendDirection, TrendPoint, TrendReport

# Minimum relative change (5%) to be called IMPROVING or DEGRADING.
_CHANGE_THRESHOLD = 0.05

_METRICS: dict[str, bool] = {
    "avg_confidence": True,   # higher is better
    "avg_latency_ms": False,  # lower is better
    "block_rate": False,      # lower is better
}


class TrendAnalyzer:
    def analyze(self, events: list[AuditEvent]) -> TrendReport:
        now = datetime.now(timezone.utc).isoformat()
        if not events:
            return TrendReport(analyzed_at=now, event_count=0)

        trends: dict[str, MetricTrend] = {}
        for metric, higher_is_better in _METRICS.items():
            points = self._extract_points(events, metric)
            if len(points) < 2:
                continue
            first = points[0].value
            last = points[-1].value
            change_pct = ((last - first) / first * 100.0) if first != 0.0 else (100.0 if last > 0 else 0.0)
            direction = self._direction(change_pct, higher_is_better)
            trends[metric] = MetricTrend(
                metric=metric,
                direction=direction,
                first_value=round(first, 2),
                last_value=round(last, 2),
                change_pct=round(change_pct, 1),
                data_points=points,
            )

        return TrendReport(analyzed_at=now, event_count=len(events), trends=trends)

    def supported_metrics(self) -> list[str]:
        return list(_METRICS.keys())

    # ── private ───────────────────────────────────────────────────────────────

    def _extract_points(self, events: list[AuditEvent], metric: str) -> list[TrendPoint]:
        points: list[TrendPoint] = []
        for e in events:
            value = self._metric_value(e, metric, events)
            if value is not None:
                points.append(TrendPoint(timestamp=e.timestamp, value=value))
        return points

    def _metric_value(
        self, event: AuditEvent, metric: str, all_events: list[AuditEvent]
    ) -> float | None:
        if metric == "avg_confidence":
            return event.confidence
        if metric == "avg_latency_ms":
            return event.latency_ms
        if metric == "block_rate":
            # Use a rolling 5-event window ending at this event
            idx = all_events.index(event)
            window = all_events[max(0, idx - 4) : idx + 1]
            if not window:
                return None
            return sum(1 for e in window if e.decision == TrustDecision.BLOCK) / len(window) * 100.0
        return None

    def _direction(self, change_pct: float, higher_is_better: bool) -> TrendDirection:
        threshold_pct = _CHANGE_THRESHOLD * 100.0
        if higher_is_better:
            if change_pct > threshold_pct:
                return TrendDirection.IMPROVING
            if change_pct < -threshold_pct:
                return TrendDirection.DEGRADING
        else:
            if change_pct < -threshold_pct:
                return TrendDirection.IMPROVING
            if change_pct > threshold_pct:
                return TrendDirection.DEGRADING
        return TrendDirection.STABLE
