from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.factory import adapter_for_device
from app.models import Device, MeterSample
from app.services.events import record_event

DEFAULT_AUTOMATION = {
    "enabled": False,
    "metric": "house_consumption_w",
    "profile": "consumption_gradient",
    "surplus_override": True,
    "blink_on_solar_grid_import": True,
    "thresholds": {"low_max_w": 350, "medium_max_w": 1650, "high_max_w": 2800},
    "colors": {
        "low": "#22C55E",
        "medium": "#F59E0B",
        "high": "#EF4444",
        "super": "#3B82F6",
    },
    "brightness": {
        "low": 96,
        "medium": 160,
        "high": 255,
        "super": 180,
    },
    "prices": {
        "low": 0.12,
        "medium": 0.17,
        "high": 0.24,
        "super": 0.24,
    },
}


@dataclass(frozen=True)
class ColorTarget:
    tier: str
    rgb: tuple[int, int, int]
    brightness: int
    blink: bool = False


async def apply_automation_for_sample(db: Session, sample: MeterSample) -> None:
    if sample.data_quality not in {"valid", "partial"}:
        return

    devices = list(
        db.scalars(
            select(Device).where(
                Device.active.is_(True),
                Device.control_mode == "automatic",
            )
        )
    )
    for device in devices:
        adapter_kind = str(device.config.get("adapter", ""))
        if adapter_kind != "flux_led":
            continue
        automation = merged_automation_config(device.config)
        if not automation["enabled"]:
            continue
        recovering_from_outage = (device.config.get("last_applied") or {}).get("tier") == "meter_outage"
        try:
            target = await apply_automation_to_device(db, device, sample, force=recovering_from_outage)
            if recovering_from_outage and target is not None:
                record_event(
                    db,
                    event_type="device_outage_failsafe_cleared",
                    severity="info",
                    message=f"Recuperado color automatico tras volver el medidor en el dispositivo {device.name}",
                    metadata={"device_id": device.id, "sample_id": sample.id, "tier": target.tier},
                )
        except Exception as exc:  # noqa: BLE001
            record_event(
                db,
                event_type="device_automation_failed",
                severity="error",
                message=str(exc),
                metadata={"device_id": device.id, "sample_id": sample.id},
            )


async def apply_meter_outage_failsafe(db: Session) -> None:
    devices = list(
        db.scalars(
            select(Device).where(
                Device.active.is_(True),
                Device.control_mode == "automatic",
            )
        )
    )
    for device in devices:
        adapter_kind = str(device.config.get("adapter", ""))
        if adapter_kind != "flux_led":
            continue
        try:
            await apply_outage_white_to_device(db, device)
        except Exception as exc:  # noqa: BLE001
            record_event(
                db,
                event_type="device_outage_failsafe_failed",
                severity="error",
                message=str(exc),
                metadata={"device_id": device.id},
            )


async def apply_automation_to_device(
    db: Session,
    device: Device,
    sample: MeterSample,
    *,
    force: bool = False,
) -> ColorTarget | None:
    if sample.data_quality not in {"valid", "partial"}:
        return None
    if not device.active:
        return None
    if not force and device.control_mode != "automatic":
        return None

    automation = merged_automation_config(device.config)
    if not force and not automation["enabled"]:
        return None

    target = resolve_color_target(sample, automation)
    if target is None:
        return None

    adapter = adapter_for_device(device)
    state = await adapter.get_state()
    if not state.online or state.is_on is not True:
        return None

    last_applied = device.config.get("last_applied")
    current_payload = {
        "tier": target.tier,
        "rgb": list(target.rgb),
        "brightness": target.brightness,
        "blink": target.blink,
    }
    if not force and last_applied == current_payload:
        return target

    if target.blink:
        await adapter.set_rgb_blink(*target.rgb, brightness=target.brightness)
    else:
        await adapter.set_rgb(*target.rgb, brightness=target.brightness)
    updated_config = dict(device.config)
    updated_config["last_applied"] = current_payload
    device.config = updated_config
    record_event(
        db,
        event_type="device_automation_applied",
        severity="info",
        message=f"Aplicado modo {target.tier}{' parpadeando' if target.blink else ''} al dispositivo {device.name}",
        metadata={"device_id": device.id, "tier": target.tier, "blink": target.blink, "sample_id": sample.id},
    )
    return target


