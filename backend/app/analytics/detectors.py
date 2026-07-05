from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MeterSample
from app.schemas.system import AnalysisEvent


def detect_analysis_events(db: Session, start: datetime | None, end: datetime | None) -> list[AnalysisEvent]:
    query = select(MeterSample).where(MeterSample.data_quality.in_(["valid", "partial"]))
    if start is not None:
        query = query.where(MeterSample.timestamp_utc >= start)
    if end is not None:
        query = query.where(MeterSample.timestamp_utc <= end)
    samples = list(db.scalars(query.order_by(MeterSample.timestamp_utc.asc()).limit(2000)))
    events: list[AnalysisEvent] = []
    events.extend(_sudden_changes(samples))
    events.extend(_night_base(samples))
    events.extend(_surplus_windows(samples))
    return events[:200]


def _sudden_changes(samples: list[MeterSample]) -> list[AnalysisEvent]:
    events: list[AnalysisEvent] = []
    previous: MeterSample | None = None
    for sample in samples:
        if previous is None or sample.house_consumption_w is None or previous.house_consumption_w is None:
            previous = sample
            continue
        delta = sample.house_consumption_w - previous.house_consumption_w
        if abs(delta) >= Decimal("900"):
            events.append(
                AnalysisEvent(
                    timestamp=sample.timestamp_utc,
                    event_type="sudden_power_change",
                    severity="info",
                    label="Cambio brusco de potencia",
                    confidence="media",
                    value_w=float(delta),
                    note="Hipotesis basada en la pinza global; requiere confirmacion manual o enchufe inteligente.",
                )
            )
        previous = sample
    return events


def _night_base(samples: list[MeterSample]) -> list[AnalysisEvent]:
    night = [
        sample.house_consumption_w
        for sample in samples
        if sample.house_consumption_w is not None and 2 <= sample.timestamp_local.hour < 6
    ]
    if len(night) < 5:
        return []
    average = sum(night, Decimal("0")) / Decimal(len(night))
    if average < Decimal("650"):
        severity = "info"
        label = "Consumo base nocturno normal"
    else:
        severity = "warning"
        label = "Consumo base nocturno alto"
    latest_night = next(
        sample.timestamp_utc for sample in reversed(samples) if sample.house_consumption_w in night
    )
    return [
        AnalysisEvent(
            timestamp=latest_night,
            event_type="night_base_load",
            severity=severity,
            label=label,
            confidence="media",
            value_w=float(average),
            note="Estimacion estadistica de 02:00 a 06:00; no identifica aparatos concretos.",
        )
    ]


def _surplus_windows(samples: list[MeterSample]) -> list[AnalysisEvent]:
    high_surplus = [
        sample
        for sample in samples
        if sample.grid_export_w is not None and sample.grid_export_w >= Decimal("1200")
    ]
    if len(high_surplus) < 3:
        return []
    sample = high_surplus[len(high_surplus) // 2]
    return [
        AnalysisEvent(
            timestamp=sample.timestamp_utc,
            event_type="solar_surplus_opportunity",
            severity="info",
            label="Oportunidad de excedente solar",
            confidence="media",
            value_w=float(sample.grid_export_w or 0),
            note="Hipotesis: puede ser una buena franja para cargas flexibles si se confirma estabilidad.",
        )
    ]
