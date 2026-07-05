from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import get_settings
from app.integrations.base import DeviceAdapter, DeviceState

POWER_ATTRIBUTE_KEYS = (
    "current_power_w",
    "power",
    "power_w",
    "load_power",
    "current_consumption",
)
ON_STATES = {"on", "playing", "open", "home", "heat", "cool", "fan_only"}
OFF_STATES = {"off", "closed", "not_home", "unavailable"}


class HomeAssistantAdapter(DeviceAdapter):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def get_state(self) -> DeviceState:
        entity_id = self._entity_id()
        state_payload = await self._api_get(f"/api/states/{entity_id}")
        power = await self._power_from_state(state_payload)
        state = str(state_payload.get("state", "")).lower()
        is_on = None
        if state in ON_STATES:
            is_on = True
        elif state in OFF_STATES:
            is_on = False
        return DeviceState(online=state not in {"unavailable", "unknown", ""}, is_on=is_on, power_w=power, raw=state_payload)

    async def turn_on(self) -> None:
        await self._call_service("turn_on")

    async def turn_off(self) -> None:
        await self._call_service("turn_off")

    async def get_power(self) -> Decimal | None:
        state = await self.get_state()
        return state.power_w

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        entity_id = self._entity_id()
        domain = self._service_domain(entity_id)
        payload: dict[str, Any] = {"entity_id": entity_id, "rgb_color": [r, g, b]}
        if brightness is not None:
            payload["brightness"] = brightness
        await self._api_post(f"/api/services/{domain}/turn_on", payload)

    async def _call_service(self, service: str) -> None:
        entity_id = self._entity_id()
        domain = self._service_domain(entity_id)
        await self._api_post(f"/api/services/{domain}/{service}", {"entity_id": entity_id})

    async def _power_from_state(self, state_payload: dict[str, Any]) -> Decimal | None:
        attrs = state_payload.get("attributes", {})
        if not isinstance(attrs, dict):
            attrs = {}
        for key in POWER_ATTRIBUTE_KEYS:
            value = _to_decimal(attrs.get(key))
            if value is not None:
                return value

        power_entity_id = self.config.get("power_entity_id")
        if isinstance(power_entity_id, str) and power_entity_id.strip():
            power_state = await self._api_get(f"/api/states/{power_entity_id.strip()}")
            return _to_decimal(power_state.get("state"))
        return None

    async def _api_get(self, path: str) -> dict[str, Any]:
        settings = get_settings()
        base_url = (settings.home_assistant_base_url or "").rstrip("/")
        token = settings.home_assistant_token
        if not base_url or not token:
            raise RuntimeError("Home Assistant no configurado: faltan HOME_ASSISTANT_BASE_URL o HOME_ASSISTANT_TOKEN")

        async with httpx.AsyncClient(
            timeout=float(settings.home_assistant_timeout_seconds),
            verify=settings.home_assistant_verify_ssl,
        ) as client:
            response = await client.get(
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def _api_post(self, path: str, payload: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
        settings = get_settings()
        base_url = (settings.home_assistant_base_url or "").rstrip("/")
        token = settings.home_assistant_token
        if not base_url or not token:
            raise RuntimeError("Home Assistant no configurado: faltan HOME_ASSISTANT_BASE_URL o HOME_ASSISTANT_TOKEN")

        async with httpx.AsyncClient(
            timeout=float(settings.home_assistant_timeout_seconds),
            verify=settings.home_assistant_verify_ssl,
        ) as client:
            response = await client.post(
                f"{base_url}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def _entity_id(self) -> str:
        entity_id = self.config.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise RuntimeError("Dispositivo Home Assistant sin config.entity_id")
        return entity_id.strip()

    def _service_domain(self, entity_id: str) -> str:
        service_domain = self.config.get("service_domain")
        if isinstance(service_domain, str) and service_domain.strip():
            return service_domain.strip()
        return entity_id.split(".", 1)[0]


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, "", "unknown", "unavailable"):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
