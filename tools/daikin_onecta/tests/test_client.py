import asyncio

import httpx
import pytest

from daikin_onecta.client import DaikinClient
from daikin_onecta.errors import ConfigurationError


def test_missing_oauth_material_fails_without_network():
    async def handler(request):
        raise AssertionError("No request expected")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DaikinClient(api_base_url="https://example.invalid", token_url="https://example.invalid/token",
                          client_id="demo", client=http)
    async def run():
        with pytest.raises(ConfigurationError):
            await client.authenticate()
        await http.aclose()
    asyncio.run(run())


def test_official_paths_are_required_before_listing():
    async def handler(request):
        return httpx.Response(200, json={"access_token":"test","expires_in":600})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DaikinClient(api_base_url="https://example.invalid", token_url="https://example.invalid/token",
                          client_id="demo", authorization_code="code", redirect_uri="https://example.invalid/cb",
                          client=http, min_request_interval=0)
    async def run():
        with pytest.raises(ConfigurationError):
            await client.list_devices()
        await http.aclose()
    asyncio.run(run())


def test_characteristic_payload_matches_documented_reading_shape():
    async def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "test", "expires_in": 3600})
        assert request.method == "PATCH"
        assert request.url.path.endswith("/characteristics/onOffMode")
        assert request.read() == b'{"value":"off"}'
        return httpx.Response(204)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DaikinClient(api_base_url="https://example.invalid", token_url="https://example.invalid/token",
                          client_id="demo", authorization_code="code", redirect_uri="https://example.invalid/cb",
                          client=http, min_request_interval=0)
    async def run():
        await client.turn_off("gateway", "climateControl")
        await http.aclose()
    asyncio.run(run())
