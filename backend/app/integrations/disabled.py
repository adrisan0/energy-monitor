from __future__ import annotations

from decimal import Decimal

from app.integrations.base import DeviceAdapter, DeviceState


class DisabledDeviceAdapter(DeviceAdapter):
    def __init__(self, reason: str = "FEATURE_SMART_DEVICES=false") -> None:
        self.reason = reason

    async def get_state(self) -> DeviceState:
        return DeviceState(online=False, raw={"disabled": True, "reason": self.reason})

    async def turn_on(self) -> None:
        raise RuntimeError(f"Integracion desactivada: {self.reason}")

    async def turn_off(self) -> None:
        raise RuntimeError(f"Integracion desactivada: {self.reason}")

    async def get_power(self) -> Decimal | None:
        return None

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        del r, g, b, brightness
        raise RuntimeError(f"Integracion desactivada: {self.reason}")
