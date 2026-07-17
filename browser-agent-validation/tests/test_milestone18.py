from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.audit.store import LocalAuditStore, make_audit_event
from app.dashboard.collector import DashboardCollector
from app.dashboard.models import DashboardState
from app.export.exporter import DataExporter
from app.export.models import ExportConfig, ExportFormat, ExportManifest
from app.models.base import RiskLevel, TrustDecision, ValidationResult
from app.review.models import ReviewItem, ReviewStatus


# ── helpers ───────────────────────────────────────────────────────────────────


def _vr(decision=TrustDecision.ALLOW, risk=RiskLevel.LOW, confidence=85.0, score=90.0):
    return ValidationResult(
        decision=decision, confidence=confidence,
        risk_level=risk, policy_score=score, violations=[],
    )


def _state_with_events(tmp_path, n_audit=3, n_review=2) -> DashboardState:
    audit_p = tmp_path / "audit.jsonl"
    store = LocalAuditStore(audit_p)
    for i in range(n_audit):
        vr = _vr(decision=TrustDecision.ALLOW if i % 2 == 0 else TrustDecision.BLOCK,
                 risk=RiskLevel.LOW if i % 2 == 0 else RiskLevel.HIGH,
                 confidence=80.0 - i * 5, score=85.0 - i * 5)
        store.append(make_audit_event(f"exec-{i}", vr, 100.0 * (i + 1)))

    review_p = tmp_path / "rq.jsonl"
    from app.review.queue import ReviewQueue
    q = ReviewQueue(review_p)
    for i in range(n_review):
        q.enqueue(f"query {i}", _vr(decision=TrustDecision.HUMAN_REVIEW))

    return DashboardCollector().collect(audit_path=audit_p, review_path=review_p)


def _empty_state() -> DashboardState:
    return DashboardState(collected_at=datetime.now(timezone.utc).isoformat())


def _review_item(query="test") -> ReviewItem:
    return ReviewItem(
        item_id="aabb1122-0000-0000-0000-aabbccddeeff",
        timestamp=datetime.now(timezone.utc).isoformat(),
        query=query,
        validation=_vr(decision=TrustDecision.HUMAN_REVIEW),
        status=ReviewStatus.PENDING,
    )


# ── ExportFormat ──────────────────────────────────────────────────────────────


class TestExportFormat:
    def test_json_value(self):
        assert ExportFormat.JSON == "json"

    def test_csv_value(self):
        assert ExportFormat.CSV == "csv"

    def test_is_str_enum(self):
        assert isinstance(ExportFormat.JSON, str)


# ── ExportConfig ──────────────────────────────────────────────────────────────


class TestExportConfig:
    def test_default_format_json(self):
        assert ExportConfig().format == ExportFormat.JSON

    def test_default_include_audit(self):
        assert ExportConfig().include_audit is True

    def test_default_include_review(self):
        assert ExportConfig().include_review is True

    def test_default_include_summary(self):
        assert ExportConfig().include_summary is True

    def test_default_include_metrics(self):
        assert ExportConfig().include_metrics is True

    def test_custom_format_csv(self):
        assert ExportConfig(format=ExportFormat.CSV).format == ExportFormat.CSV

    def test_disable_audit(self):
        assert ExportConfig(include_audit=False).include_audit is False

    def test_serializes_to_dict(self):
        d = ExportConfig().model_dump()
        assert "format" in d and "include_audit" in d


# ── ExportManifest ────────────────────────────────────────────────────────────


class TestExportManifest:
    def test_construction(self):
        m = ExportManifest(exported_at="2026-07-17T00:00:00Z", format=ExportFormat.JSON)
        assert m.format == ExportFormat.JSON

    def test_default_empty_files(self):
        m = ExportManifest(exported_at="ts", format=ExportFormat.JSON)
        assert m.files == {}

    def test_default_total_records_zero(self):
        m = ExportManifest(exported_at="ts", format=ExportFormat.JSON)
        assert m.total_records == 0

    def test_custom_files(self):
        m = ExportManifest(exported_at="ts", format=ExportFormat.CSV,
                           files={"audit": "/tmp/a.csv"}, total_records=5)
        assert m.files["audit"] == "/tmp/a.csv"
        assert m.total_records == 5

    def test_serializes(self):
        m = ExportManifest(exported_at="ts", format=ExportFormat.JSON)
        d = m.model_dump()
        assert "exported_at" in d and "format" in d


