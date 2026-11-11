from __future__ import annotations

from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.timezone import db_utc, utc_now
from app.integrations.factory import adapter_for_device
from app.models import Device, SmartPlugReading

logger = get_logger(__name__)
MAX_INTEGRATION_GAP_SECONDS = 180


async def poll_metering_smart_plugs(db: Session) -> int:
    devices = list(
        db.scalars(
            select(Device).where(
                Device.active.is_(True),
                Device.measurement_capable.is_(True),
                Device.type == "smart_plug",
            )
        )
    )
    stored = 0
    for device in devices:
        config = dict(device.config or {})
        adapter_kind = str(config.get("adapter", ""))
        if adapter_kind not in {"sonoff_s61s", "kasa_hs100"}:
            continue
        if not (device.ip_address or config.get("ip_address") or config.get("host")):
            # Avoid repeated failed requests until the device has a LAN address.
            continue

        captured_at = utc_now()
        try:
            state = await adapter_for_device(device).get_state()
        except Exception as exc:  # noqa: BLE001 - one plug must not stop other device polling
            logger.warning(
                "smart_plug_metering_read_failed",
                extra={"device_id": device.id, "error_type": type(exc).__name__},
            )
            state = None

        previous = db.scalar(
            select(SmartPlugReading)
            .where(SmartPlugReading.device_id == device.id)
            .order_by(desc(SmartPlugReading.captured_at_utc), desc(SmartPlugReading.id))
            .limit(1)
        )
        online = bool(state and state.online)
        power_w = state.power_w if state and online else None
        energy_increment = Decimal("0")
        if previous and previous.online and previous.power_w is not None and online and power_w is not None:
            elapsed = (captured_at - db_utc(previous.captured_at_utc)).total_seconds()
            if 0 < elapsed <= MAX_INTEGRATION_GAP_SECONDS:
                energy_increment = ((previous.power_w + power_w) / Decimal("2")) * Decimal(str(elapsed)) / Decimal("3600000")

        db.add(
            SmartPlugReading(
                device_id=device.id,
                device_name=device.name,
                captured_at_utc=captured_at,
                online=online,
                is_on=state.is_on if state else None,
                power_w=power_w,
                energy_increment_kwh=energy_increment,
            )
        )
        stored += 1
    if stored:
        db.commit()
    return stored
