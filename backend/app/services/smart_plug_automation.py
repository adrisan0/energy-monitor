from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.factory import adapter_for_device
from app.models import Device, MeterSample
from app.services.events import record_event

DEFAULT_THERMO_AUTOMATION = {
    "enabled": False,
    "profile": "surplus_water_heater",
    "surplus_on_w": 1200,
    "surplus_off_w": 150,
    "on_hold_seconds": 120,
    "off_hold_seconds": 120,
    "min_daily_runtime_minutes": 45,
    "topup_window_start_hour": 14,
    "topup_window_end_hour": 18,
    "block_peak_hours": True,
}


@dataclass(frozen=True)
class PlugAutomationDecision:
    should_turn_on: bool
    reason: str
    runtime_today_seconds: int
    blocked_by_peak: bool = False


async def apply_smart_plug_automation_for_sample(db: Session, sample: MeterSample) -> None:
    if sample.data_quality not in {"valid", "partial"}:
        return

    devices = list(
        db.scalars(
            select(Device).where(
                Device.active.is_(True),
                Device.control_mode == "automatic",
                Device.type == "smart_plug",
            )
        )
    )
    for device in devices:
        adapter_kind = str((device.config or {}).get("adapter", ""))
        if adapter_kind not in {"kasa_hs100", "sonoff_s61s"}:
            continue
        if not merged_thermo_automation_config(device.config)["enabled"]:
            continue
        try:
            await apply_smart_plug_automation_to_device(db, device, sample)
        except Exception as exc:  # noqa: BLE001
            record_event(
                db,
                event_type="smart_plug_automation_failed",
                severity="error",
                message=str(exc),
                metadata={"device_id": device.id, "sample_id": sample.id},
            )


async def apply_smart_plug_automation_to_device(
    db: Session,
    device: Device,
    sample: MeterSample,
    *,
    force: bool = False,
) -> PlugAutomationDecision | None:
    if sample.data_quality not in {"valid", "partial"}:
        return None
    if not device.active:
        return None
    if not force and device.control_mode != "automatic":
        return None

    automation = merged_thermo_automation_config(device.config)
    if not force and not automation["enabled"]:
        return None

    state = _merged_state(device.config)
    adapter = adapter_for_device(device)
    current_state = await adapter.get_state()
    is_on = bool(current_state.is_on)
    updated_state = _advance_state(state, sample, is_on)
    decision = _decide(sample, automation, updated_state, is_on)

    if decision.should_turn_on != is_on:
        if decision.should_turn_on:
            await adapter.turn_on()
        else:
            await adapter.turn_off()
        updated_state["is_on"] = decision.should_turn_on
        updated_state["last_switched_at"] = _iso(_aware(getattr(sample, "timestamp_utc", None) or datetime.now(UTC)))
        record_event(
            db,
            event_type="smart_plug_automation_applied",
            severity="info",
            message=f"{'Encendido' if decision.should_turn_on else 'Apagado'} automatico de {device.name}: {decision.reason}",
            metadata={"device_id": device.id, "reason": decision.reason, "sample_id": sample.id},
        )

    updated_state["runtime_today_seconds"] = decision.runtime_today_seconds
    updated_state["blocked_by_peak"] = decision.blocked_by_peak
    updated_state["last_reason"] = decision.reason
    updated_state["last_sample_at"] = _iso(_aware(getattr(sample, "timestamp_utc", None) or datetime.now(UTC)))

    updated_config = dict(device.config or {})
    updated_config["thermo_automation"] = automation
    updated_config["thermo_automation_state"] = updated_state
    device.config = updated_config
    return decision


def merged_thermo_automation_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_THERMO_AUTOMATION)
    raw = config.get("thermo_automation", {})
    if isinstance(raw, dict):
        for key in merged:
            if key in raw:
                merged[key] = raw[key]
    return merged


def _merged_state(config: dict[str, Any]) -> dict[str, Any]:
    state = {
        "runtime_date": None,
        "runtime_today_seconds": 0,
        "last_sample_at": None,
        "surplus_since": None,
        "deficit_since": None,
        "is_on": False,
        "blocked_by_peak": False,
        "last_reason": "idle",
        "last_switched_at": None,
    }
    raw = config.get("thermo_automation_state", {})
    if isinstance(raw, dict):
        state.update(raw)
    return state