# ── DataExporter — JSON audit ─────────────────────────────────────────────────


class TestDataExporterAuditJson:
    def _events(self, tmp_path, n=2):
        p = tmp_path / "a.jsonl"
        store = LocalAuditStore(p)
        for i in range(n):
            store.append(make_audit_event(f"e{i}", _vr(), 100.0))
        return store.read_all()

    def test_export_returns_count(self, tmp_path):
        events = self._events(tmp_path)
        out = tmp_path / "export.json"
        n = DataExporter().export_audit_json(events, out)
        assert n == 2

    def test_export_creates_file(self, tmp_path):
        events = self._events(tmp_path)
        out = tmp_path / "export.json"
        DataExporter().export_audit_json(events, out)
        assert out.exists()

    def test_export_valid_json(self, tmp_path):
        events = self._events(tmp_path)
        out = tmp_path / "export.json"
        DataExporter().export_audit_json(events, out)
        data = json.loads(out.read_text())
        assert isinstance(data, list)

    def test_export_contains_required_fields(self, tmp_path):
        events = self._events(tmp_path, 1)
        out = tmp_path / "export.json"
        DataExporter().export_audit_json(events, out)
        row = json.loads(out.read_text())[0]
        assert "execution_id" in row
        assert "decision" in row
        assert "confidence" in row
        assert "risk" in row

    def test_export_correct_count_in_file(self, tmp_path):
        events = self._events(tmp_path, 4)
        out = tmp_path / "export.json"
        DataExporter().export_audit_json(events, out)
        assert len(json.loads(out.read_text())) == 4

    def test_empty_events_creates_empty_array(self, tmp_path):
        out = tmp_path / "export.json"
        DataExporter().export_audit_json([], out)
        assert json.loads(out.read_text()) == []


# ── DataExporter — CSV audit ──────────────────────────────────────────────────


