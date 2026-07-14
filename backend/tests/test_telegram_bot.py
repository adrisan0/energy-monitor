from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.db.session import get_session_factory
from app.integrations.base import DeviceState
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload
from app.services.telegram_bot import (
    TelegramBotService,
    apply_callback_action,
    build_status_message,
    find_flux_device,
    is_peak_time,
    parse_allowed_chat_ids,
    parse_bot_tokens,
)


def test_parse_allowed_chat_ids() -> None:
    assert parse_allowed_chat_ids("123, 456;789") == {123, 456, 789}


def test_parse_bot_tokens_keeps_order_and_deduplicates() -> None:
    assert parse_bot_tokens("main", "backup; main, third") == ["main", "backup", "third"]


def test_is_peak_time_uses_weekdays_only() -> None:
    monday_peak = datetime(2026, 7, 6, 10, 30, tzinfo=UTC)
    saturday_peak_hour = datetime(2026, 7, 4, 10, 30, tzinfo=UTC)
    monday_valley = datetime(2026, 7, 6, 3, 30, tzinfo=UTC)

    assert is_peak_time(monday_peak) is True
    assert is_peak_time(saturday_peak_hour) is False
    assert is_peak_time(monday_valley) is False


@pytest.mark.asyncio
async def test_apply_callback_action_updates_led_profile_and_flags() -> None:
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 6)
        secondary = db.get(__import__("app.models", fromlist=["Device"]).Device, 7)
        if secondary is not None:
            secondary.active = False
        device.status = "active"
        device.active = True
        device.control_mode = "automatic"
        device.config = {"adapter": "flux_led", "ip_address": "192.168.1.29", "automation": {"enabled": True}}
        db.commit()

        result = await apply_callback_action(db, "profile:grid_import_alert")
        selected_device = find_flux_device(db)

        assert result == "Perfil aplicado: importacion"
        assert selected_device.config["automation"]["profile"] == "grid_import_alert"
        assert selected_device.config["automation"]["metric"] == "grid_import_w"

        result = await apply_callback_action(db, "flag:blink_on_solar_grid_import")
        selected_device = find_flux_device(db)

        assert result == "blink_on_solar_grid_import: OFF"
        assert selected_device.config["automation"]["blink_on_solar_grid_import"] is False


@pytest.mark.asyncio
async def test_build_status_message_includes_energy_and_led(monkeypatch) -> None:
    class FakeAdapter:
        async def get_state(self):
            return DeviceState(online=True, is_on=True, raw={"rgb": [1, 2, 3], "brightness": 120})

    monkeypatch.setattr("app.services.telegram_bot.adapter_for_device", lambda device: FakeAdapter())
    with get_session_factory()() as db:
        device = db.get(__import__("app.models", fromlist=["Device"]).Device, 6)
        device.status = "active"
        device.control_mode = "automatic"
        device.config = {"adapter": "flux_led", "ip_address": "192.168.1.29", "automation": {"enabled": True}}
        parsed = parse_meter_xml(
            """
            <root>
              <variable><id>pac1</id><value>300</value></variable>
              <variable><id>pac2</id><value>700</value></variable>
              <variable><id>fpot1</id><value>1.000</value></variable>
            </root>
            """,
            timestamp_utc=datetime(2026, 7, 6, 10, 30, tzinfo=UTC),
        )
        store_parsed_payload(db, parsed, poll_duration_ms=1)
        db.commit()

        message = await build_status_message(db)

    assert "Estado energia" in message
    assert "Importacion: 300 W" in message
    assert "en hora punta" in message
    assert "RGB actual: [1, 2, 3]" in message


@pytest.mark.asyncio
async def test_alert_condition_uses_hold_and_cooldown(monkeypatch) -> None:
    settings = Settings(
        telegram_allowed_chat_ids="1",
        telegram_import_alert_hold_seconds=0,
        telegram_alert_cooldown_seconds=900,
    )
    service = TelegramBotService(settings)
    sent: list[str] = []

    async def fake_broadcast(client, text):
        sent.append(text)

    monkeypatch.setattr(service, "_broadcast", fake_broadcast)

    await service._handle_alert_condition(None, "import", True, "alert", "recovery", hold_seconds=0)
    await service._handle_alert_condition(None, "import", True, "alert", "recovery", hold_seconds=0)
    await service._handle_alert_condition(None, "import", False, "alert", "recovery", hold_seconds=0)

    assert sent == ["alert", "recovery"]


@pytest.mark.asyncio
async def test_maybe_send_alerts_reports_meter_outage_and_recovery(monkeypatch) -> None:
    settings = Settings(
        telegram_allowed_chat_ids="1",
        telegram_meter_alert_hold_seconds=0,
        telegram_import_alert_hold_seconds=999999,
        telegram_alert_cooldown_seconds=900,
        prolonged_outage_seconds=600,
    )
    service = TelegramBotService(settings)
    sent: list[str] = []

    async def fake_broadcast(client, text):
        sent.append(text)

    monkeypatch.setattr(service, "_broadcast", fake_broadcast)

    with get_session_factory()() as db:
        old_sample = parse_meter_xml(
            """
            <root>
              <variable><id>pac1</id><value>100</value></variable>
              <variable><id>pac2</id><value>0</value></variable>
              <variable><id>fpot1</id><value>1.000</value></variable>
            </root>
            """,
            timestamp_utc=datetime(2026, 7, 6, 10, 0, tzinfo=UTC),
        )
        store_parsed_payload(db, old_sample, poll_duration_ms=1)
        db.commit()

    await service._maybe_send_alerts(None)
    await service._maybe_send_alerts(None)

    with get_session_factory()() as db:
        fresh_sample = parse_meter_xml(
            """
            <root>
              <variable><id>pac1</id><value>50</value></variable>
              <variable><id>pac2</id><value>0</value></variable>
              <variable><id>fpot1</id><value>1.000</value></variable>
            </root>
            """,
            timestamp_utc=datetime.utcnow().replace(tzinfo=UTC),
        )
        store_parsed_payload(db, fresh_sample, poll_duration_ms=1)
        db.commit()

    await service._maybe_send_alerts(None)

    assert "Medidor desconectado" in sent[0]
    assert "Medidor recuperado" in sent[1]
