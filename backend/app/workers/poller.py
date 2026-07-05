from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.timezone import utc_now
from app.db.session import get_session_factory, init_engine
from app.models import MeterSample
from app.services.device_automation import apply_automation_for_sample
from app.services.events import record_event
from app.services.meter_client import fetch_meter_payload
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload
from app.services.smart_plug_automation import apply_smart_plug_automation_for_sample
from app.services.telegram_bot import run_telegram_bot_forever

logger = get_logger(__name__)


@dataclass(frozen=True)
class PollResult:
    ok: bool
    sample_id: int | None = None
    error: str | None = None


async def poll_once(db: Session) -> PollResult:
    try:
        fetched = await fetch_meter_payload()
        parsed = parse_meter_xml(fetched.payload)
        sample = store_parsed_payload(db, parsed, poll_duration_ms=fetched.duration_ms)
        await apply_automation_for_sample(db, sample)
        await apply_smart_plug_automation_for_sample(db, sample)
        if parsed.data_quality == "invalid":
            record_event(
                db,
                event_type="meter_payload_invalid",
                severity="warning",
                message=parsed.error_message or "Payload XML invalido",
                metadata={"sample_id": sample.id, "source": fetched.source},
            )
        db.commit()
        logger.info(
            "meter_sample_stored",
            extra={"sample_id": sample.id, "quality": sample.data_quality, "source": fetched.source},
        )
        return PollResult(ok=True, sample_id=sample.id)
    except Exception as exc:  # noqa: BLE001 - worker must keep running
        db.rollback()
        record_event(
            db,
            event_type="meter_poll_failed",
            severity="error",
            message=str(exc),
            metadata={},
        )
        db.commit()
        logger.exception("meter_poll_failed")
        return PollResult(ok=False, error=str(exc))


def detect_prolonged_outage(db: Session) -> None:
    settings = get_settings()
    latest = db.scalar(
        select(MeterSample)
        .where(MeterSample.data_quality.in_(["valid", "partial"]))
        .order_by(desc(MeterSample.timestamp_utc))
        .limit(1)
    )
    if latest is None:
        return
    age_seconds = (utc_now() - latest.timestamp_utc).total_seconds()
    if age_seconds > settings.prolonged_outage_seconds:
        record_event(
            db,
            event_type="meter_outage",
            severity="warning",
            message="Ausencia prolongada de lecturas validas del medidor",
            metadata={"age_seconds": age_seconds},
        )
        db.commit()


async def run_forever() -> None:
    setup_logging()
    init_engine()
    settings = get_settings()
    failures = 0
    logger.info("worker_started", extra={"simulation_mode": settings.simulation_mode})
    if settings.feature_telegram:
        asyncio.create_task(run_telegram_bot_forever())

    while True:
        with get_session_factory()() as db:
            result = await poll_once(db)
            detect_prolonged_outage(db)
        if result.ok:
            failures = 0
            sleep_for = settings.meter_poll_interval_seconds
        else:
            failures += 1
            sleep_for = min(settings.meter_poll_interval_seconds, 5 * (2 ** min(failures, 5)))
            sleep_for += random.uniform(0, 1)
        await asyncio.sleep(sleep_for)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
