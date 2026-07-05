from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.session import get_session_factory
from app.services.device_automation import apply_automation_to_device, merged_automation_config, resolve_color_target
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload

XML_EXPORT = """
<root>
  <variable><id>pac1</id><value>2000</value></variable>
  <variable><id>pac2</id><value>3000</value></variable>
  <variable><id>fpot1</id><value>-1.000</value></variable>
</root>
"""

XML_LOW = """
<root>
  <variable><id>pac1</id><value>200</value></variable>
  <variable><id>pac2</id><value>0</value></variable>
  <variable><id>fpot1</id><value>1.000</value></variable>
</root>
"""

XML_MEDIUM = """
<root>
  <variable><id>pac1</id><value>800</value></variable>
  <variable><id>pac2</id><value>0</value></variable>
  <variable><id>fpot1</id><value>1.000</value></variable>
</root>
"""

XML_HIGH = """
<root>
  <variable><id>pac1</id><value>2000</value></variable>
  <variable><id>pac2</id><value>0</value></variable>
  <variable><id>fpot1</id><value>1.000</value></variable>
</root>
"""


def _automation() -> dict:
    return merged_automation_config(
        {
            "automation": {
                "enabled": True,
                "metric": "house_consumption_w",
                "profile": "consumption_gradient",
                "surplus_override": True,
                "thresholds": {"low_max_w": 350, "medium_max_w": 1650},
                "colors": {"low": "#22C55E", "medium": "#F59E0B", "high": "#EF4444", "surplus": "#3B82F6"},
                "brightness": {"low": 96, "medium": 160, "high": 255, "surplus": 180},
            }
        }
    )


def test_resolve_color_target_low_medium_high_surplus() -> None:
    low = parse_meter_xml(XML_LOW, timestamp_utc=datetime(2026, 7, 3, 10, 0, tzinfo=UTC))
    medium = parse_meter_xml(XML_MEDIUM, timestamp_utc=datetime(2026, 7, 3, 10, 1, tzinfo=UTC))
    high = parse_meter_xml(XML_HIGH, timestamp_utc=datetime(2026, 7, 3, 10, 2, tzinfo=UTC))
    export = parse_meter_xml(XML_EXPORT, timestamp_utc=datetime(2026, 7, 3, 10, 3, tzinfo=UTC))
    automation = _automation()

    assert resolve_color_target(store_parsed_payload_obj(low), automation).tier == "low"
    assert resolve_color_target(store_parsed_payload_obj(medium), automation).tier == "medium"
    assert resolve_color_target(store_parsed_payload_obj(high), automation).tier == "high"
    assert resolve_color_target(store_parsed_payload_obj(export), automation).tier == "surplus"


def test_resolve_color_target_interpolates_between_low_medium_and_medium_high() -> None:
    automation = _automation()

    low_edge = resolve_color_target(store_parsed_payload_obj(parse_meter_xml(XML_LOW, timestamp_utc=datetime(2026, 7, 3, 10, 0, tzinfo=UTC))), automation)
    medium_mid = resolve_color_target(
        store_parsed_payload_obj(
            parse_meter_xml(
                """
                <root>
                  <variable><id>pac1</id><value>1000</value></variable>
                  <variable><id>pac2</id><value>0</value></variable>
                  <variable><id>fpot1</id><value>1.000</value></variable>
                </root>
                """,
                timestamp_utc=datetime(2026, 7, 3, 10, 1, tzinfo=UTC),
            )
        ),
        automation,
    )
    high = resolve_color_target(store_parsed_payload_obj(parse_meter_xml(XML_HIGH, timestamp_utc=datetime(2026, 7, 3, 10, 2, tzinfo=UTC))), automation)

    assert low_edge.rgb != (34, 197, 94)
    assert low_edge.rgb != (245, 158, 11)
    assert low_edge.brightness > 96
    assert low_edge.brightness < 160
    assert medium_mid.rgb != (245, 158, 11)
    assert medium_mid.rgb != (239, 68, 68)
    assert medium_mid.brightness > 160
    assert medium_mid.brightness < 255
    assert high.rgb == (239, 68, 68)


