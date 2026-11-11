from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.timezone import utc_now
from app.models import DaikinReading

logger = get_logger(__name__)


class DaikinCloudReader:
    """Read ONECTA climate and consumption data and persist token rotation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_base = self.settings.daikin_api_base_url.rstrip("/")
        self.token_url = self.settings.daikin_token_url
        self._refresh_token = self._load_refresh_token()
        self._access_token: str | None = None
        self._expires_at = 0.0
        self._last_request_at = 0.0
        self._client = httpx.AsyncClient(timeout=self.settings.daikin_timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    def _load_refresh_token(self) -> str:
        path = Path(self.settings.daikin_token_file)
        if path.is_file():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and cached.get("refresh_token"):
                    return str(cached["refresh_token"])
            except (OSError, ValueError):
                logger.warning("daikin_token_store_unreadable")
        return self.settings.daikin_refresh_token or ""

    def _save_refresh_token(self) -> None:
        if not self._refresh_token:
            return
        path = Path(self.settings.daikin_token_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="daikin-token-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"refresh_token": self._refresh_token}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    async def _request(self, method: str, url: str, *, authenticated: bool = True, **kwargs: Any) -> httpx.Response:
        if authenticated:
            await self._authenticate()
            kwargs.setdefault("headers", {})["Authorization"] = f"Bearer {self._access_token}"
        delay = self.settings.daikin_min_request_interval_seconds - (time.monotonic() - self._last_request_at)
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError:
            # HTTPX request exceptions can include the token URL and its query.
            raise RuntimeError("No se pudo conectar con ONECTA.") from None
        self._last_request_at = time.monotonic()
        if response.status_code == 429:
            raise RuntimeError("ONECTA ha limitado temporalmente las consultas (HTTP 429).")
        if response.status_code in (401, 403):
            raise RuntimeError(f"ONECTA rechazó la autenticación (HTTP {response.status_code}).")
        if response.is_error:
            raise RuntimeError(f"ONECTA devolvió HTTP {response.status_code}.")
        return response

    async def _authenticate(self) -> None:
        if self._access_token and time.monotonic() < self._expires_at - 30:
            return
        if not self.settings.daikin_client_id or not self.settings.daikin_client_secret or not self._refresh_token:
            raise RuntimeError("Faltan credenciales ONECTA para iniciar las lecturas Daikin.")
        response = await self._request(
            "POST",
            self.token_url,
            authenticated=False,
            params={
                "grant_type": "refresh_token",
                "client_id": self.settings.daikin_client_id,
                "client_secret": self.settings.daikin_client_secret,
                "refresh_token": self._refresh_token,
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("ONECTA devolvió una respuesta de autenticación inválida.") from exc
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise RuntimeError("ONECTA no devolvió un token de acceso.")
        self._access_token = str(payload["access_token"])
        self._expires_at = time.monotonic() + float(payload.get("expires_in", 300))
        if payload.get("refresh_token"):
            self._refresh_token = str(payload["refresh_token"])
            self._save_refresh_token()

    async def _json(self, url: str) -> Any:
        response = await self._request("GET", url)
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("ONECTA devolvió datos JSON inválidos.") from exc

    async def poll(self, db: Session) -> int:
        listing = await self._json(f"{self.api_base}/gateway-devices")
        devices = _list_rows(listing)
        captured_at = utc_now()
        rows: list[DaikinReading] = []
        for index, device in enumerate(devices, start=1):
            device_id = device.get("gatewayDeviceId", device.get("id"))
            if not device_id:
                continue
            detail = await self._json(f"{self.api_base}/gateway-devices/{quote(str(device_id), safe='')}")
            if not isinstance(detail, dict):
                continue
            rows.append(_reading(device, detail, str(device_id), index, captured_at))
        if rows:
            db.add_all(rows)
            db.commit()
        return len(rows)

def _list_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "gatewayDevices", "devices", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("ONECTA devolvió una lista de equipos con formato no reconocido.")


def _value(value: Any) -> Any:
    while isinstance(value, dict) and "value" in value:
        value = value["value"]
    return value


def _number(value: Any) -> Decimal | None:
    value = _value(value)
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _sum_profile(mode_data: Any, period: str) -> Decimal | None:
    if not isinstance(mode_data, dict):
        return None
    values = _value(mode_data.get(period))
    if not isinstance(values, list):
        return None
    parsed = [_number(value) for value in values]
    numbers = [value for value in parsed if value is not None]
    return sum(numbers, Decimal("0")) if numbers else None


def _profile_values(mode_data: Any, period: str) -> list[float]:
    values = _value(mode_data.get(period)) if isinstance(mode_data, dict) else None
    if not isinstance(values, list):
        return []
    return [float(number) if (number := _number(value)) is not None else 0.0 for value in values]


def _bool_state(points: dict[str, Any], point_type: str, characteristic: str) -> bool | None:
    point = points.get(point_type, {})
    if not isinstance(point, dict):
        return None
    value = _value(point.get(characteristic))
    return value if isinstance(value, bool) else None


def _reading(device: dict[str, Any], detail: dict[str, Any], device_id: str, index: int, captured_at: Any) -> DaikinReading:
    management_points = detail.get("managementPoints", detail.get("mananagementPoints", []))
    points = {
        str(point.get("managementPointType")): point
        for point in management_points
        if isinstance(point, dict) and point.get("managementPointType")
    } if isinstance(management_points, list) else {}
    climate = points.get("climateControl", {})
    if not isinstance(climate, dict):
        climate = {}
    mode = _value(climate.get("operationMode"))
    sensory = _value(climate.get("sensoryData"))
    if not isinstance(sensory, dict):
        sensory = {}
    temperature_control = _value(climate.get("temperatureControl"))
    modes = temperature_control.get("operationModes", {}) if isinstance(temperature_control, dict) else {}
    active_mode = modes.get(mode, {}) if isinstance(modes, dict) and mode else {}
    setpoints = active_mode.get("setpoints", {}) if isinstance(active_mode, dict) else {}
    energy = _value(climate.get("consumptionData"))
    electrical = energy.get("electrical", {}) if isinstance(energy, dict) else {}
    heating = electrical.get("heating", {}) if isinstance(electrical, dict) else {}
    cooling = electrical.get("cooling", {}) if isinstance(electrical, dict) else {}
    fan_control = _value(climate.get("fanControl"))
    climate_modes = climate.get("operationModes", {})
    active_climate_mode = climate_modes.get(mode, {}) if isinstance(climate_modes, dict) and mode else {}
    fan_modes = active_climate_mode.get("fanSpeed", {}) if isinstance(active_climate_mode, dict) else {}
    fan_mode = _value(fan_modes.get("currentMode")) if isinstance(fan_modes, dict) else None
    if fan_mode is None and isinstance(fan_control, dict):
        fan_mode = _value(fan_control.get("currentMode"))
    is_on_raw = _value(climate.get("onOffMode"))
    is_on = str(is_on_raw).lower() == "on" if is_on_raw is not None else None
    profiles: dict[str, Any] = {}
    for label, key in (("day", "d"), ("week", "w"), ("month", "m")):
        profiles[label] = {
            "unit": _value(electrical.get("unit")) if isinstance(electrical, dict) else "kWh",
            "heating_kwh": _profile_values(heating, key),
            "cooling_kwh": _profile_values(cooling, key),
            "heating_total_kwh": float(_sum_profile(heating, key) or 0),
            "cooling_total_kwh": float(_sum_profile(cooling, key) or 0),
        }
    device_name = next(
        (str(device[key]) for key in ("name", "gatewayDeviceName", "deviceName", "displayName") if device.get(key)),
        f"Aire Daikin {index}",
    )
    model = next((str(device[key]) for key in ("modelName", "deviceModel", "model") if device.get(key)), None)
    return DaikinReading(
        captured_at_utc=captured_at,
        device_id=device_id,
        device_name=device_name,
        model=model,
        is_on=is_on,
        operating_mode=str(mode) if mode is not None else None,
        fan_mode=str(fan_mode) if fan_mode is not None else None,
        room_temperature_c=_number(sensory.get("roomTemperature")),
        outdoor_temperature_c=_number(sensory.get("outdoorTemperature")),
        target_temperature_c=_number(setpoints.get("roomTemperature") if isinstance(setpoints, dict) else None),
        heating_today_kwh=_sum_profile(heating, "d"),
        cooling_today_kwh=_sum_profile(cooling, "d"),
        energy_profiles=profiles,
        in_error_state=_bool_state(points, "gateway", "isInErrorState"),
        in_warning_state=_bool_state(points, "gateway", "isInWarningState"),
    )
