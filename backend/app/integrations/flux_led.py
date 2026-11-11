from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from flux_led import WifiLedBulb

from app.integrations.base import DeviceAdapter, DeviceState


class FluxLedAdapter(DeviceAdapter):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def get_state(self) -> DeviceState:
        try:
            bulb = await self._query_bulb()
        except (OSError, TimeoutError) as exc:
            return DeviceState(
                online=False,
                raw={"error": "device_unreachable", "detail": str(exc), "ip_address": self._ip_address()},
            )
        rgb = getattr(bulb, "rgb", None)
        brightness = getattr(bulb, "brightness", None)
        power = _brightness_to_power(brightness)
        raw = {
            "mode": getattr(bulb, "mode", None),
            "model": getattr(bulb, "model", None),
            "color_mode": getattr(bulb, "color_mode", None),
            "rgb": list(rgb) if isinstance(rgb, tuple) else rgb,
            "brightness": brightness,
            "white_active": getattr(bulb, "white_active", None),
            "warm_white": getattr(bulb, "warm_white", None),
            "cold_white": getattr(bulb, "cold_white", None),
        }
        return DeviceState(
            online=True,
            is_on=bool(getattr(bulb, "is_on", None)),
            power_w=power,
            raw=raw,
        )

    async def turn_on(self) -> None:
        await self._run_blocking(self._turn_on_sync)

    async def turn_off(self) -> None:
        await self._run_blocking(self._turn_off_sync)

    async def get_power(self) -> Decimal | None:
        state = await self.get_state()
        return state.power_w

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        await self._run_blocking(lambda: self._set_rgb_sync(r, g, b, brightness))

    async def set_rgb_blink(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        await self._run_blocking(lambda: self._set_rgb_blink_sync(r, g, b, brightness))

    def _turn_on_sync(self) -> None:
        bulb = self._make_bulb()
        bulb.turnOn()

    def _turn_off_sync(self) -> None:
        bulb = self._make_bulb()
        bulb.turnOff()

    def _set_rgb_sync(self, r: int, g: int, b: int, brightness: int | None) -> None:
        bulb = self._make_bulb()
        if _is_white_channel_bulb(bulb):
            bulb.setRgb(r, g, b, brightness=brightness)
            return
        if _supports_white_channels(bulb):
            # RGBCW bulbs can keep a white channel active unless we zero it explicitly.
            bulb.setRgbw(r, g, b, 0, brightness=brightness, w2=0)
            return
        bulb.setRgb(r, g, b, brightness=brightness)

    def _set_rgb_blink_sync(self, r: int, g: int, b: int, brightness: int | None) -> None:
        bulb = self._make_bulb()
        if _is_white_channel_bulb(bulb):
            bulb.set_effect(_nearest_strobe_effect((r, g, b)), speed=60, brightness=_effect_brightness(brightness))
            return
        if _supports_white_channels(bulb):
            bulb.setRgbw(r, g, b, 0, brightness=brightness, w2=0)
            return
        bulb.set_effect(_nearest_strobe_effect((r, g, b)), speed=60, brightness=_effect_brightness(brightness))

    async def _query_bulb(self) -> WifiLedBulb:
        bulb = self._make_bulb()
        await self._run_blocking(bulb.query_state)
        return bulb

    def _make_bulb(self) -> WifiLedBulb:
        ip_address = self._ip_address()
        return WifiLedBulb(ip_address)

    def _ip_address(self) -> str:
        ip_address = self.config.get("ip_address") or self.config.get("host")
        if not isinstance(ip_address, str) or not ip_address.strip():
            raise RuntimeError("Dispositivo flux_led sin config.ip_address")
        return ip_address.strip()

    async def _run_blocking(self, fn) -> Any:
        return await asyncio.to_thread(fn)


def _brightness_to_power(brightness: Any) -> Decimal | None:
    if not isinstance(brightness, int):
        return None
    return Decimal(str(round((brightness / 255) * 100, 3)))


def _supports_white_channels(bulb: WifiLedBulb) -> bool:
    model = str(getattr(bulb, "model", "") or "").lower()
    return bool(getattr(bulb, "rgbwcapable", False)) or "rgbw" in model or "rgbcw" in model or "rgbww" in model


def _is_white_channel_bulb(bulb: WifiLedBulb) -> bool:
    model = str(getattr(bulb, "model", "") or "").lower()
    return _supports_white_channels(bulb) and "bulb" in model


def _effect_brightness(brightness: int | None) -> int:
    if brightness is None:
        return 100
    return max(1, min(100, round((brightness / 255) * 100)))


def _nearest_strobe_effect(rgb: tuple[int, int, int]) -> str:
    effects = {
        "green_strobe": (34, 197, 94),
        "yellow_strobe": (245, 158, 11),
        "red_strobe": (239, 68, 68),
        "blue_strobe": (59, 130, 246),
        "purple_strobe": (168, 85, 247),
        "cyan_strobe": (6, 182, 212),
        "white_strobe": (255, 255, 255),
    }
    return min(effects, key=lambda name: _rgb_distance(rgb, effects[name]))


def _rgb_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum((left[index] - right[index]) ** 2 for index in range(3))