def store_parsed_payload_obj(parsed):
    class Sample:
        data_quality = parsed.data_quality
        solar_w = parsed.derived.solar_w if parsed.derived else None
        grid_export_w = parsed.derived.grid_export_w if parsed.derived else None
        grid_import_w = parsed.derived.grid_import_w if parsed.derived else None
        house_consumption_w = parsed.derived.house_consumption_w if parsed.derived else None

    return Sample()


def test_resolve_color_target_blinks_when_solar_generation_and_grid_import() -> None:
    automation = _automation()

    class Sample:
        data_quality = "partial"
        solar_w = Decimal("500")
        grid_import_w = Decimal("100")
        grid_export_w = Decimal("0")
        house_consumption_w = Decimal("800")

    target = resolve_color_target(Sample(), automation)

    assert target.tier == "medium"
    assert target.blink is True


def test_resolve_color_target_does_not_blink_when_flag_disabled() -> None:
    automation = _automation()
    automation["blink_on_solar_grid_import"] = False

    class Sample:
        data_quality = "partial"
        solar_w = Decimal("500")
        grid_import_w = Decimal("100")
        grid_export_w = Decimal("0")
        house_consumption_w = Decimal("800")

    target = resolve_color_target(Sample(), automation)

    assert target.tier == "medium"
    assert target.blink is False


@pytest.mark.asyncio
async def test_apply_automation_to_device_skips_manual(monkeypatch) -> None:
    from app.integrations.base import DeviceState

    class FakeAdapter:
        async def get_state(self):
            return DeviceState(online=True)

        async def turn_on(self):
            return None

        async def turn_off(self):
            return None

        async def get_power(self):
            return None

        async def set_rgb(self, r, g, b, brightness=None):
            raise AssertionError("should not be called")

    monkeypatch.setattr("app.services.device_automation.adapter_for_device", lambda device: FakeAdapter())
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 6)
        device.control_mode = "manual"
        device.config["automation"] = _automation()
        parsed = parse_meter_xml(XML_HIGH, timestamp_utc=datetime(2026, 7, 3, 10, 2, tzinfo=UTC))
        sample = store_parsed_payload(db, parsed, poll_duration_ms=1)
        result = await apply_automation_to_device(db, device, sample)
        assert result is None


@pytest.mark.asyncio
async def test_apply_automation_to_device_uses_blink_when_solar_generation_and_grid_import(monkeypatch) -> None:
    from app.integrations.base import DeviceState

    class FakeAdapter:
        def __init__(self) -> None:
            self.rgb_call = None
            self.blink_call = None

        async def get_state(self):
            return DeviceState(online=True)

        async def turn_on(self):
            return None

        async def turn_off(self):
            return None

        async def get_power(self):
            return None

        async def set_rgb(self, r, g, b, brightness=None):
            self.rgb_call = (r, g, b, brightness)

        async def set_rgb_blink(self, r, g, b, brightness=None):
            self.blink_call = (r, g, b, brightness)

    adapter = FakeAdapter()
    monkeypatch.setattr("app.services.device_automation.adapter_for_device", lambda device: adapter)
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 6)
        device.control_mode = "automatic"
        device.config = {
            **device.config,
            "automation": _automation(),
            "last_applied": None,
        }
        parsed = parse_meter_xml(
            """
            <root>
              <variable><id>pac1</id><value>100</value></variable>
              <variable><id>pac2</id><value>500</value></variable>
              <variable><id>fpot1</id><value>1.000</value></variable>
            </root>
            """,
            timestamp_utc=datetime(2026, 7, 3, 10, 5, tzinfo=UTC),
        )
        sample = store_parsed_payload(db, parsed, poll_duration_ms=1)
        result = await apply_automation_to_device(db, device, sample)

        assert result is not None
        assert result.blink is True
        assert adapter.rgb_call is None
        assert adapter.blink_call is not None


