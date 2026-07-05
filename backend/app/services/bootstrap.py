from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device
from app.services.tariffs import get_or_create_tariff

DEFAULT_DEVICES = [
    {
        "name": "Sonoff S61S termo padres",
        "manufacturer": "Sonoff",
        "model": "S61S",
        "type": "smart_plug",
        "zone": "padres",
        "measurement_capable": True,
        "status": "planned",
        "config": {"feature_flag": "FEATURE_SMART_DEVICES", "adapter": "sonoff_s61s"},
    },
    {
        "name": "TP-Link HS100 termo",
        "manufacturer": "TP-Link",
        "model": "HS100",
        "type": "smart_plug",
        "zone": "termo",
        "measurement_capable": False,
        "status": "active",
        "control_mode": "manual",
        "config": {
            "feature_flag": "FEATURE_SMART_DEVICES",
            "adapter": "kasa_hs100",
            "thermo_automation": {
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
            },
        },
    },
    {
        "name": "Home Assistant futuro",
        "manufacturer": "Home Assistant",
        "model": "REST/MQTT",
        "type": "hub",
        "zone": "local",
        "measurement_capable": True,
        "status": "planned",
        "config": {"feature_flag": "FEATURE_SMART_DEVICES", "adapter": "home_assistant"},
    },
    {
        "name": "Lampara Flux LED",
        "manufacturer": "Magic Home / Flux",
        "model": "Controller RGB",
        "type": "light_controller",
        "zone": "lampara",
        "ip_address": "192.168.1.29",
        "measurement_capable": False,
        "status": "active",
        "control_mode": "automatic",
        "config": {
            "feature_flag": "FEATURE_SMART_DEVICES",
            "adapter": "flux_led",
            "ip_address": "192.168.1.29",
            "automation": {
                "enabled": False,
                "metric": "house_consumption_w",
                "surplus_override": True,
                "thresholds": {"low_max_w": 350, "medium_max_w": 1650},
                "colors": {
                    "low": "#22C55E",
                    "medium": "#F59E0B",
                    "high": "#EF4444",
                    "surplus": "#3B82F6",
                },
                "brightness": {"low": 96, "medium": 160, "high": 255, "surplus": 180},
                "prices": {"low": 0.12, "medium": 0.17, "high": 0.24, "surplus": 0.24},
            },
        },
    },
    {
        "name": "Bulbo Magic Home",
        "manufacturer": "Magic Home / Flux",
        "model": "Bulb RGBCW",
        "type": "light_controller",
        "zone": "bulbo",
        "ip_address": "192.168.1.55",
        "measurement_capable": False,
        "status": "active",
        "control_mode": "automatic",
        "config": {
            "feature_flag": "FEATURE_SMART_DEVICES",
            "adapter": "flux_led",
            "ip_address": "192.168.1.55",
            "automation": {
                "enabled": True,
                "profile": "consumption_gradient",
                "metric": "house_consumption_w",
                "surplus_override": False,
                "blink_on_solar_grid_import": True,
                "thresholds": {"low_max_w": 500, "medium_max_w": 1650},
                "colors": {
                    "low": "#22C55E",
                    "medium": "#ffc800",
                    "high": "#ff004c",
                    "surplus": "#3B82F6",
                },
                "brightness": {"low": 96, "medium": 160, "high": 255, "surplus": 180},
                "prices": {"low": 0.12, "medium": 0.17, "high": 0.24, "surplus": 0.24},
            },
        },
    },
    {
        "name": "MQTT local futuro",
        "manufacturer": "MQTT",
        "model": "broker",
        "type": "message_bus",
        "zone": "local",
        "measurement_capable": True,
        "status": "planned",
        "config": {"feature_flag": "FEATURE_SMART_DEVICES", "adapter": "mqtt"},
    },
    {
        "name": "Alexa futuro",
        "manufacturer": "Amazon",
        "model": "Alexa",
        "type": "voice_assistant",
        "zone": "local",
        "measurement_capable": False,
        "status": "planned",
        "config": {"feature_flag": "FEATURE_AUTOMATIONS", "adapter": "alexa"},
    },
]


def ensure_initial_data(db: Session) -> None:
    get_or_create_tariff(db)
    existing = set(db.scalars(select(Device.name)))
    for item in DEFAULT_DEVICES:
        if item["name"] not in existing:
            db.add(Device(**item))
    db.flush()
