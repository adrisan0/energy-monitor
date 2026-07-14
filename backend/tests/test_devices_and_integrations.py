from __future__ import annotations

from decimal import Decimal
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.integrations.base import DeviceState
from app.main import app
from app.db.session import get_session_factory
from app.integrations.factory import adapter_for_device
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload


class FakeAdapter:
    def __init__(self) -> None:
        self.last_rgb = None

    async def get_state(self) -> DeviceState:
        return DeviceState(online=True, is_on=True, power_w=Decimal("123.4"), raw={"source": "fake"})

    async def turn_on(self) -> None:
        return None

    async def turn_off(self) -> None:
        return None

    async def get_power(self) -> Decimal | None:
        return Decimal("123.4")

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        self.last_rgb = (r, g, b, brightness)


def test_device_state_route(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes, "adapter_for_device", lambda device: FakeAdapter())
    with TestClient(app) as client:
        response = client.get("/api/v1/devices/3/state")
        assert response.status_code == 200
        body = response.json()
        assert body["online"] is True
        assert body["is_on"] is True
        assert body["power_w"] == 123.4


def test_device_turn_on_route_requires_token(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes, "adapter_for_device", lambda device: FakeAdapter())
    with TestClient(app) as client:
        unauthorized = client.post("/api/v1/devices/3/on")
        assert unauthorized.status_code == 401
        authorized = client.post("/api/v1/devices/3/on", headers={"X-Admin-Token": "test-token"})
        assert authorized.status_code == 200
        assert authorized.json()["message"] == "Dispositivo encendido"


def test_device_turn_off_route_returns_503_when_device_unreachable(monkeypatch) -> None:
    from app.api import routes

    class TimeoutAdapter(FakeAdapter):
        async def turn_off(self) -> None:
            raise TimeoutError("timed out")

    monkeypatch.setattr(routes, "adapter_for_device", lambda device: TimeoutAdapter())
    with TestClient(app) as client:
        response = client.post("/api/v1/devices/5/off", headers={"X-Admin-Token": "test-token"})
        assert response.status_code == 503
        assert "No se pudo comunicar" in response.json()["detail"]


def test_device_set_color_route(monkeypatch) -> None:
    from app.api import routes

    adapter = FakeAdapter()
    monkeypatch.setattr(routes, "adapter_for_device", lambda device: adapter)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices/3/color",
            headers={"X-Admin-Token": "test-token"},
            json={"rgb": [10, 20, 30], "brightness": 120},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Color aplicado"
        assert adapter.last_rgb == (10, 20, 30, 120)


def test_device_set_color_route_accepts_stringified_json_body(monkeypatch) -> None:
    from app.api import routes

    adapter = FakeAdapter()
    monkeypatch.setattr(routes, "adapter_for_device", lambda device: adapter)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices/3/color",
            headers={"X-Admin-Token": "test-token", "Content-Type": "application/json"},
            content='{"rgb":[155,0,158],"brightness":17}',
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Color aplicado"
        assert adapter.last_rgb == (155, 0, 158, 17)


def test_device_set_color_route_accepts_bytes_json_body(monkeypatch) -> None:
    from app.api import routes

    adapter = FakeAdapter()
    monkeypatch.setattr(routes, "adapter_for_device", lambda device: adapter)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices/3/color",
            headers={"X-Admin-Token": "test-token", "Content-Type": "application/octet-stream"},
            content=b'{"rgb":[1,2,3],"brightness":4}',
        )
        assert response.status_code == 200
        assert adapter.last_rgb == (1, 2, 3, 4)


