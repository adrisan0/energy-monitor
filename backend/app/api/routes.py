from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Awaitable, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.orm import Session

from app.analytics.detectors import detect_analysis_events
from app.core.auth import require_write_token
from app.core.config import get_settings
from app.core.timezone import to_local, to_utc, utc_now
from app.db.session import get_db
from app.integrations.factory import adapter_for_device
from app.models import (
    ApplianceAnnotation,
    BackupRecord,
    DaikinReading,
    Device,
    EnergyAggregate,
    MeterSample,
    SmartPlugReading,
    SystemEvent,
)
from app.schemas.annotations import AnnotationCreate, AnnotationRead, AnnotationUpdate
from app.schemas.common import HealthResponse, Message
from app.schemas.devices import DeviceColorUpdate, DeviceModeUpdate, DeviceRead, DeviceStateRead, DeviceUpdate
from app.schemas.energy import AggregateRead, EnergyComparison, EnergySummary
from app.schemas.measurements import LatestResponse, MeasurementRead, RawPayloadRead
from app.schemas.system import BackupRead, EventRead, SystemStatus
from app.schemas.tariffs import TariffRead, TariffUpdate
from app.services.backup import list_backup_files, run_backup
from app.services.bootstrap import ensure_initial_data
from app.services.device_automation import apply_automation_to_device
from app.services.exporter import iter_measurement_csv
from app.services.smart_plug_automation import apply_smart_plug_automation_to_device
from app.services.tariffs import get_or_create_tariff

router = APIRouter()
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=utc_now(), simulation_mode=get_settings().simulation_mode)


@router.get("/latest", response_model=LatestResponse, tags=["measurements"])
def latest(db: DbDep) -> LatestResponse:
    sample = _latest_usable_sample(db) or _latest_sample(db)
    if sample is None:
        raise HTTPException(status_code=404, detail="No hay lecturas todavia")
    age = (utc_now() - _aware(sample.timestamp_utc)).total_seconds()
    return LatestResponse(
        timestamp=sample.timestamp_local,
        solar_w=_float(sample.solar_w),
        grid_import_w=_float(sample.grid_import_w),
        grid_export_w=_float(sample.grid_export_w),
        house_consumption_w=_float(sample.house_consumption_w),
        solar_self_consumption_w=_float(sample.solar_self_consumption_w),
        solar_self_consumption_percent=_float(sample.solar_self_consumption_percent),
        data_quality=sample.data_quality,
        meter_online=age <= get_settings().prolonged_outage_seconds and sample.data_quality in {"valid", "partial"},
        seconds_since_last_reading=age,
    )


@router.get("/climate/daikin/latest", tags=["climate"])
def latest_daikin_readings(db: DbDep) -> dict[str, Any]:
    latest_by_device = (
        select(DaikinReading.device_id, func.max(DaikinReading.captured_at_utc).label("captured_at_utc"))
        .group_by(DaikinReading.device_id)
        .subquery()
    )
    rows = db.scalars(
        select(DaikinReading)
        .join(
            latest_by_device,
            and_(
                DaikinReading.device_id == latest_by_device.c.device_id,
                DaikinReading.captured_at_utc == latest_by_device.c.captured_at_utc,
            ),
        )
        .order_by(DaikinReading.device_name.asc())
    ).all()
    return {"configured": get_settings().feature_daikin, "data": [_daikin_reading_dict(row, include_profiles=True) for row in rows]}


@router.get("/climate/daikin/readings", tags=["climate"])
def daikin_readings(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    device_id: str | None = Query(default=None),
    limit: int = Query(default=20000, ge=1, le=20000),
) -> dict[str, Any]:
    query = select(DaikinReading)
    if start:
        query = query.where(DaikinReading.captured_at_utc >= to_utc(start))
    if end:
        query = query.where(DaikinReading.captured_at_utc <= to_utc(end))
    if device_id:
        query = query.where(DaikinReading.device_id == device_id)
    rows = db.scalars(query.order_by(desc(DaikinReading.captured_at_utc)).limit(limit)).all()
    return {"data": [_daikin_reading_dict(row, include_profiles=False) for row in rows]}


@router.get("/smart-plugs/latest", tags=["smart-plugs"])
def latest_smart_plug_readings(db: DbDep) -> dict[str, Any]:
    latest_by_device = (
        select(SmartPlugReading.device_id, func.max(SmartPlugReading.captured_at_utc).label("captured_at_utc"))
        .group_by(SmartPlugReading.device_id)
        .subquery()
    )
    rows = db.scalars(
        select(SmartPlugReading)
        .join(
            latest_by_device,
            and_(
                SmartPlugReading.device_id == latest_by_device.c.device_id,
                SmartPlugReading.captured_at_utc == latest_by_device.c.captured_at_utc,
            ),
        )
        .order_by(SmartPlugReading.device_name.asc())
    ).all()
    return {"data": [_smart_plug_reading_dict(row) for row in rows]}