@pytest.mark.asyncio
async def test_apply_automation_to_device_force_bypasses_last_applied(monkeypatch) -> None:
    from app.integrations.base import DeviceState

    class FakeAdapter:
        def __init__(self) -> None:
            self.rgb_call = None

        async def get_state(self):
            return DeviceState(online=True)

        async def turn_on(self):
            return None

        async def turn_off(self):
            return None

        async def get_power(self):
            return None

        async def set_rgb(self, r, g, b, brightness=None):
            self.rgb_call = (r, g, b, brightness)

        async def set_rgb_blink(self, r, g, b, brightness=None):
            raise AssertionError("should not blink")

    adapter = FakeAdapter()
    monkeypatch.setattr("app.services.device_automation.adapter_for_device", lambda device: adapter)
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 6)
        device.control_mode = "automatic"
        automation = _automation()
        automation["surplus_override"] = False
        device.config = {
            **device.config,
            "automation": automation,
            "last_applied": {"tier": "high", "rgb": [239, 68, 68], "brightness": 255, "blink": False},
        }
        parsed = parse_meter_xml(XML_HIGH, timestamp_utc=datetime(2026, 7, 3, 10, 6, tzinfo=UTC))
        sample = store_parsed_payload(db, parsed, poll_duration_ms=1)
        result = await apply_automation_to_device(db, device, sample, force=True)

        assert result is not None
        assert result.tier == "high"
        assert adapter.rgb_call == (239, 68, 68, 255)


def test_resolve_color_target_grid_import_alert_profile() -> None:
    automation = merged_automation_config(
        {
            "automation": {
                "enabled": True,
                "profile": "grid_import_alert",
                "thresholds": {"low_max_w": 350, "medium_max_w": 1650},
                "colors": {"low": "#22C55E", "medium": "#F59E0B", "high": "#EF4444", "surplus": "#A855F7"},
                "brightness": {"low": 96, "medium": 128, "high": 196, "surplus": 255},
            }
        }
    )

    class Sample:
        data_quality = "partial"
        grid_export_w = Decimal("0")
        house_consumption_w = Decimal("0")

        def __init__(self, imported: str) -> None:
            self.grid_import_w = Decimal(imported)

    zero_import = resolve_color_target(Sample("0"), automation)
    low_import = resolve_color_target(Sample("120"), automation)
    medium_import = resolve_color_target(Sample("800"), automation)
    high_import = resolve_color_target(Sample("2500"), automation)

    assert zero_import.tier == "low"
    assert zero_import.rgb == (34, 197, 94)
    assert low_import.tier == "medium"
    assert medium_import.tier == "high"
    assert high_import.tier == "surplus"


def test_resolve_color_target_tariff_price_profile() -> None:
    automation = merged_automation_config(
        {
            "automation": {
                "enabled": True,
                "profile": "tariff_price",
                "colors": {"low": "#22C55E", "medium": "#F59E0B", "high": "#EF4444", "surplus": "#A855F7"},
                "brightness": {"low": 96, "medium": 160, "high": 255, "surplus": 255},
                "prices": {"low": 0.12, "medium": 0.17, "high": 0.24, "surplus": 0.24},
            }
        }
    )

    class Sample:
        data_quality = "partial"
        solar_w = Decimal("0")
        grid_import_w = Decimal("0")
        grid_export_w = Decimal("0")
        house_consumption_w = Decimal("0")

        def __init__(self, timestamp_local: datetime) -> None:
            self.timestamp_local = timestamp_local

    valley = resolve_color_target(Sample(datetime(2026, 7, 6, 7, 30, tzinfo=UTC)), automation)
    shoulder = resolve_color_target(Sample(datetime(2026, 7, 6, 15, 30, tzinfo=UTC)), automation)
    peak = resolve_color_target(Sample(datetime(2026, 7, 6, 20, 30, tzinfo=UTC)), automation)
    weekend = resolve_color_target(Sample(datetime(2026, 7, 4, 20, 30, tzinfo=UTC)), automation)

    assert valley.tier == "low"
    assert valley.rgb == (34, 197, 94)
    assert shoulder.tier == "medium"
    assert shoulder.rgb == (245, 158, 11)
    assert peak.tier == "high"
    assert peak.rgb == (239, 68, 68)
    assert weekend.tier == "low"
