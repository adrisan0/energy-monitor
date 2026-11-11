from __future__ import annotations

import httpx

from .errors import ApiError


class LegacyLocalDaikin:
    """Read-only client for legacy Daikin LAN adapters exposing documented endpoints."""

    def __init__(self, host: str, *, timeout: float = 2.0):
        self.base_url = f"http://{host.strip().strip('/')}/"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_basic_info(self) -> dict[str, str]:
        return await self._get_form("common/basic_info")

    async def get_control_info(self) -> dict[str, str]:
        return await self._get_form("aircon/get_control_info")

    async def _get_form(self, path: str) -> dict[str, str]:
        try:
            response = await self._client.get(self.base_url + path)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(f"No se pudo leer el adaptador local ({type(exc).__name__}).") from exc
        result: dict[str, str] = {}
        for pair in response.text.strip().split(","):
            if "=" in pair:
                key, value = pair.split("=", 1); result[key] = value
        if not result:
            raise ApiError("La respuesta local no tiene el formato esperado; se omite interpretación.")
        return result
