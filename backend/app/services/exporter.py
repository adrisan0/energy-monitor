from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MeterSample

CSV_FIELDS = [
    "id",
    "timestamp_utc",
    "timestamp_local",
    "solar_w",
    "grid_import_w",
    "grid_export_w",
    "house_consumption_w",
    "solar_self_consumption_w",
    "solar_self_consumption_percent",
    "voltage_v",
    "current_a",
    "frequency_hz",
    "power_factor",
    "pac1",
    "pac2",
    "fpot1",
    "fpot2",
    "pact",
    "data_quality",
    "error_message",
    "poll_duration_ms",
    "repeated_payload",
]


def iter_measurement_csv(
    db: Session,
    *,
    start: datetime | None,
    end: datetime | None,
    data_quality: str | None,
) -> Iterable[str]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
    writer.writeheader()
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    query = select(MeterSample)
    if start is not None:
        query = query.where(MeterSample.timestamp_utc >= start)
    if end is not None:
        query = query.where(MeterSample.timestamp_utc <= end)
    if data_quality is not None:
        query = query.where(MeterSample.data_quality == data_quality)

    for sample in db.scalars(query.order_by(MeterSample.timestamp_utc.asc()).limit(200000)):
        writer.writerow({field: _value(getattr(sample, field)) for field in CSV_FIELDS})
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def _value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
