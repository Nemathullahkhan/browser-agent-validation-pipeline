from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class ExportConfig(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    include_audit: bool = True
    include_review: bool = True
    include_summary: bool = True
    include_metrics: bool = True


class ExportManifest(BaseModel):
    exported_at: str
    format: ExportFormat
    files: dict[str, str] = Field(default_factory=dict)
    total_records: int = 0