async def apply_outage_white_to_device(db: Session, device: Device) -> bool:
    if not device.active or device.control_mode != "automatic":
        return False

    adapter = adapter_for_device(device)
    state = await adapter.get_state()
    if not state.online or state.is_on is not True:
        return False

    current_payload = {
        "tier": "meter_outage",
        "rgb": [255, 255, 255],
        "brightness": 255,
        "blink": False,
    }
    if device.config.get("last_applied") == current_payload:
        return False

    await adapter.set_rgb(255, 255, 255, brightness=255)
    updated_config = dict(device.config)
    updated_config["last_applied"] = current_payload
    device.config = updated_config
    record_event(
        db,
        event_type="device_outage_failsafe_applied",
        severity="warning",
        message=f"Aplicado blanco de seguridad por perdida de medidor al dispositivo {device.name}",
        metadata={"device_id": device.id},
    )
    return True


def merged_automation_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "enabled": DEFAULT_AUTOMATION["enabled"],
        "metric": DEFAULT_AUTOMATION["metric"],
        "profile": DEFAULT_AUTOMATION["profile"],
        "surplus_override": DEFAULT_AUTOMATION["surplus_override"],
        "blink_on_solar_grid_import": DEFAULT_AUTOMATION["blink_on_solar_grid_import"],
        "thresholds": dict(DEFAULT_AUTOMATION["thresholds"]),
        "colors": dict(DEFAULT_AUTOMATION["colors"]),
        "brightness": dict(DEFAULT_AUTOMATION["brightness"]),
        "prices": dict(DEFAULT_AUTOMATION["prices"]),
    }
    automation = config.get("automation", {})
    if isinstance(automation, dict):
        merged.update(
            {
                k: v
                for k, v in automation.items()
                if k in {"enabled", "metric", "profile", "surplus_override", "blink_on_solar_grid_import"}
            }
        )
        if isinstance(automation.get("thresholds"), dict):
            merged["thresholds"].update(automation["thresholds"])
        for section in ("colors", "brightness", "prices"):
            if isinstance(automation.get(section), dict):
                values = dict(automation[section])
                if "super" not in values and "surplus" in values:
                    values["super"] = values["surplus"]
                merged[section].update(values)
    return merged


def resolve_color_target(sample: MeterSample, automation: dict[str, Any]) -> ColorTarget | None:
    profile = str(automation.get("profile", "consumption_gradient"))
    if profile == "grid_import_alert":
        return _resolve_grid_import_alert_target(sample, automation)
    if profile == "tariff_price":
        return _resolve_tariff_price_target(sample, automation)

    target = _resolve_consumption_gradient_target(sample, automation)
    solar_blink_min_w = Decimal(str(automation["thresholds"]["low_max_w"]))
    if (
        automation.get("blink_on_solar_grid_import", True)
        and _decimal(sample.solar_w) > solar_blink_min_w
        and _decimal(sample.grid_import_w) > Decimal("0")
    ):
        return ColorTarget(target.tier, target.rgb, target.brightness, blink=True)

    if automation.get("surplus_override", True) and _decimal(sample.grid_export_w) > Decimal("0"):
        return ColorTarget("super", _hex_to_rgb(automation["colors"]["super"]), int(automation["brightness"]["super"]))

    return target


