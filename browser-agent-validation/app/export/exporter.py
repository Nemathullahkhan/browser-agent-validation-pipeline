from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.audit.store import AuditEvent
from app.dashboard.models import DashboardState
from app.export.models import ExportConfig, ExportFormat, ExportManifest
from app.review.models import ReviewItem


class DataExporter:
    def __init__(self, config: ExportConfig | None = None) -> None:
        self._config = config or ExportConfig()

    @property
    def config(self) -> ExportConfig:
        return self._config

    def export_all(
        self, state: DashboardState, output_dir: Path | str = "."
    ) -> ExportManifest:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        fmt = self._config.format
        files: dict[str, str] = {}
        total = 0

        if self._config.include_audit and state.recent_events:
            path = out / f"audit_export.{fmt.value}"
            n = (
                self.export_audit_json(state.recent_events, path)
                if fmt == ExportFormat.JSON
                else self.export_audit_csv(state.recent_events, path)
            )
            files["audit"] = str(path)
            total += n

        if self._config.include_review and state.pending_review_items:
            path = out / f"review_export.{fmt.value}"
            n = (
                self.export_review_json(state.pending_review_items, path)
                if fmt == ExportFormat.JSON
                else self.export_review_csv(state.pending_review_items, path)
            )
            files["review"] = str(path)
            total += n

        if self._config.include_summary:
            path = out / f"summary_export.{fmt.value}"
            self.export_summary(state, path)
            files["summary"] = str(path)

        if self._config.include_metrics and state.metrics:
            path = out / f"metrics_export.json"
            path.write_text(json.dumps(state.metrics, indent=2), encoding="utf-8")
            files["metrics"] = str(path)

        return ExportManifest(
            exported_at=datetime.now(timezone.utc).isoformat(),
            format=fmt,
            files=files,
            total_records=total,
        )

    # ── audit ─────────────────────────────────────────────────────────────────

    def export_audit_json(self, events: list[AuditEvent], path: Path) -> int:
        rows = [
            {
                "execution_id": e.execution_id,
                "timestamp": e.timestamp,
                "decision": e.decision.value,
                "confidence": e.confidence,
                "risk": e.risk.value,
                "latency_ms": e.latency_ms,
                "violations": e.violations,
            }
            for e in events
        ]
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return len(rows)

    def export_audit_csv(self, events: list[AuditEvent], path: Path) -> int:
        fieldnames = ["execution_id", "timestamp", "decision", "confidence", "risk", "latency_ms", "violations"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for e in events:
                writer.writerow({
                    "execution_id": e.execution_id,
                    "timestamp": e.timestamp,
                    "decision": e.decision.value,
                    "confidence": e.confidence,
                    "risk": e.risk.value,
                    "latency_ms": e.latency_ms,
                    "violations": "; ".join(e.violations),
                })
        return len(events)

    # ── review ────────────────────────────────────────────────────────────────

    def export_review_json(self, items: list[ReviewItem], path: Path) -> int:
        rows = [
            {
                "item_id": i.item_id,
                "timestamp": i.timestamp,
                "query": i.query,
                "status": i.status.value,
                "reviewer_note": i.reviewer_note,
                "reviewed_at": i.reviewed_at,
            }
            for i in items
        ]
        path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return len(rows)

    def export_review_csv(self, items: list[ReviewItem], path: Path) -> int:
        fieldnames = ["item_id", "timestamp", "query", "status", "reviewer_note", "reviewed_at"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i in items:
                writer.writerow({
                    "item_id": i.item_id,
                    "timestamp": i.timestamp,
                    "query": i.query,
                    "status": i.status.value,
                    "reviewer_note": i.reviewer_note or "",
                    "reviewed_at": i.reviewed_at or "",
                })
        return len(items)

    # ── summary ───────────────────────────────────────────────────────────────

    def export_summary(self, state: DashboardState, path: Path) -> None:
        if self._config.format == ExportFormat.CSV:
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["metric", "value"])
                for field, value in self._summary_rows(state):
                    writer.writerow([field, value])
        else:
            data = {field: value for field, value in self._summary_rows(state)}
            data["collected_at"] = state.collected_at
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _summary_rows(self, state: DashboardState) -> list[tuple[str, object]]:
        return [
            ("total_governed_runs", state.total_governed_runs),
            ("allowed", state.allowed),
            ("blocked", state.blocked),
            ("escalated", state.escalated),
            ("pending_review", state.pending_review),
            ("avg_confidence", state.avg_confidence),
            ("avg_latency_ms", state.avg_latency_ms),
            ("violation_count", state.violation_count),
            ("most_common_risk", state.most_common_risk),
            ("has_comparison", state.has_comparison),
        ]