@router.get("/smart-plugs/readings", tags=["smart-plugs"])
def smart_plug_readings(
    db: DbDep,
    device_id: int = Query(ge=1),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
) -> dict[str, Any]:
    query = select(SmartPlugReading).where(SmartPlugReading.device_id == device_id)
    if start:
        query = query.where(SmartPlugReading.captured_at_utc >= to_utc(start))
    if end:
        query = query.where(SmartPlugReading.captured_at_utc <= to_utc(end))
    rows = db.scalars(query.order_by(desc(SmartPlugReading.captured_at_utc)).limit(limit)).all()
    return {"data": [_smart_plug_reading_dict(row) for row in rows]}


@router.get("/measurements", tags=["measurements"])
def measurements(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    resolution: str = Query(default="raw", pattern="^(raw|minute|hour|day|month|year)$"),
    data_quality: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=50000),
) -> dict[str, Any]:
    if resolution == "raw":
        sample_query = select(MeterSample)
        if start:
            sample_query = sample_query.where(MeterSample.timestamp_utc >= to_utc(start))
        if end:
            sample_query = sample_query.where(MeterSample.timestamp_utc <= to_utc(end))
        if data_quality:
            sample_query = sample_query.where(MeterSample.data_quality == data_quality)
        sample_rows = db.scalars(sample_query.order_by(MeterSample.timestamp_utc.desc()).limit(limit)).all()
        return {"resolution": "raw", "data": [MeasurementRead.model_validate(row).model_dump(mode="json") for row in sample_rows]}

    aggregate_query = select(EnergyAggregate).where(EnergyAggregate.period == resolution)
    if start:
        aggregate_query = aggregate_query.where(EnergyAggregate.period_start_utc >= to_utc(start))
    if end:
        aggregate_query = aggregate_query.where(EnergyAggregate.period_start_utc <= to_utc(end))
    aggregate_rows = db.scalars(aggregate_query.order_by(EnergyAggregate.period_start_utc.desc()).limit(limit)).all()
    return {
        "resolution": resolution,
        "data": [AggregateRead.model_validate(row).model_dump(mode="json") for row in aggregate_rows],
    }


@router.get("/measurements/raw/latest", response_model=RawPayloadRead, tags=["measurements"])
def raw_latest(db: DbDep) -> RawPayloadRead:
    sample = _latest_sample(db)
    if sample is None:
        raise HTTPException(status_code=404, detail="No hay payloads todavia")
    return RawPayloadRead(
        id=sample.id,
        timestamp_utc=sample.timestamp_utc,
        timestamp_local=sample.timestamp_local,
        raw_payload_redacted=sample.raw_payload_redacted,
        raw_variables=sample.raw_variables,
        payload_hash=sample.payload_hash,
        repeated_payload=sample.repeated_payload,
        data_quality=sample.data_quality,
        error_message=sample.error_message,
        poll_duration_ms=sample.poll_duration_ms,
    )


@router.get("/energy/summary", response_model=EnergySummary, tags=["energy"])
def energy_summary(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    period: str = Query(default="day", pattern="^(hour|day|month|year)$"),
) -> EnergySummary:
    start_utc, end_utc = _default_range(start, end)
    return _summary(db, start_utc, end_utc, period)


@router.get("/energy/comparison", response_model=EnergyComparison, tags=["energy"])
def energy_comparison(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    period: str = Query(default="day", pattern="^(hour|day|month|year)$"),
) -> EnergyComparison:
    start_utc, end_utc = _default_range(start, end)
    duration = end_utc - start_utc
    current = _summary(db, start_utc, end_utc, period)
    previous = _summary(db, start_utc - duration, start_utc, period)
    return EnergyComparison(
        current=current,
        previous=previous,
        delta_net_cost_eur=current.net_cost_eur - previous.net_cost_eur,
        delta_house_consumption_kwh=current.house_consumption_kwh - previous.house_consumption_kwh,
    )


