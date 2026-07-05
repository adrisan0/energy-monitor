from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import OrmModel


class LatestResponse(BaseModel):
    timestamp: datetime
    solar_w: float | None
    grid_import_w: float | None
    grid_export_w: float | None
    house_consumption_w: float | None
    solar_self_consumption_w: float | None
    solar_self_consumption_percent: float | None
    data_quality: str
    meter_online: bool
    seconds_since_last_reading: float


class MeasurementRead(OrmModel):
    id: int
    timestamp_utc: datetime
    timestamp_local: datetime
    local_date: date
    solar_w: float | None
    grid_import_w: float | None
    grid_export_w: float | None
    house_consumption_w: float | None
    solar_self_consumption_w: float | None
    solar_self_consumption_percent: float | None
    voltage_v: float | None
    current_a: float | None
    frequency_hz: float | None
    power_factor: float | None
    pac1: float | None
    pac2: float | None
    fpot1: float | None
    fpot2: float | None
    pact: float | None
    repeated_payload: bool
    data_quality: str
    error_message: str | None
    poll_duration_ms: int | None


class RawPayloadRead(BaseModel):
    id: int
    timestamp_utc: datetime
    timestamp_local: datetime
    raw_payload_redacted: str
    raw_variables: dict[str, Any]
    payload_hash: str
    repeated_payload: bool
    data_quality: str
    error_message: str | None
    poll_duration_ms: int | None
