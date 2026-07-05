from __future__ import annotations

from app.core.config import get_settings
from app.integrations.base import DeviceAdapter
from app.integrations.disabled import DisabledDeviceAdapter
from app.models import Device


def adapter_for(kind: str) -> DeviceAdapter:
    settings = get_settings()
    if not settings.feature_smart_devices:
        return DisabledDeviceAdapter()
    if kind == "flux_led":
        from app.integrations.flux_led import FluxLedAdapter

        return FluxLedAdapter({})
    if kind == "home_assistant":
        from app.integrations.home_assistant import HomeAssistantAdapter

        return HomeAssistantAdapter({})
    if kind == "kasa_hs100":
        from app.integrations.kasa_hs100 import KasaHs100Adapter

        return KasaHs100Adapter({})
    if kind == "sonoff_s61s":
        from app.integrations.sonoff_s61s import SonoffS61SAdapter

        return SonoffS61SAdapter({})
    return DisabledDeviceAdapter(reason=f"Adaptador {kind} pendiente de implementacion segura")


def adapter_for_device(device: Device) -> DeviceAdapter:
    settings = get_settings()
    if not settings.feature_smart_devices:
        return DisabledDeviceAdapter()

    adapter_kind = str(device.config.get("adapter", ""))
    if adapter_kind == "flux_led":
        from app.integrations.flux_led import FluxLedAdapter

        config = dict(device.config)
        if device.ip_address and "ip_address" not in config:
            config["ip_address"] = device.ip_address
        return FluxLedAdapter(config)
    if adapter_kind == "home_assistant":
        from app.integrations.home_assistant import HomeAssistantAdapter

        return HomeAssistantAdapter(device.config)
    if adapter_kind == "kasa_hs100":
        from app.integrations.kasa_hs100 import KasaHs100Adapter

        config = dict(device.config)
        if device.ip_address and "ip_address" not in config:
            config["ip_address"] = device.ip_address
        return KasaHs100Adapter(config)
    if adapter_kind == "sonoff_s61s":
        from app.integrations.sonoff_s61s import SonoffS61SAdapter

        config = dict(device.config)
        if device.ip_address and "ip_address" not in config:
            config["ip_address"] = device.ip_address
        return SonoffS61SAdapter(config)

    return DisabledDeviceAdapter(reason=f"Adaptador {adapter_kind or 'desconocido'} pendiente de implementacion segura")