@router.get("/energy/aggregates", response_model=list[AggregateRead], tags=["energy"])
def energy_aggregates(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    period: str = Query(default="day", pattern="^(minute|hour|day|month|year)$"),
    limit: int = Query(default=1000, ge=1, le=10000),
) -> list[EnergyAggregate]:
    query = select(EnergyAggregate).where(EnergyAggregate.period == period)
    if start:
        query = query.where(EnergyAggregate.period_start_utc >= to_utc(start))
    if end:
        query = query.where(EnergyAggregate.period_start_utc <= to_utc(end))
    return list(db.scalars(query.order_by(EnergyAggregate.period_start_utc.desc()).limit(limit)))


@router.get("/tariff", response_model=TariffRead, tags=["tariff"])
def get_tariff(db: DbDep) -> TariffRead:
    tariff = get_or_create_tariff(db)
    db.commit()
    return TariffRead.model_validate(tariff)


@router.put("/tariff", response_model=TariffRead, dependencies=[Depends(require_write_token)], tags=["tariff"])
def update_tariff(db: DbDep, payload: TariffUpdate) -> TariffRead:
    tariff = get_or_create_tariff(db)
    for key, value in payload.model_dump().items():
        setattr(tariff, key, value)
    db.commit()
    db.refresh(tariff)
    return TariffRead.model_validate(tariff)


@router.get("/annotations", response_model=list[AnnotationRead], tags=["annotations"])
def list_annotations(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    zone: str | None = Query(default=None),
) -> list[ApplianceAnnotation]:
    query = select(ApplianceAnnotation)
    if start:
        query = query.where(ApplianceAnnotation.starts_at >= to_utc(start))
    if end:
        query = query.where(ApplianceAnnotation.starts_at <= to_utc(end))
    if zone:
        query = query.where(ApplianceAnnotation.home_area == zone)
    return list(db.scalars(query.order_by(ApplianceAnnotation.starts_at.desc()).limit(1000)))


