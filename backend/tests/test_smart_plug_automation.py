from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.session import get_session_factory
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload
from app.services.smart_plug_automation import (
    apply_smart_plug_automation_to_device,
    is_peak_time,
    merged_thermo_automation_config,
)


def test_is_peak_time_matches_weekday_peak_windows() -> None:
    assert is_peak_time(datetime(2026, 7, 6, 10, 30, tzinfo=UTC)) is True
    assert is_peak_time(datetime(2026, 7, 6, 15, 30, tzinfo=UTC)) is False
    assert is_peak_time(datetime(2026, 7, 4, 20, 30, tzinfo=UTC)) is False


def test_merged_thermo_automation_config_uses_defaults() -> None:
    config = merged_thermo_automation_config({"thermo_automation": {"enabled": True, "surplus_on_w": 900}})
    assert config["enabled"] is True
    assert config["surplus_on_w"] == 900
    assert config["off_hold_seconds"] == 120


@pytest.mark.asyncio
async def test_turns_on_with_sustained_surplus(monkeypatch) -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.is_on = False
            self.turn_on_calls = 0

        async def get_state(self):
            from app.integrations.base import DeviceState

            return DeviceState(online=True, is_on=self.is_on)

        async def turn_on(self):
            self.is_on = True
            self.turn_on_calls += 1

        async def turn_off(self):
            self.is_on = False

        async def get_power(self):
            return None

    adapter = FakeAdapter()
    monkeypatch.setattr("app.services.smart_plug_automation.adapter_for_device", lambda device: adapter)

    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 2)
        device.control_mode = "automatic"
        device.config = {
            **device.config,
            "thermo_automation": {
                "enabled": True,
                "surplus_on_w": 800,
                "surplus_off_w": 100,
                "on_hold_seconds": 60,
                "off_hold_seconds": 60,
                "min_daily_runtime_minutes": 0,
                "topup_window_start_hour": 14,
                "topup_window_end_hour": 18,
                "block_peak_hours": True,
            },
        }
        first = store_parsed_payload(
            db,
            parse_meter_xml(
                """
                <root>
                  <variable><id>pac1</id><value>1500</value></variable>
                  <variable><id>pac2</id><value>2400</value></variable>
                  <variable><id>fpot1</id><value>-1.000</value></variable>
                </root>
                """,
                timestamp_utc=datetime(2026, 7, 6, 7, 0, tzinfo=UTC),
            ),
            poll_duration_ms=1,
        )
        await apply_smart_plug_automation_to_device(db, device, first, force=True)
        second = store_parsed_payload(
            db,
            parse_meter_xml(
                """
                <root>
                  <variable><id>pac1</id><value>1500</value></variable>
                  <variable><id>pac2</id><value>2400</value></variable>
                  <variable><id>fpot1</id><value>-1.000</value></variable>
                </root>
                """,
                timestamp_utc=datetime(2026, 7, 6, 7, 2, tzinfo=UTC),
            ),
            poll_duration_ms=1,
        )
        decision = await apply_smart_plug_automation_to_device(db, device, second, force=True)

        assert decision is not None
        assert decision.should_turn_on is True
        assert decision.reason == "excedente"
        assert adapter.turn_on_calls == 1


@pytest.mark.asyncio
async def test_turns_off_in_peak_even_if_currently_on(monkeypatch) -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.is_on = True
            self.turn_off_calls = 0

        async def get_state(self):
            from app.integrations.base import DeviceState

            return DeviceState(online=True, is_on=self.is_on)

        async def turn_on(self):
            self.is_on = True

        async def turn_off(self):
            self.is_on = False
            self.turn_off_calls += 1

        async def get_power(self):
            return None

    adapter = FakeAdapter()
    monkeypatch.setattr("app.services.smart_plug_automation.adapter_for_device", lambda device: adapter)

    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 2)
        device.control_mode = "automatic"
        device.config = {
            **device.config,
            "thermo_automation": {"enabled": True},
            "thermo_automation_state": {"runtime_date": "2026-07-06", "runtime_today_seconds": 1200},
        }
        sample = store_parsed_payload(
            db,
            parse_meter_xml(
                """
                <root>
                  <variable><id>pac1</id><value>200</value></variable>
                  <variable><id>pac2</id><value>0</value></variable>
                  <variable><id>fpot1</id><value>1.000</value></variable>
                </root>
                """,
                timestamp_utc=datetime(2026, 7, 6, 10, 30, tzinfo=UTC),
            ),
            poll_duration_ms=1,
        )
        decision = await apply_smart_plug_automation_to_device(db, device, sample, force=True)

        assert decision is not None
        assert decision.should_turn_on is False
        assert decision.blocked_by_peak is True
        assert adapter.turn_off_calls == 1


@pytest.mark.asyncio
async def test_topup_window_meets_daily_minimum(monkeypatch) -> None:
    class FakeAdapter:
        def __init__(self) -> None:
            self.is_on = False
            self.turn_on_calls = 0

        async def get_state(self):
            from app.integrations.base import DeviceState

            return DeviceState(online=True, is_on=self.is_on)

        async def turn_on(self):
            self.is_on = True
            self.turn_on_calls += 1

        async def turn_off(self):
            self.is_on = False

        async def get_power(self):
            return None

    adapter = FakeAdapter()
    monkeypatch.setattr("app.services.smart_plug_automation.adapter_for_device", lambda device: adapter)

    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 2)
        device.control_mode = "automatic"
        device.config = {
            **device.config,
            "thermo_automation": {
                "enabled": True,
                "surplus_on_w": 2000,
                "surplus_off_w": 100,
                "on_hold_seconds": 120,
                "off_hold_seconds": 120,
                "min_daily_runtime_minutes": 45,
                "topup_window_start_hour": 14,
                "topup_window_end_hour": 18,
                "block_peak_hours": True,
            },
            "thermo_automation_state": {"runtime_date": "2026-07-06", "runtime_today_seconds": 300},
        }
        sample = store_parsed_payload(
            db,
            parse_meter_xml(
                """
                <root>
                  <variable><id>pac1</id><value>300</value></variable>
                  <variable><id>pac2</id><value>0</value></variable>
                  <variable><id>fpot1</id><value>1.000</value></variable>
                </root>
                """,
                timestamp_utc=datetime(2026, 7, 6, 15, 15, tzinfo=UTC),
            ),
            poll_duration_ms=1,
        )
        decision = await apply_smart_plug_automation_to_device(db, device, sample, force=True)

        assert decision is not None
        assert decision.should_turn_on is True
        assert decision.reason == "minimo_diario"
        assert adapter.turn_on_calls == 1
