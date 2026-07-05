import httpx
import pytest

from app.core.config import get_settings
from app.services.meter_client import _extract_device_ids, _extract_xml_payload, _meter_request_urls
from app.services.meter_client import fetch_meter_payload


def test_meter_request_urls_prefer_values_endpoint_for_root_url() -> None:
    urls = _meter_request_urls(
        "http://192.168.1.31/",
        values_path="/services/user/values.xml",
        device_ids=["solar", "SOLAR"],
    )
    assert urls == [
        "http://192.168.1.31/services/user/values.xml?id=solar",
        "http://192.168.1.31/services/user/values.xml?id=SOLAR",
    ]


def test_meter_request_urls_include_root_only_without_known_ids() -> None:
    urls = _meter_request_urls(
        "http://192.168.1.31/",
        values_path="/services/user/values.xml",
        device_ids=[],
    )
    assert urls == [
        "http://192.168.1.31/services/user/values.xml",
        "http://192.168.1.31/",
    ]


def test_meter_request_urls_keep_explicit_endpoint() -> None:
    urls = _meter_request_urls(
        "http://192.168.1.31/custom.xml",
        values_path="/services/user/values.xml",
        device_ids=[],
    )
    assert urls == ["http://192.168.1.31/custom.xml"]


def test_extract_xml_payload_ignores_login_html() -> None:
    payload = _extract_xml_payload(
        "<!DOCTYPE html><html><body></body><script>window.location.href='/en/login.html'</script></html>"
    )
    assert payload is None


def test_extract_xml_payload_strips_wrapper_text() -> None:
    payload = _extract_xml_payload("noise before <root><variable><id>pac1</id><value>1</value></variable></root> trailing")
    assert payload == "<root><variable><id>pac1</id><value>1</value></variable></root>"


def test_extract_xml_payload_discards_empty_values() -> None:
    assert _extract_xml_payload("<values />") is None
    assert _extract_xml_payload("<?xml version='1.0' encoding='utf-8'?><values />") is None


def test_extract_device_ids_from_devices_xml() -> None:
    ids = _extract_device_ids("<devices><device><id>wibeee</id></device><device><id>meter2</id></device></devices>")
    assert ids == ["wibeee", "meter2"]


@pytest.mark.asyncio
async def test_fetch_meter_payload_retries_before_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATION_MODE", "false")
    monkeypatch.setenv("METER_URL", "http://meter/")
    monkeypatch.setenv("METER_DEVICE_ID", "WIBEEE")
    monkeypatch.setenv("METER_REQUEST_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("METER_REQUEST_ATTEMPTS", "3")
    get_settings.cache_clear()

    calls: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @property
        def text(self) -> str:
            return ""

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            calls.append(url)
            raise httpx.ReadError("boom")

    monkeypatch.setattr("app.services.meter_client.httpx.AsyncClient", lambda **kwargs: FakeClient())

    with pytest.raises(RuntimeError, match="No se pudo obtener XML del medidor"):
        await fetch_meter_payload()

    assert calls == ["http://meter/services/user/values.xml?id=WIBEEE"] * 3
