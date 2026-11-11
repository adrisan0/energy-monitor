"""Read and summarize ONECTA devices using the DPAPI credential store."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from oauth_callback import API_BASE, TOKEN_URL, data_dir, save_tokens, unprotect


def _rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "gatewayDevices", "devices", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("La respuesta de /gateway-devices no tiene el formato documentado.")


def _value(raw: object) -> object:
    return raw.get("value") if isinstance(raw, dict) and "value" in raw else raw


def _summary(device: dict[str, object], detail: dict[str, object], index: int) -> dict[str, object]:
    name = next((device.get(key) for key in ("name", "gatewayDeviceName", "deviceName", "displayName")
                 if device.get(key)), f"Daikin {index}")
    model = next((device.get(key) for key in ("modelName", "deviceModel", "model") if device.get(key)), None)
    points = detail.get("managementPoints", detail.get("mananagementPoints", []))
    if not isinstance(points, list):
        points = []
    climate = next((p for p in points if isinstance(p, dict)
                    and p.get("managementPointType") == "climateControl"), {})
    result: dict[str, object] = {
        "name": name,
        "model": model,
        "management_points": [p.get("managementPointType") for p in points if isinstance(p, dict)],
    }
    mode = _value(climate.get("operationMode")) if isinstance(climate, dict) else None
    power = _value(climate.get("onOffMode")) if isinstance(climate, dict) else None
    if mode is not None:
        result["operating_mode"] = mode
    if power is not None:
        result["is_on"] = str(power).lower() == "on"
    if isinstance(climate, dict):
        sensory = _value(climate.get("sensoryData"))
        if isinstance(sensory, dict):
            room = _value(sensory.get("roomTemperature"))
            if room is not None:
                result["room_temperature"] = room
        controls = _value(climate.get("temperatureControl"))
        modes = controls.get("operationModes", {}) if isinstance(controls, dict) else {}
        active = modes.get(mode, {}) if isinstance(modes, dict) and mode is not None else {}
        setpoints = active.get("setpoints", {}) if isinstance(active, dict) else {}
        target = _value(setpoints.get("roomTemperature")) if isinstance(setpoints, dict) else None
        if target is not None:
            result["temperature_setpoint"] = target
    return result


def main() -> int:
    store = data_dir() / "credentials.dpapi"
    if not store.is_file():
        print("No existe el almacén DPAPI. Completa antes el flujo OAuth.", file=sys.stderr)
        return 2
    try:
        credentials = json.loads(unprotect(store.read_bytes()))
        required = ("client_id", "client_secret", "refresh_token")
        if any(not credentials.get(key) for key in required):
            raise RuntimeError("El almacén DPAPI no contiene todas las credenciales necesarias.")
        params = {
            "grant_type": "refresh_token",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "refresh_token": credentials["refresh_token"],
        }
        with httpx.Client(timeout=15.0) as client:
            refreshed = client.post(TOKEN_URL, params=params)
        if refreshed.is_error:
            raise RuntimeError(f"ONECTA refresh devolvió HTTP {refreshed.status_code}.")
        token_payload = refreshed.json()
        if not isinstance(token_payload, dict) or not token_payload.get("access_token"):
            raise RuntimeError("ONECTA no devolvió un access token al renovar.")
        token_payload.setdefault("refresh_token", credentials["refresh_token"])
        cfg = {
            "DAIKIN_CLIENT_ID": credentials["client_id"],
            "DAIKIN_CLIENT_SECRET": credentials["client_secret"],
            "DAIKIN_REDIRECT_URI": credentials.get("redirect_uri", ""),
        }
        # Refresh tokens rotate. Save the new token before any device requests.
        save_tokens(cfg, token_payload)

        headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
        with httpx.Client(timeout=15.0) as client:
            listing = client.get(f"{API_BASE}/gateway-devices", headers=headers)
            if listing.is_error:
                raise RuntimeError(f"ONECTA device listing devolvió HTTP {listing.status_code}.")
            devices = _rows(listing.json())
            summaries = []
            for index, device in enumerate(devices, start=1):
                device_id = device.get("gatewayDeviceId", device.get("id"))
                if not device_id:
                    summaries.append({"name": f"Daikin {index}", "detail": "sin identificador"})
                    continue
                time.sleep(1.0)
                detail_response = client.get(
                    f"{API_BASE}/gateway-devices/{quote(str(device_id), safe='')}", headers=headers
                )
                if detail_response.is_error:
                    summaries.append({"name": f"Daikin {index}",
                                      "detail_http_status": detail_response.status_code})
                    continue
                detail = detail_response.json()
                if not isinstance(detail, dict):
                    summaries.append({"name": f"Daikin {index}", "detail": "respuesta no reconocida"})
                    continue
                summaries.append(_summary(device, detail, index))
        print(json.dumps({"connected": True, "device_count": len(devices), "devices": summaries},
                         ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        # Exception messages omit response bodies and credentials by design.
        print(f"Diagnóstico ONECTA fallido: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
