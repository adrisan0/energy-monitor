from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from kasa import Discover
from kasa.exceptions import KasaException

from app.integrations.base import DeviceAdapter, DeviceState


class KasaHs100Adapter(DeviceAdapter):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def get_state(self) -> DeviceState:
        device = await self._device()
        power = _power_from_device(device)
        raw = {
            "alias": getattr(device, "alias", None),
            "model": getattr(device, "model", None),
            "is_on": getattr(device, "is_on", None),
            "has_emeter": getattr(device, "has_emeter", None),
        }
        return DeviceState(
            online=True,
            is_on=bool(getattr(device, "is_on", False)),
            power_w=power,
            raw=raw,
        )

    async def turn_on(self) -> None:
        device = await self._device()
        await device.turn_on()

    async def turn_off(self) -> None:
        device = await self._device()
        await device.turn_off()

    async def get_power(self) -> Decimal | None:
        state = await self.get_state()
        return state.power_w

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        del r, g, b, brightness
        raise RuntimeError("El adaptador kasa_hs100 no soporta control RGB")

    async def _device(self):
        host = self._host()
        username = self._optional_str("username")
        password = self._optional_str("password")
        try:
            kwargs: dict[str, Any] = {}
            if username and password:
                kwargs["username"] = username
                kwargs["password"] = password
            device = await Discover.discover_single(host, **kwargs)
        except KasaException as exc:
            raise RuntimeError(f"No se pudo conectar con el HS100 en {host}: {exc}") from exc
        return device

    def _host(self) -> str:
        host = self.config.get("ip_address") or self.config.get("host")
        if not isinstance(host, str) or not host.strip():
            raise RuntimeError("Dispositivo kasa_hs100 sin config.ip_address")
        return host.strip()

    def _optional_str(self, key: str) -> str | None:
        value = self.config.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()


def _power_from_device(device: Any) -> Decimal | None:
    if not bool(getattr(device, "has_emeter", False)):
        return None
    emeter = getattr(device, "emeter_realtime", None)
    if isinstance(emeter, dict):
        for key in ("power", "power_mw", "current_power"):
            if key not in emeter:
                continue
            value = _to_decimal(emeter.get(key))
            if value is None:
                continue
            if key == "power_mw":
                return value / Decimal("1000")
            return value
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "unknown", "unavailable"):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
