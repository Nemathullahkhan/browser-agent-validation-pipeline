from __future__ import annotations

from pathlib import Path

from app.audit.store import AuditEvent
from app.comparison.engine import ComparisonResult
from app.report.models import ReportSummary, SessionReport
from app.review.models import ReviewItem


class MarkdownRenderer:
    """Renders a SessionReport to a Markdown string."""

    def render(self, report: SessionReport) -> str:
        parts: list[str] = [
            f"# {report.title}",
            "",
            f"**Generated:** {report.generated_at[:19].replace('T', ' ')} UTC",
            "",
            "## Executive Summary",
            "",
            self._render_summary(report.summary),
        ]

        if report.audit_events:
            parts += ["", "## Audit Log", "", self._render_audit(report.audit_events)]

        if report.metrics:
            parts += ["", "## Governance Metrics", "", self._render_metrics(report.metrics)]

        if report.comparison is not None:
            parts += ["", "## Comparison Run", "", self._render_comparison(report.comparison)]

        if report.review_items:
            parts += ["", "## Human Review Queue", "", self._render_review(report.review_items)]

        parts.append("")
        return "\n".join(parts)

    def save(self, report: SessionReport, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.render(report), encoding="utf-8")
        return p

    # ── section renderers ─────────────────────────────────────────────────────

    def _render_summary(self, s: ReportSummary) -> str:
        total = s.total_governed_runs
        pct = lambda n: f"{n / total * 100:.0f}%" if total else "—"
        rows = [
            ("Total governed runs", str(total)),
            ("Allowed", f"{s.allowed} ({pct(s.allowed)})"),
            ("Blocked", f"{s.blocked} ({pct(s.blocked)})"),
            ("Escalated", f"{s.escalated} ({pct(s.escalated)})"),
            ("Avg confidence", f"{s.avg_confidence:.1f}/100"),
            ("Avg latency", f"{s.avg_latency_ms:,.0f} ms"),
            ("Total violations", str(s.violation_count)),
            ("Most common risk", s.most_common_risk),
        ]
        lines = ["| Metric | Value |", "|--------|-------|"]
        lines += [f"| {k} | {v} |" for k, v in rows]
        return "\n".join(lines)

    def _render_audit(self, events: list[AuditEvent]) -> str:
        lines = [
            "| Timestamp | Decision | Confidence | Risk | Violations |",
            "|-----------|----------|------------|------|------------|",
        ]
        for e in events:
            ts = e.timestamp[:19].replace("T", " ")
            viols = (
                "; ".join(e.violations[:2]) + ("…" if len(e.violations) > 2 else "")
                if e.violations
                else "—"
            )
            lines.append(
                f"| {ts} | {e.decision.value} | {e.confidence:.0f} | {e.risk.value} | {viols} |"
            )
        return "\n".join(lines)

    def _render_metrics(self, metrics: dict) -> str:
        rows = [
            (k, v)
            for k, v in sorted(metrics.items())
            if isinstance(v, dict) and "avg" in v
        ]
        if not rows:
            return "_No metrics data._"
        lines = ["| Metric | Avg | Last | Count |", "|--------|-----|------|-------|"]
        for k, v in rows[:20]:
            lines.append(
                f"| {k} | {v.get('avg', 0):.1f} | {v.get('last', 0):.1f} | {int(v.get('count', 0))} |"
            )
        return "\n".join(lines)

    def _render_comparison(self, cr: ComparisonResult) -> str:
        lines = [
            f"**Query:** {cr.query}",
            "",
            f"| | Without AgentTrust | With AgentTrust |",
            f"|--|--|--|",
            f"| Latency | {cr.raw_latency_ms:,.0f} ms | {cr.governed_latency_ms:,.0f} ms |",
            f"| Decision | — | {cr.governed_decision or '—'} |",
            f"| Overhead | — | {cr.governance_overhead_ms:,.0f} ms |",
        ]
        if cr.governed_error:
            lines.append(f"\n**Governance error:** {cr.governed_error}")
        return "\n".join(lines)

    def _render_review(self, items: list[ReviewItem]) -> str:
        lines = [
            "| ID | Timestamp | Status | Query | Note |",
            "|----|-----------|--------|-------|------|",
        ]
        for item in items:
            ts = item.timestamp[:19].replace("T", " ")
            q = item.query[:40] + ("…" if len(item.query) > 40 else "")
            lines.append(
                f"| {item.item_id[:8]}… | {ts} | {item.status.value} | {q} | {item.reviewer_note or '—'} |"
            )
        return "\n".join(lines)