@router.post("/annotations", response_model=AnnotationRead, tags=["annotations"])
def create_annotation(db: DbDep, payload: AnnotationCreate) -> ApplianceAnnotation:
    annotation = ApplianceAnnotation(**payload.model_dump())
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.patch("/annotations/{annotation_id}", response_model=AnnotationRead, tags=["annotations"])
def patch_annotation(db: DbDep, annotation_id: int, payload: AnnotationUpdate) -> ApplianceAnnotation:
    annotation = db.get(ApplianceAnnotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Anotacion no encontrada")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(annotation, key, value)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.delete("/annotations/{annotation_id}", response_model=Message, tags=["annotations"])
def delete_annotation(db: DbDep, annotation_id: int) -> Message:
    annotation = db.get(ApplianceAnnotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Anotacion no encontrada")
    db.delete(annotation)
    db.commit()
    return Message(message="Anotacion eliminada")


@router.get("/devices", response_model=list[DeviceRead], tags=["devices"])
def devices(db: DbDep) -> list[Device]:
    ensure_initial_data(db)
    db.commit()
    return list(db.scalars(select(Device).order_by(Device.name.asc())))


@router.get("/devices/{device_id}/state", response_model=DeviceStateRead, tags=["devices"])
async def device_state(db: DbDep, device_id: int) -> DeviceStateRead:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    state = await adapter_for_device(device).get_state()
    return DeviceStateRead(
        online=state.online,
        is_on=state.is_on,
        power_w=_float(state.power_w),
        raw=state.raw,
    )


@router.post("/devices/{device_id}/on", response_model=Message, dependencies=[Depends(require_write_token)], tags=["devices"])
async def device_turn_on(db: DbDep, device_id: int) -> Message:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await _run_device_command(adapter_for_device(device).turn_on, device)
    return Message(message="Dispositivo encendido")


@router.post("/devices/{device_id}/off", response_model=Message, dependencies=[Depends(require_write_token)], tags=["devices"])
async def device_turn_off(db: DbDep, device_id: int) -> Message:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await _run_device_command(adapter_for_device(device).turn_off, device)
    return Message(message="Dispositivo apagado")


@router.post("/devices/{device_id}/color", response_model=Message, dependencies=[Depends(require_write_token)], tags=["devices"])
async def device_set_color(db: DbDep, device_id: int, payload: Any = Body(...)) -> Message:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    parsed = _parse_body_model(payload, DeviceColorUpdate)
    rgb = parsed.rgb
    adapter = adapter_for_device(device)
    await _run_device_command(lambda: adapter.set_rgb(rgb[0], rgb[1], rgb[2], brightness=parsed.brightness), device)
    updated_config = dict(device.config)
    updated_config["last_applied"] = {
        "tier": "manual",
        "rgb": rgb,
        "brightness": parsed.brightness,
    }
    device.config = updated_config
    db.commit()
    return Message(message="Color aplicado")


@router.post("/devices/{device_id}/mode", response_model=Message, dependencies=[Depends(require_write_token)], tags=["devices"])
def device_set_mode(db: DbDep, device_id: int, payload: Any = Body(...)) -> Message:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    parsed = _parse_body_model(payload, DeviceModeUpdate)
    device.control_mode = parsed.mode
    db.commit()
    return Message(message=f"Modo {parsed.mode} aplicado")


@router.post(
    "/devices/{device_id}/apply-automation",
    response_model=Message,
    dependencies=[Depends(require_write_token)],
    tags=["devices"],
)
async def device_apply_automation(db: DbDep, device_id: int) -> Message:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    sample = _latest_usable_sample(db)
    if sample is None:
        raise HTTPException(status_code=404, detail="No hay lecturas utiles")
    adapter_kind = str((device.config or {}).get("adapter", ""))
    try:
        if adapter_kind == "flux_led":
            target = await apply_automation_to_device(db, device, sample, force=True)
        elif adapter_kind in {"kasa_hs100", "sonoff_s61s"}:
            target = await apply_smart_plug_automation_to_device(db, device, sample, force=True)
        else:
            raise HTTPException(status_code=400, detail="Este dispositivo no soporta automatizacion aplicable")
    except (OSError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo comunicar con {device.name}. Comprueba que esta encendido y accesible en la red local.",
        ) from exc
    db.commit()
    if target is None:
        return Message(message="Automatizacion no aplicable")
    if hasattr(target, "tier"):
        return Message(message=f"Automatizacion aplicada: {target.tier}")
    return Message(message=f"Automatizacion aplicada: {target.reason}")


@router.patch("/devices/{device_id}", response_model=DeviceRead, dependencies=[Depends(require_write_token)], tags=["devices"])
def update_device(db: DbDep, device_id: int, payload: Any = Body(...)) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    parsed = _parse_body_model(payload, DeviceUpdate)
    for key, value in parsed.model_dump(exclude_unset=True).items():
        setattr(device, key, value)

    db.commit()
    db.refresh(device)
    return device


@router.get("/events", tags=["events"])
def events(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> dict[str, Any]:
    query = select(SystemEvent)
    if start:
        query = query.where(SystemEvent.timestamp_utc >= to_utc(start))
    if end:
        query = query.where(SystemEvent.timestamp_utc <= to_utc(end))
    if event_type:
        query = query.where(SystemEvent.event_type == event_type)
    system_events = list(db.scalars(query.order_by(SystemEvent.timestamp_utc.desc()).limit(500)))
    analysis = detect_analysis_events(db, to_utc(start) if start else None, to_utc(end) if end else None)
    return {
        "system": [EventRead.model_validate(item).model_dump(mode="json") for item in system_events],
        "analysis": [item.model_dump(mode="json") for item in analysis],
    }


@router.get("/export/csv", tags=["export"])
def export_csv(
    db: DbDep,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    data_quality: str | None = Query(default=None),
) -> StreamingResponse:
    headers = {"Content-Disposition": "attachment; filename=energy_measurements.csv"}
    return StreamingResponse(
        iter_measurement_csv(
            db,
            start=to_utc(start) if start else None,
            end=to_utc(end) if end else None,
            data_quality=data_quality,
        ),
        media_type="text/csv",
        headers=headers,
    )


@router.get("/system/status", response_model=SystemStatus, tags=["system"])
def system_status(db: DbDep) -> SystemStatus:
    db.execute(text("select 1"))
    sample = _latest_sample(db)
    latest_at = sample.timestamp_utc if sample else None
    age = (utc_now() - _aware(latest_at)).total_seconds() if latest_at else None
    settings = get_settings()
    return SystemStatus(
        backend="ok",
        database="ok",
        meter_online=bool(sample and age is not None and age <= settings.prolonged_outage_seconds),
        simulation_mode=settings.simulation_mode,
        latest_sample_at=latest_at,
        latest_data_quality=sample.data_quality if sample else None,
        feature_flags={
            "automations": settings.feature_automations,
            "telegram": settings.feature_telegram,
            "smart_devices": settings.feature_smart_devices,
            "daikin": settings.feature_daikin,
        },
        backups_path=str(settings.backup_dir),
    )


@router.post(
    "/backups/run",
    response_model=BackupRead,
    dependencies=[Depends(require_write_token)],
    tags=["backups"],
)
def backup_run(db: DbDep) -> BackupRecord:
    record = run_backup(db)
    db.commit()
    db.refresh(record)
    return record


@router.get("/backups", response_model=list[BackupRead], tags=["backups"])
def backups(db: DbDep) -> list[BackupRecord]:
    return list_backup_files(db)


def _latest_sample(db: Session) -> MeterSample | None:
    return db.scalar(select(MeterSample).order_by(desc(MeterSample.timestamp_utc)).limit(1))


def _latest_usable_sample(db: Session) -> MeterSample | None:
    return db.scalar(
        select(MeterSample)
        .where(MeterSample.data_quality.in_(["valid", "partial"]))
        .order_by(desc(MeterSample.timestamp_utc))
        .limit(1)
    )


def _default_range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    end_utc = to_utc(end) if end else utc_now()
    if start:
        return to_utc(start), end_utc
    local_end = to_local(end_utc)
    local_start = local_end.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(UTC), end_utc


def _summary(db: Session, start: datetime, end: datetime, period: str) -> EnergySummary:
    rows = list(
        db.scalars(
            select(EnergyAggregate).where(
                EnergyAggregate.period == period,
                EnergyAggregate.period_start_utc >= start,
                EnergyAggregate.period_start_utc < end,
            )
        )
    )
    solar = sum((row.solar_kwh for row in rows), Decimal("0"))
    imported = sum((row.grid_import_kwh for row in rows), Decimal("0"))
    exported = sum((row.grid_export_kwh for row in rows), Decimal("0"))
    consumption = sum((row.house_consumption_kwh for row in rows), Decimal("0"))
    self_consumption = sum((row.solar_self_consumption_kwh for row in rows), Decimal("0"))
    variable = sum((row.estimated_cost_eur for row in rows), Decimal("0"))
    compensation = sum((row.compensation_eur for row in rows), Decimal("0"))
    fixed = sum((row.fixed_cost_eur for row in rows), Decimal("0"))
    taxes = sum((row.taxes_eur for row in rows), Decimal("0"))
    net = sum((row.net_cost_eur for row in rows), Decimal("0"))
    incomplete = sum(row.incomplete_intervals for row in rows)
    return EnergySummary(
        start=start,
        end=end,
        solar_kwh=float(solar),
        grid_import_kwh=float(imported),
        grid_export_kwh=float(exported),
        house_consumption_kwh=float(consumption),
        solar_self_consumption_kwh=float(self_consumption),
        self_sufficiency_percent=_percent_float(self_consumption, consumption),
        surplus_export_percent=_percent_float(exported, solar),
        estimated_cost_eur=float(variable),
        compensation_eur=float(compensation),
        fixed_cost_eur=float(fixed),
        taxes_eur=float(taxes),
        net_cost_eur=float(net),
        incomplete_intervals=incomplete,
        note="Estimacion local configurable; no equivale necesariamente a la factura real.",
    )


def _percent_float(numerator: Decimal, denominator: Decimal) -> float | None:
    if denominator <= 0:
        return None
    return float((numerator / denominator * Decimal("100")).quantize(Decimal("0.001")))


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def _daikin_reading_dict(row: DaikinReading, *, include_profiles: bool = False) -> dict[str, Any]:
    return {
        "id": row.id,
        "captured_at_utc": row.captured_at_utc,
        "device_id": row.device_id,
        "device_name": row.device_name,
        "model": row.model,
        "is_on": row.is_on,
        "operating_mode": row.operating_mode,
        "fan_mode": row.fan_mode,
        "room_temperature_c": _float(row.room_temperature_c),
        "outdoor_temperature_c": _float(row.outdoor_temperature_c),
        "target_temperature_c": _float(row.target_temperature_c),
        "heating_today_kwh": _float(row.heating_today_kwh),
        "cooling_today_kwh": _float(row.cooling_today_kwh),
        "energy_profiles": row.energy_profiles if include_profiles else {},
        "in_error_state": row.in_error_state,
        "in_warning_state": row.in_warning_state,
    }


def _smart_plug_reading_dict(row: SmartPlugReading) -> dict[str, Any]:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "device_name": row.device_name,
        "captured_at_utc": row.captured_at_utc,
        "online": row.online,
        "is_on": row.is_on,
        "power_w": _float(row.power_w),
        "energy_increment_kwh": _float(row.energy_increment_kwh),
    }


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def _run_device_command(command: Callable[[], Awaitable[None]], device: Device) -> None:
    try:
        await command()
    except (OSError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo comunicar con {device.name}. Comprueba que esta encendido y accesible en la red local.",
        ) from exc


def _parse_body_model(payload: Any, model: type[Any]) -> Any:
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="Payload JSON invalido: bytes no UTF-8") from exc
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Payload JSON invalido: {exc.msg}") from exc
    return model.model_validate(payload)