def _resolve_consumption_gradient_target(sample: MeterSample, automation: dict[str, Any]) -> ColorTarget:
    metric_name = str(automation.get("metric", "house_consumption_w"))
    metric_value = _decimal(getattr(sample, metric_name, None))
    low_max = Decimal(str(automation["thresholds"]["low_max_w"]))
    medium_max = Decimal(str(automation["thresholds"]["medium_max_w"]))
    high_max = Decimal(str(automation["thresholds"]["high_max_w"]))

    if metric_value < low_max:
        tier = "low"
        ratio = _safe_ratio(metric_value, Decimal("0"), low_max)
        rgb = _interpolate_rgb(_hex_to_rgb(automation["colors"]["low"]), _hex_to_rgb(automation["colors"]["medium"]), ratio)
        brightness = _interpolate_int(int(automation["brightness"]["low"]), int(automation["brightness"]["medium"]), ratio)
    elif metric_value < medium_max:
        tier = "medium"
        ratio = _safe_ratio(metric_value, low_max, medium_max)
        rgb = _interpolate_rgb(_hex_to_rgb(automation["colors"]["medium"]), _hex_to_rgb(automation["colors"]["high"]), ratio)
        brightness = _interpolate_int(int(automation["brightness"]["medium"]), int(automation["brightness"]["high"]), ratio)
    elif metric_value < high_max:
        tier = "high"
        ratio = _safe_ratio(metric_value, medium_max, high_max)
        rgb = _interpolate_rgb(_hex_to_rgb(automation["colors"]["high"]), _hex_to_rgb(automation["colors"]["super"]), ratio)
        brightness = _interpolate_int(int(automation["brightness"]["high"]), int(automation["brightness"]["super"]), ratio)
    else:
        tier = "super"
        rgb = _hex_to_rgb(automation["colors"]["super"])
        brightness = int(automation["brightness"]["super"])
    return ColorTarget(tier, rgb, brightness)


def _resolve_grid_import_alert_target(sample: MeterSample, automation: dict[str, Any]) -> ColorTarget:
    imported = _decimal(sample.grid_import_w)
    if imported <= Decimal("0"):
        return ColorTarget("low", _hex_to_rgb(automation["colors"]["low"]), int(automation["brightness"]["low"]))

    low_max = Decimal(str(automation["thresholds"]["low_max_w"]))
    medium_max = Decimal(str(automation["thresholds"]["medium_max_w"]))
    high_max = Decimal(str(automation["thresholds"]["high_max_w"]))
    if imported < low_max:
        return ColorTarget("medium", _hex_to_rgb(automation["colors"]["medium"]), int(automation["brightness"]["medium"]))
    if imported < medium_max:
        return ColorTarget("high", _hex_to_rgb(automation["colors"]["high"]), int(automation["brightness"]["high"]))
    if imported < high_max:
        return ColorTarget("super", _hex_to_rgb(automation["colors"]["super"]), int(automation["brightness"]["super"]))
    return ColorTarget("super", _hex_to_rgb(automation["colors"]["super"]), int(automation["brightness"]["super"]))


def _resolve_tariff_price_target(sample: MeterSample, automation: dict[str, Any]) -> ColorTarget:
    tier = _tariff_tier_for_sample(sample)
    return ColorTarget(tier, _hex_to_rgb(automation["colors"][tier]), int(automation["brightness"][tier]))


def _tariff_tier_for_sample(sample: MeterSample) -> str:
    timestamp = getattr(sample, "timestamp_local", None) or getattr(sample, "timestamp_utc", None)
    if timestamp is None:
        return "medium"
    if timestamp.weekday() >= 5:
        return "low"

    hour = timestamp.hour
    if 10 <= hour < 14 or 18 <= hour < 22:
        return "high"
    if 8 <= hour < 10 or 14 <= hour < 18 or 22 <= hour < 24:
        return "medium"
    return "low"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    clean = hex_color.strip().lstrip("#")
    if len(clean) != 6:
        raise ValueError(f"Color invalido: {hex_color}")
    return tuple(int(clean[i : i + 2], 16) for i in (0, 2, 4))


def _safe_ratio(value: Decimal, start: Decimal, end: Decimal) -> float:
    span = end - start
    if span <= Decimal("0"):
        return 1.0
    ratio = (value - start) / span
    return max(0.0, min(1.0, float(ratio)))


def _interpolate_rgb(start: tuple[int, int, int], end: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(_interpolate_int(start[i], end[i], ratio) for i in range(3))


def _interpolate_int(start: int, end: int, ratio: float) -> int:
    return max(0, min(255, round(start + ((end - start) * ratio))))


def _decimal(value: Decimal | None) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal("0")