def test_device_set_mode_route() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices/3/mode",
            headers={"X-Admin-Token": "test-token"},
            json={"mode": "automatic"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Modo automatic aplicado"


def test_device_set_mode_route_accepts_stringified_json_body() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices/3/mode",
            headers={"X-Admin-Token": "test-token", "Content-Type": "application/json"},
            content='{"mode":"manual"}',
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Modo manual aplicado"


def test_device_set_mode_route_accepts_bytes_json_body() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices/3/mode",
            headers={"X-Admin-Token": "test-token", "Content-Type": "application/octet-stream"},
            content=b'{"mode":"manual"}',
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Modo manual aplicado"


def test_device_patch_route_updates_config() -> None:
    with TestClient(app) as client:
        response = client.patch(
            "/api/v1/devices/3",
            headers={"X-Admin-Token": "test-token"},
            json={
                "status": "active",
                "control_mode": "home_assistant",
                "config": {
                    "adapter": "home_assistant",
                    "entity_id": "switch.termo_padres",
                    "power_entity_id": "sensor.termo_padres_power",
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "active"
        assert body["control_mode"] == "home_assistant"
        assert body["config"]["entity_id"] == "switch.termo_padres"


def test_device_patch_route_accepts_stringified_json_body() -> None:
    with TestClient(app) as client:
        response = client.patch(
            "/api/v1/devices/6",
            headers={"X-Admin-Token": "test-token", "Content-Type": "application/json"},
            content='{"config":{"adapter":"flux_led","ip_address":"192.168.1.29","automation":{"enabled":true,"profile":"consumption_gradient","metric":"house_consumption_w","surplus_override":true,"thresholds":{"low_max_w":350,"medium_max_w":1650,"high_max_w":2800},"colors":{"low":"#22C55E","medium":"#F59E0B","high":"#EF4444","super":"#3B82F6"},"brightness":{"low":255,"medium":255,"high":255,"super":180}}},"control_mode":"automatic"}',
        )
        assert response.status_code == 200
        body = response.json()
        assert body["control_mode"] == "automatic"
        assert body["config"]["automation"]["profile"] == "consumption_gradient"


def test_device_patch_route_accepts_bytes_json_body() -> None:
    with TestClient(app) as client:
        response = client.patch(
            "/api/v1/devices/6",
            headers={"X-Admin-Token": "test-token", "Content-Type": "application/octet-stream"},
            content=b'{"config":{"adapter":"flux_led","ip_address":"192.168.1.29"},"control_mode":"manual"}',
        )
        assert response.status_code == 200
        body = response.json()
        assert body["control_mode"] == "manual"
        assert body["config"]["ip_address"] == "192.168.1.29"


def test_device_apply_automation_route_forces_preview(monkeypatch) -> None:
    from app.api import routes

    class FakeTarget:
        tier = "medium"

    async def fake_apply(db, device, sample, *, force=False):
        assert force is True
        return FakeTarget()

    monkeypatch.setattr(routes, "apply_automation_to_device", fake_apply)
    with get_session_factory()() as db:
        parsed = parse_meter_xml(
            """
            <root>
              <variable><id>pac1</id><value>250</value></variable>
              <variable><id>pac2</id><value>0</value></variable>
              <variable><id>fpot1</id><value>1.000</value></variable>
            </root>
            """,
            timestamp_utc=datetime(2026, 7, 4, 10, 0, tzinfo=UTC),
        )
        store_parsed_payload(db, parsed, poll_duration_ms=2)
        db.commit()
    with TestClient(app) as client:
        response = client.post("/api/v1/devices/4/apply-automation", headers={"X-Admin-Token": "test-token"})
        assert response.status_code == 200
        assert response.json()["message"] == "Automatizacion aplicada: medium"


def test_device_apply_automation_route_returns_503_when_device_unreachable(monkeypatch) -> None:
    from app.api import routes

    async def fake_apply(db, device, sample, *, force=False):
        assert force is True
        raise OSError("No route to host")

    monkeypatch.setattr(routes, "apply_automation_to_device", fake_apply)
    with get_session_factory()() as db:
        parsed = parse_meter_xml(
            """
            <root>
              <variable><id>pac1</id><value>100</value></variable>
              <variable><id>pac2</id><value>500</value></variable>
              <variable><id>fpot1</id><value>1.000</value></variable>
            </root>
            """,
            timestamp_utc=datetime(2026, 7, 4, 10, 1, tzinfo=UTC),
        )
        store_parsed_payload(db, parsed, poll_duration_ms=2)
        db.commit()
    with TestClient(app) as client:
        response = client.post("/api/v1/devices/4/apply-automation", headers={"X-Admin-Token": "test-token"})
        assert response.status_code == 503
        assert "No se pudo comunicar" in response.json()["detail"]


def test_adapter_for_device_supports_kasa_hs100() -> None:
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 2)
        assert device is not None
        device.ip_address = "192.168.1.50"
        device.config = {"adapter": "kasa_hs100"}
        adapter = adapter_for_device(device)

        assert adapter.__class__.__name__ == "KasaHs100Adapter"
        assert adapter.config["ip_address"] == "192.168.1.50"


def test_adapter_for_device_supports_sonoff_s61s() -> None:
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 1)
        assert device is not None
        device.ip_address = "192.168.1.54"
        device.config = {"adapter": "sonoff_s61s"}
        adapter = adapter_for_device(device)

        assert adapter.__class__.__name__ == "SonoffS61SAdapter"
        assert adapter.config["ip_address"] == "192.168.1.54"


def test_kasa_hs100_adapter_reports_state_and_power(monkeypatch) -> None:
    from app.integrations.kasa_hs100 import KasaHs100Adapter

    class FakePlug:
        alias = "HS100 salon"
        model = "HS100"
        is_on = True
        has_emeter = True
        emeter_realtime = {"power": 42.5}

    async def fake_discover_single(host, **kwargs):
        assert host == "192.168.1.50"
        assert kwargs == {}
        return FakePlug()

    monkeypatch.setattr("app.integrations.kasa_hs100.Discover.discover_single", fake_discover_single)
    adapter = KasaHs100Adapter({"ip_address": "192.168.1.50"})
    state = __import__("asyncio").run(adapter.get_state())

    assert state.online is True
    assert state.is_on is True
    assert state.power_w == Decimal("42.5")
    assert state.raw["alias"] == "HS100 salon"


def test_kasa_hs100_adapter_passes_optional_credentials(monkeypatch) -> None:
    from app.integrations.kasa_hs100 import KasaHs100Adapter

    class FakePlug:
        alias = "HS100 cocina"
        model = "HS100"
        is_on = False
        has_emeter = False

    async def fake_discover_single(host, **kwargs):
        assert host == "192.168.1.51"
        assert kwargs == {"username": "user@example.com", "password": "secret"}
        return FakePlug()

    monkeypatch.setattr("app.integrations.kasa_hs100.Discover.discover_single", fake_discover_single)
    adapter = KasaHs100Adapter({"ip_address": "192.168.1.51", "username": "user@example.com", "password": "secret"})
    state = __import__("asyncio").run(adapter.get_state())

    assert state.online is True
    assert state.is_on is False


def test_sonoff_s61s_adapter_reports_state_and_power(monkeypatch) -> None:
    from app.integrations.sonoff_s61s import SonoffS61SAdapter

    class FakeSwitch:
        def __init__(self, host, callback_after_update, logger, loop, device_id=None, api_key=None, timeout=6):
            del logger, api_key, timeout
            self.host = host
            self.available = True
            self.is_on = True
            self.basic_info = {"data": {"power": "87.4"}, "deviceid": device_id or "abc123"}
            self._loop = loop
            self._callback = callback_after_update
            loop.call_soon(loop.create_task, callback_after_update(self))

        async def turn_on(self):
            self.is_on = True
            await self._callback(self)

        async def turn_off(self):
            self.is_on = False
            await self._callback(self)

        def shutdown_event_loop(self):
            return None

    monkeypatch.setattr("app.integrations.sonoff_s61s.SonoffSwitch", FakeSwitch)
    adapter = SonoffS61SAdapter({"ip_address": "192.168.1.54", "device_id": "abc123", "api_key": "secret"})
    state = __import__("asyncio").run(adapter.get_state())

    assert state.online is True
    assert state.is_on is True
    assert state.power_w == Decimal("87.4")


def test_sonoff_s61s_adapter_turns_off(monkeypatch) -> None:
    from app.integrations.sonoff_s61s import SonoffS61SAdapter

    class FakeSwitch:
        def __init__(self, host, callback_after_update, logger, loop, device_id=None, api_key=None, timeout=6):
            del host, logger, device_id, api_key, timeout
            self.available = True
            self.is_on = True
            self.basic_info = {"data": {}, "deviceid": "abc123"}
            self._loop = loop
            self._callback = callback_after_update
            loop.call_soon(loop.create_task, callback_after_update(self))

        async def turn_on(self):
            self.is_on = True
            await self._callback(self)

        async def turn_off(self):
            self.is_on = False
            await self._callback(self)

        def shutdown_event_loop(self):
            return None

    monkeypatch.setattr("app.integrations.sonoff_s61s.SonoffSwitch", FakeSwitch)
    adapter = SonoffS61SAdapter({"ip_address": "192.168.1.54", "device_id": "abc123", "api_key": "secret"})
    __import__("asyncio").run(adapter.turn_off())
