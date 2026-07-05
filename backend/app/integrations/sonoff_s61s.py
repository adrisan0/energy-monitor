from __future__ import annotations

import asyncio
import contextlib
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pysonofflanr3 import SonoffSwitch

from app.integrations.base import DeviceAdapter, DeviceState


class SonoffS61SAdapter(DeviceAdapter):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def get_state(self) -> DeviceState:
        snapshot = await asyncio.to_thread(self._run_session, "state")
        return DeviceState(
            online=snapshot["online"],
            is_on=snapshot["is_on"],
            power_w=_power_from_basic_info(snapshot["basic_info"]),
            raw=snapshot["basic_info"],
        )

    async def turn_on(self) -> None:
        await asyncio.to_thread(self._run_session, "on")

    async def turn_off(self) -> None:
        await asyncio.to_thread(self._run_session, "off")

    async def get_power(self) -> Decimal | None:
        state = await self.get_state()
        return state.power_w

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        del r, g, b, brightness
        raise RuntimeError("El adaptador sonoff_s61s no soporta control RGB")

    def _run_session(self, action: Literal["state", "on", "off"]) -> dict[str, Any]:
        host = self._required_str("ip_address", fallback_keys=("host",))
        device_id = self._optional_str("device_id")
        api_key = self._optional_str("api_key")
        timeout = self._timeout_seconds()
        result: dict[str, Any] = {
            "online": False,
            "is_on": None,
            "basic_info": {"host": host, "device_id": device_id, "needs_api_key": api_key is None},
        }
        command_sent = False
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        done = asyncio.Event()

        async def callback(device: SonoffSwitch | None) -> None:
            nonlocal command_sent
            if device is None:
                if not done.is_set():
                    done.set()
                return

            basic_info = dict(device.basic_info or {})
            basic_info.setdefault("host", host)
            basic_info.setdefault("device_id", device_id)
            result["basic_info"] = basic_info
            result["online"] = bool(device.available)
            result["is_on"] = bool(device.is_on)

            if action == "state":
                done.set()
                return

            desired_is_on = action == "on"
            if result["is_on"] == desired_is_on:
                done.set()
                return

            if not command_sent:
                command_sent = True
                if desired_is_on:
                    await device.turn_on()
                else:
                    await device.turn_off()

        switch = SonoffSwitch(
            host=host,
            callback_after_update=callback,
            logger=self.logger,
            loop=loop,
            device_id=device_id,
            api_key=api_key,
            timeout=timeout,
        )

        try:
            loop.run_until_complete(asyncio.wait_for(done.wait(), timeout + 1))
        except TimeoutError as exc:
            raise RuntimeError(
                "No se pudo comunicar con el Sonoff por LAN mode. "
                "Comprueba device_id/api_key o que el dispositivo anuncie _ewelink._tcp.local."
            ) from exc
        finally:
            switch.shutdown_event_loop()
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                with contextlib.suppress(Exception):
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

        return result

    def _timeout_seconds(self) -> int:
        value = self.config.get("timeout_seconds")
        if isinstance(value, int) and value > 0:
            return value
        return 6

    def _required_str(self, key: str, *, fallback_keys: tuple[str, ...] = ()) -> str:
        for candidate in (key, *fallback_keys):
            value = self.config.get(candidate)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise RuntimeError(f"Dispositivo sonoff_s61s sin config.{key}")

    def _optional_str(self, key: str) -> str | None:
        value = self.config.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()


def _power_from_basic_info(basic_info: dict[str, Any]) -> Decimal | None:
    params = basic_info.get("data")
    if isinstance(params, dict):
        for key in ("power", "currentPower", "actPow"):
            value = _to_decimal(params.get(key))
            if value is not None:
                return value
    for key in ("power", "currentPower", "actPow"):
        value = _to_decimal(basic_info.get(key))
        if value is not None:
            return value
    return None


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "unknown", "unavailable"):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
