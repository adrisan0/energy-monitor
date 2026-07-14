from __future__ import annotations

from decimal import Decimal
import pytest

from app.integrations.flux_led import FluxLedAdapter


class FakeBulb:
    def __init__(self, ip_address: str) -> None:
        self.ip_address = ip_address
        self.is_on = True
        self.brightness = 255
        self.rgb = (255, 120, 20)
        self.mode = "color"
        self.model = "Controller RGB (0x33)"
        self.color_mode = "RGB"

    def query_state(self) -> None:
        return None

    def turnOn(self) -> None:
        self.is_on = True

    def turnOff(self) -> None:
        self.is_on = False

    def setRgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        self.rgb = (r, g, b)
        if brightness is not None:
            self.brightness = brightness

    def set_effect(self, effect: str, speed: int, brightness: int = 100) -> None:
        self.effect = (effect, speed, brightness)


class FakeRgbwBulb(FakeBulb):
    def __init__(self, ip_address: str) -> None:
        super().__init__(ip_address)
        self.model = "Bulb RGBCW (0x35)"
        self.rgbwcapable = True
        self.last_rgbw = None
        self.effect = None
        self.white_active = True
        self.warm_white = 100
        self.cold_white = 80

    def setRgbw(
        self,
        r: int | None = None,
        g: int | None = None,
        b: int | None = None,
        w: int | None = None,
        persist: bool = True,
        brightness: int | None = None,
        w2: int | None = None,
        retry: int = 2,
    ) -> None:
        del persist, retry
        self.last_rgbw = (r, g, b, w, brightness, w2)
        self.rgb = (r, g, b)
        self.white_active = False
        self.warm_white = w
        self.cold_white = w2
        if brightness is not None:
            self.brightness = brightness


@pytest.mark.asyncio
async def test_flux_led_adapter_state(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.flux_led.WifiLedBulb", FakeBulb)
    adapter = FluxLedAdapter({"ip_address": "192.168.1.29"})
    state = await adapter.get_state()
    assert state.online is True
    assert state.is_on is True
    assert state.power_w == Decimal("100.0")
    assert state.raw["model"] == "Controller RGB (0x33)"


@pytest.mark.asyncio
async def test_flux_led_adapter_state_returns_offline_when_unreachable(monkeypatch) -> None:
    def factory(ip_address: str) -> FakeBulb:
        del ip_address
        raise OSError("No route to host")

    monkeypatch.setattr("app.integrations.flux_led.WifiLedBulb", factory)
    adapter = FluxLedAdapter({"ip_address": "192.168.1.29"})
    state = await adapter.get_state()
    assert state.online is False
    assert state.is_on is None
    assert state.power_w is None
    assert state.raw == {
        "error": "device_unreachable",
        "detail": "No route to host",
        "ip_address": "192.168.1.29",
    }


@pytest.mark.asyncio
async def test_flux_led_adapter_turn_off(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.flux_led.WifiLedBulb", FakeBulb)
    adapter = FluxLedAdapter({"ip_address": "192.168.1.29"})
    await adapter.turn_off()


@pytest.mark.asyncio
async def test_flux_led_adapter_set_rgb(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.flux_led.WifiLedBulb", FakeBulb)
    adapter = FluxLedAdapter({"ip_address": "192.168.1.29"})
    await adapter.set_rgb(10, 20, 30, brightness=99)


@pytest.mark.asyncio
async def test_flux_led_adapter_set_rgb_zeroes_white_channels_on_rgbw_bulb(monkeypatch) -> None:
    captured: dict[str, FakeRgbwBulb] = {}

    def factory(ip_address: str) -> FakeRgbwBulb:
        bulb = FakeRgbwBulb(ip_address)
        captured["bulb"] = bulb
        return bulb

    monkeypatch.setattr("app.integrations.flux_led.WifiLedBulb", factory)
    adapter = FluxLedAdapter({"ip_address": "192.168.1.55"})
    await adapter.set_rgb(10, 20, 30, brightness=99)

    assert captured["bulb"].last_rgbw == (10, 20, 30, 0, 99, 0)


@pytest.mark.asyncio
async def test_flux_led_adapter_blink_uses_saturated_rgb_on_rgbw_bulb(monkeypatch) -> None:
    captured: dict[str, FakeRgbwBulb] = {}

    def factory(ip_address: str) -> FakeRgbwBulb:
        bulb = FakeRgbwBulb(ip_address)
        captured["bulb"] = bulb
        return bulb

    monkeypatch.setattr("app.integrations.flux_led.WifiLedBulb", factory)
    adapter = FluxLedAdapter({"ip_address": "192.168.1.55"})
    await adapter.set_rgb_blink(255, 200, 0, brightness=30)

    assert captured["bulb"].last_rgbw == (255, 200, 0, 0, 30, 0)
    assert captured["bulb"].effect is None