def _advance_state(state: dict[str, Any], sample: MeterSample, is_on: bool) -> dict[str, Any]:
    updated = dict(state)
    sample_utc = _aware(getattr(sample, "timestamp_utc", None) or datetime.now(UTC))
    sample_date = str(getattr(sample, "local_date", sample_utc.date()))
    runtime_date = str(updated.get("runtime_date")) if updated.get("runtime_date") else None
    runtime_seconds = int(updated.get("runtime_today_seconds") or 0)

    if runtime_date != sample_date:
        runtime_seconds = 0
        updated["runtime_date"] = sample_date
        updated["surplus_since"] = None
        updated["deficit_since"] = None

    last_sample_at = _parse_dt(updated.get("last_sample_at"))
    if is_on and last_sample_at is not None and last_sample_at.date() == sample_utc.date():
        runtime_seconds += max(0, round((sample_utc - last_sample_at).total_seconds()))

    updated["runtime_today_seconds"] = runtime_seconds
    updated["last_sample_at"] = _iso(sample_utc)
    updated["is_on"] = is_on
    return updated


def _decide(
    sample: MeterSample,
    automation: dict[str, Any],
    state: dict[str, Any],
    is_on: bool,
) -> PlugAutomationDecision:
    local_dt = getattr(sample, "timestamp_local", None) or _aware(getattr(sample, "timestamp_utc", None) or datetime.now(UTC))
    export_w = _decimal(getattr(sample, "grid_export_w", None))
    runtime_today_seconds = int(state.get("runtime_today_seconds") or 0)
    min_runtime_seconds = max(0, int(automation["min_daily_runtime_minutes"]) * 60)
    topup_needed = runtime_today_seconds < min_runtime_seconds
    peak = bool(automation.get("block_peak_hours", True)) and is_peak_time(local_dt)
    in_topup_window = _in_topup_window(
        local_dt,
        int(automation["topup_window_start_hour"]),
        int(automation["topup_window_end_hour"]),
    )

    if peak:
        state["surplus_since"] = None
        state["deficit_since"] = None
        return PlugAutomationDecision(False, "hora_punta", runtime_today_seconds, blocked_by_peak=True)

    if topup_needed and in_topup_window:
        state["surplus_since"] = None
        state["deficit_since"] = None
        return PlugAutomationDecision(True, "minimo_diario", runtime_today_seconds)

    sample_utc = _aware(getattr(sample, "timestamp_utc", None) or datetime.now(UTC))
    surplus_on_w = Decimal(str(automation["surplus_on_w"]))
    surplus_off_w = Decimal(str(automation["surplus_off_w"]))
    on_hold_seconds = int(automation["on_hold_seconds"])
    off_hold_seconds = int(automation["off_hold_seconds"])

    if export_w >= surplus_on_w:
        state["surplus_since"] = state.get("surplus_since") or _iso(sample_utc)
        state["deficit_since"] = None
        held = _held_seconds(state.get("surplus_since"), sample_utc)
        if is_on or held >= on_hold_seconds:
            return PlugAutomationDecision(True, "excedente", runtime_today_seconds)
        return PlugAutomationDecision(False, "esperando_excedente_estable", runtime_today_seconds)

    if export_w <= surplus_off_w:
        state["deficit_since"] = state.get("deficit_since") or _iso(sample_utc)
        state["surplus_since"] = None
        held = _held_seconds(state.get("deficit_since"), sample_utc)
        if is_on and held < off_hold_seconds:
            return PlugAutomationDecision(True, "esperando_fin_excedente", runtime_today_seconds)
        return PlugAutomationDecision(False, "sin_excedente", runtime_today_seconds)

    state["surplus_since"] = None
    state["deficit_since"] = None
    return PlugAutomationDecision(is_on, "banda_muerta", runtime_today_seconds)


def is_peak_time(local_dt: datetime) -> bool:
    if local_dt.weekday() >= 5:
        return False
    hour = local_dt.hour
    return 10 <= hour < 14 or 18 <= hour < 22


def _in_topup_window(local_dt: datetime, start_hour: int, end_hour: int) -> bool:
    hour = local_dt.hour
    return start_hour <= hour < end_hour


def _held_seconds(started_at: str | None, now: datetime) -> int:
    if not started_at:
        return 0
    started = _parse_dt(started_at)
    if started is None:
        return 0
    return max(0, round((now - started).total_seconds()))


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat()


def _decimal(value: Decimal | None) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal("0")
