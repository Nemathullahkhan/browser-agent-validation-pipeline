from __future__ import annotations

from app.audit.store import AuditEvent
from app.dashboard.models import DashboardConfig, DashboardState
from app.review.models import ReviewItem


class DashboardRenderer:
    """Renders a DashboardState to a plain-text summary string."""

    def render(self, state: DashboardState, config: DashboardConfig | None = None) -> str:
        cfg = config or DashboardConfig()
        parts = [
            f"# {cfg.title}",
            "",
            f"Collected: {state.collected_at[:19].replace('T', ' ')} UTC",
            "",
            "## KPIs",
            "",
            self._render_kpis(state),
        ]

        if state.recent_events:
            parts += ["", "## Recent Audit Events", "", self._render_events(state.recent_events)]

        if state.pending_review_items:
            parts += ["", "## Pending Review", "", self._render_review(state.pending_review_items)]

        if state.metrics:
            parts += ["", "## Metrics Summary", "", self._render_metrics(state.metrics)]

        if state.has_comparison:
            parts += ["", "## Comparison", "", "_Comparison data available._"]

        parts.append("")
        return "\n".join(parts)

    # ── section renderers ─────────────────────────────────────────────────────

    def _render_kpis(self, state: DashboardState) -> str:
        total = state.total_governed_runs
        pct = lambda n: f"{n / total * 100:.0f}%" if total else "—"
        rows = [
            ("Total governed runs", str(total)),
            ("Allowed", f"{state.allowed} ({pct(state.allowed)})"),
            ("Blocked", f"{state.blocked} ({pct(state.blocked)})"),
            ("Escalated", f"{state.escalated} ({pct(state.escalated)})"),
            ("Pending review", str(state.pending_review)),
            ("Avg confidence", f"{state.avg_confidence:.1f}/100"),
            ("Avg latency", f"{state.avg_latency_ms:,.0f} ms"),
            ("Total violations", str(state.violation_count)),
            ("Most common risk", state.most_common_risk),
            ("Comparison available", "Yes" if state.has_comparison else "No"),
        ]
        lines = ["| KPI | Value |", "|-----|-------|"]
        lines += [f"| {k} | {v} |" for k, v in rows]
        return "\n".join(lines)

    def _render_events(self, events: list[AuditEvent]) -> str:
        lines = [
            "| Timestamp | Decision | Confidence | Risk |",
            "|-----------|----------|------------|------|",
        ]
        for e in events:
            ts = e.timestamp[:19].replace("T", " ")
            lines.append(f"| {ts} | {e.decision.value} | {e.confidence:.0f} | {e.risk.value} |")
        return "\n".join(lines)

    def _render_review(self, items: list[ReviewItem]) -> str:
        lines = ["| ID | Query | Status |", "|----|-------|--------|"]
        for item in items:
            q = item.query[:40] + ("…" if len(item.query) > 40 else "")
            lines.append(f"| {item.item_id[:8]}… | {q} | {item.status.value} |")
        return "\n".join(lines)

    def _render_metrics(self, metrics: dict) -> str:
        rows = [
            (k, v)
            for k, v in sorted(metrics.items())
            if isinstance(v, dict) and "avg" in v
        ]
        if not rows:
            return "_No metric averages available._"
        lines = ["| Metric | Avg | Count |", "|--------|-----|-------|"]
        for k, v in rows[:10]:
            lines.append(f"| {k} | {v.get('avg', 0):.1f} | {int(v.get('count', 0))} |")
        return "\n".join(lines)
