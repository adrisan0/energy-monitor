from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.timezone import utc_now
from app.db.session import get_session_factory
from app.integrations.factory import adapter_for_device
from app.models import Device, MeterSample
from app.services.device_automation import apply_automation_to_device, merged_automation_config, resolve_color_target
from app.services.events import record_event

logger = get_logger(__name__)


@dataclass
class AlertState:
    since: datetime | None = None
    last_sent: datetime | None = None
    active_sent: bool = False


def parse_allowed_chat_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        result.add(int(item))
    return result


def parse_bot_tokens(primary: str | None, extra: str) -> list[str]:
    tokens: list[str] = []
    for raw in [primary or "", extra]:
        for item in raw.replace(";", ",").split(","):
            token = item.strip()
            if token and token not in tokens:
                tokens.append(token)
    return tokens


def is_peak_time(local_timestamp: datetime) -> bool:
    if local_timestamp.weekday() >= 5:
        return False
    hour = local_timestamp.hour
    return 10 <= hour < 14 or 18 <= hour < 22


def latest_usable_sample(db: Session) -> MeterSample | None:
    return db.scalar(
        select(MeterSample)
        .where(MeterSample.data_quality.in_(["valid", "partial"]))
        .order_by(desc(MeterSample.timestamp_utc))
        .limit(1)
    )


def find_flux_device(db: Session) -> Device | None:
    devices = db.scalars(select(Device).where(Device.active.is_(True)).order_by(Device.id.asc()))
    flux_devices = [
        device
        for device in devices
        if (device.config or {}).get("adapter") == "flux_led"
        or device.type == "light_controller"
        or device.ip_address in {"192.168.1.29", "192.168.1.55"}
    ]
    active_flux_devices = [device for device in flux_devices if device.status == "active"]
    candidates = active_flux_devices or flux_devices
    return (
        next((device for device in candidates if device.ip_address == "192.168.1.29"), None)
        or next((device for device in candidates if (device.config or {}).get("ip_address") == "192.168.1.29"), None)
        or next(iter(candidates), None)
    )


def build_telegram_keyboard(device: Device | None) -> dict[str, Any]:
    automation = _automation_from_device(device)
    surplus_enabled = bool(automation.get("surplus_override", True))
    blink_enabled = bool(automation.get("blink_on_solar_grid_import", True))
    return {
        "inline_keyboard": [
            [{"text": "Status", "callback_data": "status"}],
            [
                {"text": "Modo consumo", "callback_data": "profile:consumption_gradient"},
                {"text": "Modo importacion", "callback_data": "profile:grid_import_alert"},
                {"text": "Modo precio", "callback_data": "profile:tariff_price"},
            ],
            [
                {"text": f"Excedente {'ON' if surplus_enabled else 'OFF'}", "callback_data": "flag:surplus_override"},
                {"text": f"Parpadeo {'ON' if blink_enabled else 'OFF'}", "callback_data": "flag:blink_on_solar_grid_import"},
            ],
            [
                {"text": "Auto", "callback_data": "control:automatic"},
                {"text": "Manual", "callback_data": "control:manual"},
            ],
            [
                {"text": "Encender", "callback_data": "power:on"},
                {"text": "Apagar", "callback_data": "power:off"},
            ],
            [{"text": "Probar auto", "callback_data": "apply"}],
        ]
    }


