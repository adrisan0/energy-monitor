from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


def json_column(default: dict[str, Any] | None = None) -> Mapped[dict[str, Any]]:
    return mapped_column(MutableDict.as_mutable(JSON().with_variant(JSONB, "postgresql")), default=default or dict)


class MeterSample(Base):
    __tablename__ = "meter_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    timestamp_local: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    local_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    local_time: Mapped[time] = mapped_column(Time, nullable=False)

    solar_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    grid_import_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    grid_export_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    house_consumption_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    solar_self_consumption_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    solar_self_consumption_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)

    voltage_v: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    current_a: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    frequency_hz: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    power_factor: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)

    pac1: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    pac2: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    fpot1: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fpot2: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    pact: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    raw_variables: Mapped[dict[str, Any]] = json_column()
    raw_payload_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    repeated_payload: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    data_quality: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="valid")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    poll_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EnergyAggregate(Base, TimestampMixin):
    __tablename__ = "energy_aggregates"
    __table_args__ = (UniqueConstraint("period", "period_start_utc"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    period_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    period_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_start_local: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    period_end_local: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    solar_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    grid_import_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    grid_export_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    house_consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    solar_self_consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)

    self_sufficiency_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    surplus_export_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    max_power_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    min_power_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    estimated_cost_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    compensation_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    fixed_cost_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    taxes_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    net_cost_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)

    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incomplete_intervals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DaikinReading(Base):
    """Read-only snapshot of one ONECTA climate unit."""

    __tablename__ = "daikin_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    captured_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(160), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_on: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    operating_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fan_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    outdoor_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    target_temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    heating_today_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    cooling_today_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    energy_profiles: Mapped[dict[str, Any]] = json_column()
    in_error_state: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    in_warning_state: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class TariffSettings(Base, TimestampMixin):
    __tablename__ = "tariff_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), default="flat", nullable=False)
    flat_price_eur_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.180000"), nullable=False)
    peak_price_eur_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.240000"), nullable=False)
    shoulder_price_eur_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.170000"), nullable=False)
    valley_price_eur_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.120000"), nullable=False)
    surplus_compensation_eur_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0.060000"), nullable=False)
    monthly_fixed_cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("29.00"), nullable=False)
    meter_rental_monthly_eur: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    electricity_tax_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("5.1127"), nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("21.0000"), nullable=False)
    billing_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApplianceAnnotation(Base, TimestampMixin):
    __tablename__ = "appliance_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appliance_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    home_area: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    appliance_type: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    approx_power_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), default="confirmed_manual", nullable=False)


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    zone: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False)
    measurement_capable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_power_w: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    control_mode: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    config: Mapped[dict[str, Any]] = json_column()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = json_column()


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(240), index=True, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