class TestDataExporterAuditCsv:
    def _events(self, tmp_path, n=2):
        p = tmp_path / "a.jsonl"
        store = LocalAuditStore(p)
        for i in range(n):
            store.append(make_audit_event(f"e{i}", _vr(), 100.0))
        return store.read_all()

    def test_export_returns_count(self, tmp_path):
        events = self._events(tmp_path, 3)
        out = tmp_path / "audit.csv"
        assert DataExporter().export_audit_csv(events, out) == 3

    def test_export_creates_file(self, tmp_path):
        events = self._events(tmp_path)
        out = tmp_path / "audit.csv"
        DataExporter().export_audit_csv(events, out)
        assert out.exists()

    def test_export_has_header(self, tmp_path):
        events = self._events(tmp_path, 1)
        out = tmp_path / "audit.csv"
        DataExporter().export_audit_csv(events, out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert "decision" in rows[0]

    def test_export_row_count_matches(self, tmp_path):
        events = self._events(tmp_path, 3)
        out = tmp_path / "audit.csv"
        DataExporter().export_audit_csv(events, out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert len(rows) == 3

    def test_export_decision_value(self, tmp_path):
        events = self._events(tmp_path, 1)
        out = tmp_path / "audit.csv"
        DataExporter().export_audit_csv(events, out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert rows[0]["decision"] in ("ALLOW", "BLOCK", "HUMAN_REVIEW")


# ── DataExporter — JSON review ────────────────────────────────────────────────


class TestDataExporterReviewJson:
    def test_export_returns_count(self, tmp_path):
        items = [_review_item("q1"), _review_item("q2")]
        out = tmp_path / "review.json"
        assert DataExporter().export_review_json(items, out) == 2

    def test_export_creates_file(self, tmp_path):
        out = tmp_path / "review.json"
        DataExporter().export_review_json([_review_item()], out)
        assert out.exists()

    def test_export_valid_json(self, tmp_path):
        out = tmp_path / "review.json"
        DataExporter().export_review_json([_review_item("test")], out)
        data = json.loads(out.read_text())
        assert isinstance(data, list)
        assert data[0]["query"] == "test"

    def test_export_contains_status(self, tmp_path):
        out = tmp_path / "review.json"
        DataExporter().export_review_json([_review_item()], out)
        data = json.loads(out.read_text())
        assert "status" in data[0]


# ── DataExporter — CSV review ─────────────────────────────────────────────────


class TestDataExporterReviewCsv:
    def test_export_returns_count(self, tmp_path):
        items = [_review_item("a"), _review_item("b")]
        out = tmp_path / "review.csv"
        assert DataExporter().export_review_csv(items, out) == 2

    def test_export_has_header(self, tmp_path):
        out = tmp_path / "review.csv"
        DataExporter().export_review_csv([_review_item()], out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert "query" in rows[0]

    def test_export_query_in_row(self, tmp_path):
        out = tmp_path / "review.csv"
        DataExporter().export_review_csv([_review_item("my query")], out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert rows[0]["query"] == "my query"


# ── DataExporter — summary ────────────────────────────────────────────────────


class TestDataExporterSummary:
    def test_export_summary_json_creates_file(self, tmp_path):
        out = tmp_path / "summary.json"
        DataExporter().export_summary(_empty_state(), out)
        assert out.exists()

    def test_export_summary_json_valid(self, tmp_path):
        out = tmp_path / "summary.json"
        DataExporter().export_summary(_empty_state(), out)
        data = json.loads(out.read_text())
        assert "total_governed_runs" in data

    def test_export_summary_csv_creates_file(self, tmp_path):
        cfg = ExportConfig(format=ExportFormat.CSV)
        out = tmp_path / "summary.csv"
        DataExporter(cfg).export_summary(_empty_state(), out)
        assert out.exists()

    def test_export_summary_csv_has_rows(self, tmp_path):
        cfg = ExportConfig(format=ExportFormat.CSV)
        out = tmp_path / "summary.csv"
        DataExporter(cfg).export_summary(_empty_state(), out)
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert len(rows) > 0


# ── DataExporter — export_all ─────────────────────────────────────────────────


class TestDataExporterExportAll:
    def test_export_all_returns_manifest(self, tmp_path):
        state = _state_with_events(tmp_path)
        manifest = DataExporter().export_all(state, tmp_path / "out")
        assert isinstance(manifest, ExportManifest)

    def test_export_all_creates_output_dir(self, tmp_path):
        state = _state_with_events(tmp_path)
        out_dir = tmp_path / "exports" / "session1"
        DataExporter().export_all(state, out_dir)
        assert out_dir.exists()

    def test_export_all_json_includes_audit(self, tmp_path):
        state = _state_with_events(tmp_path)
        manifest = DataExporter().export_all(state, tmp_path / "out")
        assert "audit" in manifest.files
        assert Path(manifest.files["audit"]).exists()

    def test_export_all_json_includes_review(self, tmp_path):
        state = _state_with_events(tmp_path)
        manifest = DataExporter().export_all(state, tmp_path / "out")
        assert "review" in manifest.files

    def test_export_all_includes_summary(self, tmp_path):
        state = _state_with_events(tmp_path)
        manifest = DataExporter().export_all(state, tmp_path / "out")
        assert "summary" in manifest.files

    def test_export_all_total_records(self, tmp_path):
        state = _state_with_events(tmp_path, n_audit=3, n_review=2)
        manifest = DataExporter().export_all(state, tmp_path / "out")
        assert manifest.total_records >= 3

    def test_export_all_csv_format(self, tmp_path):
        state = _state_with_events(tmp_path)
        cfg = ExportConfig(format=ExportFormat.CSV)
        manifest = DataExporter(cfg).export_all(state, tmp_path / "out")
        assert manifest.format == ExportFormat.CSV
        assert manifest.files.get("audit", "").endswith(".csv")

    def test_export_all_skip_audit_when_disabled(self, tmp_path):
        state = _state_with_events(tmp_path)
        cfg = ExportConfig(include_audit=False)
        manifest = DataExporter(cfg).export_all(state, tmp_path / "out")
        assert "audit" not in manifest.files

    def test_export_all_skip_review_when_disabled(self, tmp_path):
        state = _state_with_events(tmp_path)
        cfg = ExportConfig(include_review=False)
        manifest = DataExporter(cfg).export_all(state, tmp_path / "out")
        assert "review" not in manifest.files

    def test_export_all_manifest_timestamp_recent(self, tmp_path):
        before = datetime.now(timezone.utc)
        manifest = DataExporter().export_all(_empty_state(), tmp_path / "out")
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(manifest.exported_at)
        assert before <= ts <= after

    def test_config_property(self):
        cfg = ExportConfig(format=ExportFormat.CSV)
        e = DataExporter(cfg)
        assert e.config is cfg
