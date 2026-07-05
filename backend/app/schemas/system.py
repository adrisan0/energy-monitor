from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmModel


class EventRead(OrmModel):
    id: int
    timestamp_utc: datetime
    event_type: str
    severity: str
    message: str
    metadata_json: dict[str, Any]


class AnalysisEvent(BaseModel):
    timestamp: datetime
    event_type: str
    severity: str
    label: str
    confidence: str
    value_w: float | None = None
    note: str


class SystemStatus(BaseModel):
    backend: str
    database: str
    meter_online: bool
    simulation_mode: bool
    latest_sample_at: datetime | None
    latest_data_quality: str | None
    feature_flags: dict[str, bool]
    backups_path: str


class BackupRead(OrmModel):
    id: int
    filename: str
    path: str
    size_bytes: int | None
    checksum_sha256: str | None
    status: str
    created_at: datetime
    finished_at: datetime | None
    error_message: str | None