async def build_status_message(db: Session) -> str:
    sample = latest_usable_sample(db)
    device = find_flux_device(db)
    lines: list[str] = ["Estado energia"]
    if sample is None:
        lines.append("Sin lecturas utiles todavia.")
    else:
        age = max(0, round((utc_now() - _as_utc(sample.timestamp_utc)).total_seconds()))
        lines.extend(
            [
                f"Lectura: {sample.timestamp_local} ({age}s)",
                f"Solar: {_format_w(sample.solar_w)}",
                f"Consumo casa: {_format_w(sample.house_consumption_w)}",
                f"Importacion: {_format_w(sample.grid_import_w)}",
                f"Exportacion: {_format_w(sample.grid_export_w)}",
                f"Calidad: {sample.data_quality}",
            ]
        )
        if _decimal(sample.grid_import_w) > Decimal("0"):
            lines.append("Alerta: importando de la red" + (" en hora punta" if is_peak_time(sample.timestamp_local) else ""))
        else:
            lines.append("Alerta: sin importacion")

    lines.append("")
    lines.append("Lampara")
    if device is None:
        lines.append("No hay dispositivo flux_led activo.")
        return "\n".join(lines)

    automation = merged_automation_config(device.config)
    profile = str(automation.get("profile", "consumption_gradient"))
    lines.extend(
        [
            f"Dispositivo: {device.name}",
            f"Modo control: {device.control_mode}",
            f"Perfil: {_profile_label(profile)}",
            f"Excedente especial: {'ON' if automation.get('surplus_override', True) else 'OFF'}",
            f"Parpadeo solar+red: {'ON' if automation.get('blink_on_solar_grid_import', True) else 'OFF'}",
        ]
    )
    if sample is not None:
        target = resolve_color_target(sample, automation)
        if target is not None:
            lines.append(f"Color esperado: {target.tier}{' parpadeando' if target.blink else ''}")

    try:
        state = await adapter_for_device(device).get_state()
        raw = state.raw or {}
        lines.extend(
            [
                f"Estado real: {'online' if state.online else 'offline'} / {'encendida' if state.is_on else 'apagada'}",
                f"RGB actual: {raw.get('rgb', '-')}",
                f"Brillo actual: {raw.get('brightness', '-')}",
            ]
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Estado real: error ({exc})")
    return "\n".join(lines)


async def apply_callback_action(db: Session, data: str) -> str:
    device = find_flux_device(db)
    if device is None:
        return "No hay lampara flux_led activa."

    if data.startswith("profile:"):
        profile = data.split(":", 1)[1]
        _set_profile(device, profile)
        db.commit()
        return f"Perfil aplicado: {_profile_label(profile)}"
    if data.startswith("flag:"):
        flag = data.split(":", 1)[1]
        enabled = _toggle_automation_flag(device, flag)
        db.commit()
        return f"{flag}: {'ON' if enabled else 'OFF'}"
    if data.startswith("control:"):
        mode = data.split(":", 1)[1]
        device.control_mode = mode
        config = dict(device.config)
        automation = merged_automation_config(config)
        automation["enabled"] = mode == "automatic"
        config["automation"] = automation
        _save_device_config(device, config)
        db.commit()
        return f"Modo {mode} aplicado"
    if data.startswith("power:"):
        action = data.split(":", 1)[1]
        adapter = adapter_for_device(device)
        if action == "on":
            await adapter.turn_on()
            return "Lampara encendida"
        if action == "off":
            await adapter.turn_off()
            return "Lampara apagada"
    if data == "apply":
        sample = latest_usable_sample(db)
        if sample is None:
            return "No hay lecturas utiles para aplicar automatizacion."
        target = await apply_automation_to_device(db, device, sample, force=True)
        db.commit()
        if target is None:
            return "Automatizacion no aplicable."
        return f"Automatizacion aplicada: {target.tier}{' parpadeando' if target.blink else ''}"
    if data == "status":
        return "Status actualizado"
    return "Accion no reconocida"


class TelegramBotService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.allowed_chat_ids = parse_allowed_chat_ids(self.settings.telegram_allowed_chat_ids)
        self.bot_tokens = parse_bot_tokens(self.settings.telegram_bot_token, self.settings.telegram_bot_tokens)
        self.offset = 0
        self.alerts = {
            "import": AlertState(),
            "peak_import": AlertState(),
            "meter_outage": AlertState(),
        }

    async def run_forever(self) -> None:
        if not self.bot_tokens or not self.allowed_chat_ids:
            logger.warning("telegram_disabled_missing_token_or_chats")
            return
        base_url = f"https://api.telegram.org/bot{self.bot_tokens[0]}"
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            logger.info("telegram_bot_started", extra={"allowed_chat_count": len(self.allowed_chat_ids)})
            while True:
                try:
                    updates = await self._api(client, "getUpdates", {"offset": self.offset, "timeout": 10})
                    for update in updates:
                        self.offset = max(self.offset, int(update.get("update_id", 0)) + 1)
                        await self._handle_update(client, update)
                    await self._maybe_send_alerts(client)
                except Exception:  # noqa: BLE001
                    logger.exception("telegram_poll_failed")
                    await asyncio.sleep(self.settings.telegram_poll_interval_seconds)

    async def _handle_update(self, client: httpx.AsyncClient, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._handle_callback(client, update["callback_query"])
            return
        message = update.get("message") or {}
        chat_id = int((message.get("chat") or {}).get("id", 0))
        if not await self._authorize(client, chat_id):
            return
        text = str(message.get("text") or "").strip()
        await self._handle_text(client, chat_id, text)

    async def _handle_callback(self, client: httpx.AsyncClient, callback: dict[str, Any]) -> None:
        chat_id = int(((callback.get("message") or {}).get("chat") or {}).get("id", 0))
        callback_id = str(callback.get("id") or "")
        data = str(callback.get("data") or "")
        if not await self._authorize(client, chat_id):
            if callback_id:
                await self._api(client, "answerCallbackQuery", {"callback_query_id": callback_id, "text": "No autorizado"})
            return
        with get_session_factory()() as db:
            result = await apply_callback_action(db, data)
            record_event(
                db,
                event_type="telegram_command",
                severity="info",
                message=result,
                metadata={"chat_id": chat_id, "callback": data},
            )
            db.commit()
            status = await build_status_message(db)
            keyboard = build_telegram_keyboard(find_flux_device(db))
        if callback_id:
            await self._api(client, "answerCallbackQuery", {"callback_query_id": callback_id, "text": result})
        message = callback.get("message") or {}
        if message.get("message_id"):
            await self._api(
                client,
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": message["message_id"],
                    "text": status,
                    "reply_markup": keyboard,
                },
            )
        else:
            await self._send_status(client, chat_id)

    async def _handle_text(self, client: httpx.AsyncClient, chat_id: int, text: str) -> None:
        command = text.split()[0].lower().split("@", 1)[0] if text else "/status"
        action = {
            "/start": "status",
            "/status": "status",
            "/modo_consumo": "profile:consumption_gradient",
            "/consumo": "profile:consumption_gradient",
            "/modo_importacion": "profile:grid_import_alert",
            "/modo_exportacion": "profile:grid_import_alert",
            "/importacion": "profile:grid_import_alert",
            "/modo_precio": "profile:tariff_price",
            "/precio": "profile:tariff_price",
            "/excedente_on": "set:surplus_override:on",
            "/excedente_off": "set:surplus_override:off",
            "/blink_on": "set:blink_on_solar_grid_import:on",
            "/blink_off": "set:blink_on_solar_grid_import:off",
            "/auto": "control:automatic",
            "/manual": "control:manual",
            "/on": "power:on",
            "/off": "power:off",
            "/apply": "apply",
        }.get(command)
        if action is None:
            await self._api(client, "sendMessage", {"chat_id": chat_id, "text": "Comando no reconocido. Usa /status."})
            return
        with get_session_factory()() as db:
            if action.startswith("set:"):
                result = _set_flag_from_command(db, action)
            else:
                result = await apply_callback_action(db, action)
            record_event(
                db,
                event_type="telegram_command",
                severity="info",
                message=result,
                metadata={"chat_id": chat_id, "command": command},
            )
            db.commit()
        await self._send_status(client, chat_id)

    async def _send_status(self, client: httpx.AsyncClient, chat_id: int) -> None:
        with get_session_factory()() as db:
            text = await build_status_message(db)
            keyboard = build_telegram_keyboard(find_flux_device(db))
        await self._api(client, "sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

    async def _authorize(self, client: httpx.AsyncClient, chat_id: int) -> bool:
        if chat_id in self.allowed_chat_ids:
            return True
        if chat_id:
            await self._api(client, "sendMessage", {"chat_id": chat_id, "text": "Chat no autorizado."})
        return False

    async def _maybe_send_alerts(self, client: httpx.AsyncClient) -> None:
        with get_session_factory()() as db:
            sample = latest_usable_sample(db)
        if sample is None:
            return

        age_seconds = max(0, round((utc_now() - _as_utc(sample.timestamp_utc)).total_seconds()))
        meter_outage = age_seconds > self.settings.prolonged_outage_seconds
        await self._handle_alert_condition(
            client,
            "meter_outage",
            meter_outage,
            (
                "Medidor desconectado: sin lecturas recientes. "
                f"Ultima lectura hace {age_seconds}s ({sample.timestamp_local})."
            ),
            f"Medidor recuperado: han vuelto las lecturas ({sample.timestamp_local}).",
            hold_seconds=self.settings.telegram_meter_alert_hold_seconds,
        )

        imported = _decimal(sample.grid_import_w)
        import_condition = imported >= Decimal(str(self.settings.telegram_import_alert_min_w))
        peak_condition = import_condition and is_peak_time(sample.timestamp_local)
        await self._handle_alert_condition(
            client,
            "import",
            import_condition,
            f"Alerta: importando {_format_w(imported)} de la red.",
            "Recuperado: ya no hay importacion relevante.",
            hold_seconds=self.settings.telegram_import_alert_hold_seconds,
        )
        await self._handle_alert_condition(
            client,
            "peak_import",
            peak_condition,
            f"Alerta punta: importando {_format_w(imported)} en hora punta.",
            "Recuperado: ya no importas en hora punta.",
            hold_seconds=self.settings.telegram_import_alert_hold_seconds,
        )

    async def _handle_alert_condition(
        self,
        client: httpx.AsyncClient,
        key: str,
        condition: bool,
        alert_text: str,
        recovery_text: str,
        *,
        hold_seconds: int,
    ) -> None:
        now = utc_now()
        state = self.alerts[key]
        if not condition:
            state.since = None
            if state.active_sent:
                state.active_sent = False
                await self._broadcast(client, recovery_text)
            return
        if state.since is None:
            state.since = now
            return
        held = (now - state.since).total_seconds() >= hold_seconds
        cooled = (
            state.last_sent is None
            or (now - state.last_sent).total_seconds() >= self.settings.telegram_alert_cooldown_seconds
        )
        if held and cooled:
            state.last_sent = now
            state.active_sent = True
            await self._broadcast(client, alert_text)

    async def _broadcast(self, client: httpx.AsyncClient, text: str) -> None:
        for chat_id in self.allowed_chat_ids:
            await self._api(client, "sendMessage", {"chat_id": chat_id, "text": text})
        for token in self.bot_tokens[1:]:
            async with httpx.AsyncClient(base_url=f"https://api.telegram.org/bot{token}", timeout=30.0) as extra_client:
                for chat_id in self.allowed_chat_ids:
                    await self._api(extra_client, "sendMessage", {"chat_id": chat_id, "text": text})

    async def _api(self, client: httpx.AsyncClient, method: str, payload: dict[str, Any]) -> Any:
        response = await client.post(f"/{method}", json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            raise RuntimeError(f"Telegram API error on {method}: {body}")
        return body.get("result")


async def run_telegram_bot_forever() -> None:
    await TelegramBotService().run_forever()


def _automation_from_device(device: Device | None) -> dict[str, Any]:
    if device is None:
        return merged_automation_config({})
    return merged_automation_config(device.config)


def _set_profile(device: Device, profile: str) -> None:
    config = dict(device.config)
    automation = merged_automation_config(config)
    automation["enabled"] = True
    automation["profile"] = profile
    automation["metric"] = "grid_import_w" if profile == "grid_import_alert" else "house_consumption_w"
    if profile == "grid_import_alert":
        automation["surplus_override"] = False
    if profile == "tariff_price":
        automation["surplus_override"] = False
        automation["blink_on_solar_grid_import"] = False
    config["automation"] = automation
    _save_device_config(device, config)


def _toggle_automation_flag(device: Device, flag: str) -> bool:
    if flag not in {"surplus_override", "blink_on_solar_grid_import"}:
        raise RuntimeError(f"Flag no soportado: {flag}")
    config = dict(device.config)
    automation = merged_automation_config(config)
    automation[flag] = not bool(automation.get(flag, True))
    config["automation"] = automation
    _save_device_config(device, config)
    return bool(automation[flag])


def _set_flag_from_command(db: Session, action: str) -> str:
    _, flag, value = action.split(":", 2)
    device = find_flux_device(db)
    if device is None:
        return "No hay lampara flux_led activa."
    config = dict(device.config)
    automation = merged_automation_config(config)
    automation[flag] = value == "on"
    config["automation"] = automation
    _save_device_config(device, config)
    return f"{flag}: {'ON' if automation[flag] else 'OFF'}"


def _profile_label(profile: str) -> str:
    if profile == "grid_import_alert":
        return "importacion"
    if profile == "tariff_price":
        return "precio"
    return "consumo"


def _format_w(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.0f} W"


def _decimal(value: Decimal | None) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal("0")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _save_device_config(device: Device, config: dict[str, Any]) -> None:
    device.config = config
    flag_modified(device, "config")
