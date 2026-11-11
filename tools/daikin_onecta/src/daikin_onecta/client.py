from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

from .errors import ApiError, AuthenticationError, ConfigurationError, RateLimitError
from .models import DaikinDevice, DeviceStatus


class DaikinClient:
    """Small cloud client driven by endpoint paths from the authenticated portal.

    ONECTA Cloud paths and OAuth details are intentionally configuration values;
    no private or undocumented endpoint is assumed by this package.
    """

    def __init__(self, *, api_base_url: str, token_url: str, client_id: str,
                 client_secret: str | None = None, redirect_uri: str | None = None,
                 scopes: str | None = None, authorization_code: str | None = None,
                 refresh_token: str | None = None, devices_path: str | None = None,
                 status_path_template: str | None = None, timeout: float = 10.0,
                 min_request_interval: float = 1.0, max_retries: int = 2,
                 client: httpx.AsyncClient | None = None):
        self.api_base_url = api_base_url.rstrip("/")
        self.token_url, self.client_id = token_url, client_id
        self.client_secret, self.redirect_uri, self.scopes = client_secret, redirect_uri, scopes
        self.authorization_code, self.refresh_token = authorization_code, refresh_token
        self.devices_path, self.status_path_template = devices_path, status_path_template
        self.timeout, self.min_request_interval, self.max_retries = timeout, min_request_interval, max_retries
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._last_request_at = 0.0
        self._lock = asyncio.Lock()

    def authorization_url(self, *, state: str | None = None, use_offline_access: bool = True) -> tuple[str, str]:
        """Build the documented OIDC authorization URL and return (url, state)."""
        if not self.client_id or not self.redirect_uri:
            raise ConfigurationError("Se requieren client ID y redirect URI registrados en My Apps.")
        state = state or secrets.token_urlsafe(32)
        scopes = "openid onecta:basic.integration"
        if use_offline_access:
            scopes += " offline_access"
        query = urlencode({"response_type": "code", "client_id": self.client_id,
                           "redirect_uri": self.redirect_uri, "scope": scopes, "state": state})
        return f"https://idp.onecta.daikineurope.com/v1/oidc/authorize?{query}", state

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "DaikinClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def authenticate(self) -> None:
        if self._access_token and time.monotonic() < self._expires_at - 30:
            return
        if not self.token_url or not self.client_id:
            raise ConfigurationError("Completa token URL y client ID según la documentación privada del portal ONECTA.")
        if self.refresh_token:
            data: dict[str, str] = {"grant_type": "refresh_token", "refresh_token": self.refresh_token, "client_id": self.client_id}
        elif self.authorization_code and self.redirect_uri:
            data = {"grant_type": "authorization_code", "code": self.authorization_code,
                    "redirect_uri": self.redirect_uri, "client_id": self.client_id}
        else:
            raise ConfigurationError("Se requiere un authorization code obtenido mediante OAuth o un refresh token.")
        if self.client_secret:
            data["client_secret"] = self.client_secret
        # Daikin's portal examples send token parameters in the POST query string.
        response = await self._request("POST", self.token_url, params=data, authenticated=False)
        payload = self._json(response)
        token = payload.get("access_token")
        if not token:
            raise AuthenticationError("La respuesta OAuth no incluyó access_token.")
        self._access_token = str(token)
        self.refresh_token = payload.get("refresh_token", self.refresh_token)
        self._expires_at = time.monotonic() + float(payload.get("expires_in", 300))

    async def _request(self, method: str, url: str, *, authenticated: bool = True, **kwargs: Any) -> httpx.Response:
        if authenticated:
            await self.authenticate()
            kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {self._access_token}"
        for attempt in range(self.max_retries + 1):
            async with self._lock:
                delay = self.min_request_interval - (time.monotonic() - self._last_request_at)
                if delay > 0:
                    await asyncio.sleep(delay)
                try:
                    response = await self._client.request(method, url, **kwargs)
                except httpx.TimeoutException as exc:
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.25 * (attempt + 1)); continue
                    raise ApiError("Timeout al conectar con ONECTA.") from exc
                self._last_request_at = time.monotonic()
            if response.status_code == 429:
                if attempt < self.max_retries:
                    try: wait = min(float(response.headers.get("Retry-After", "1")), 30.0)
                    except ValueError: wait = 1.0
                    await asyncio.sleep(max(0.0, wait)); continue
                raise RateLimitError("ONECTA devolvió HTTP 429; se agotaron los reintentos limitados.")
            if response.status_code in (401, 403):
                raise AuthenticationError(f"ONECTA denegó la solicitud (HTTP {response.status_code}).")
            if response.is_error:
                raise ApiError(f"ONECTA devolvió HTTP {response.status_code}.")
            return response
        raise ApiError("Solicitud fallida tras reintentos limitados.")

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try: result = response.json()
        except ValueError as exc: raise ApiError("Respuesta JSON inválida.") from exc
        if not isinstance(result, dict): raise ApiError("La respuesta JSON debe ser un objeto.")
        return result

    async def list_devices(self) -> list[DaikinDevice]:
        if not self.devices_path:
            raise ConfigurationError("Configura DAIKIN_DEVICES_PATH desde la documentación del portal.")
        payload = self._json(await self._request("GET", urljoin(self.api_base_url + "/", self.devices_path.lstrip("/"))))
        rows: Any = payload if isinstance(payload, list) else payload.get("items", payload.get("devices", payload.get("data")))
        # The documented API returns an array; some tenants wrap it in a JSON object.
        if isinstance(rows, dict):
            rows = next((v for v in rows.values() if isinstance(v, list)), None)
        if not isinstance(rows, list): raise ApiError("No se reconoció la lista de dispositivos en la respuesta.")
        return [DaikinDevice.model_validate(row) for row in rows]

    async def get_device_status(self, device_id: str) -> DeviceStatus:
        if not self.status_path_template:
            raise ConfigurationError("Configura DAIKIN_STATUS_PATH_TEMPLATE desde la documentación del portal.")
        path = self.status_path_template.format(device_id=device_id)
        raw = self._json(await self._request("GET", urljoin(self.api_base_url + "/", path.lstrip("/"))))
        points = raw.get("managementPoints", raw.get("mananagementPoints", []))
        climate = next((p for p in points if p.get("managementPointType") == "climateControl"), {}) if isinstance(points, list) else {}
        mode = self._char_value(climate.get("operationMode"))
        sensory = climate.get("sensoryData", {})
        sensory_value = sensory.get("value", sensory) if isinstance(sensory, dict) else {}
        room = self._char_value(sensory_value.get("roomTemperature")) if isinstance(sensory_value, dict) else None
        controls = climate.get("temperatureControl", {})
        controls_value = controls.get("value", controls) if isinstance(controls, dict) else {}
        modes = controls_value.get("operationModes", {}) if isinstance(controls_value, dict) else {}
        active_mode = modes.get(mode, {}) if isinstance(modes, dict) and mode else {}
        setpoints = active_mode.get("setpoints", {}) if isinstance(active_mode, dict) else {}
        target = self._char_value(setpoints.get("roomTemperature")) if isinstance(setpoints, dict) else None
        power = self._char_value(climate.get("onOffMode"))
        return DeviceStatus(device_id=device_id, temperature_setpoint=target, room_temperature=room,
                            operating_mode=mode, is_on=(str(power).lower() == "on") if power is not None else None,
                            raw=raw)

    @staticmethod
    def _char_value(value: Any) -> Any:
        return value.get("value") if isinstance(value, dict) else value

    async def get_temperature(self, device_id: str) -> tuple[float | None, float | None]:
        status = await self.get_device_status(device_id)
        return status.temperature_setpoint, status.room_temperature

    async def get_operating_mode(self, device_id: str) -> str | None:
        return (await self.get_device_status(device_id)).operating_mode

    async def set_temperature(self, device_id: str, embedded_id: str, mode: str, temperature: float) -> None:
        """PATCH a setpoint using the documented characteristic path and schema."""
        await self.update_characteristic(device_id, embedded_id, "temperatureControl",
                                         {"path": f"/operationModes/{mode}/setpoints/roomTemperature", "value": temperature})

    async def set_operating_mode(self, device_id: str, embedded_id: str, mode: str) -> None:
        await self.update_characteristic(device_id, embedded_id, "operationMode", {"value": mode})

    async def turn_on(self, device_id: str, embedded_id: str) -> None:
        await self.update_characteristic(device_id, embedded_id, "onOffMode", {"value": "on"})

    async def turn_off(self, device_id: str, embedded_id: str) -> None:
        await self.update_characteristic(device_id, embedded_id, "onOffMode", {"value": "off"})

    async def update_characteristic(self, gateway_device_id: str, embedded_id: str, name: str,
                                    body: dict[str, Any]) -> None:
        """Execute a documented PATCH. This changes device state; never called by diagnostics."""
        path = (f"/gateway-devices/{gateway_device_id}/management-points/{embedded_id}"
                f"/characteristics/{name}")
        url = urljoin(self.api_base_url + "/", path.lstrip("/"))
        await self._request("PATCH", url, json=body)
