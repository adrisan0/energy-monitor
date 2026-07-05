from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.timezone import local_date_time, utc_now
from app.models import MeterSample
from app.services.aggregates import update_aggregates_for_new_sample
from app.services.meter_parser import ParsedMeterPayload


def store_parsed_payload(
    db: Session,
    parsed: ParsedMeterPayload,
    *,
    poll_duration_ms: int | None,
) -> MeterSample:
    local_ts, local_date, local_time = local_date_time(parsed.timestamp_utc)
    previous = db.scalar(select(MeterSample).order_by(desc(MeterSample.timestamp_utc)).limit(1))
    repeated = previous is not None and previous.payload_hash == parsed.payload_hash
    derived = parsed.derived

    sample = MeterSample(
        timestamp_utc=parsed.timestamp_utc,
        timestamp_local=local_ts,
        local_date=local_date,
        local_time=local_time,
        solar_w=derived.solar_w if derived else None,
        grid_import_w=derived.grid_import_w if derived else None,
        grid_export_w=derived.grid_export_w if derived else None,
        house_consumption_w=derived.house_consumption_w if derived else None,
        solar_self_consumption_w=derived.solar_self_consumption_w if derived else None,
        solar_self_consumption_percent=derived.solar_self_consumption_percent if derived else None,
        voltage_v=parsed.voltage_v,
        current_a=parsed.current_a,
        frequency_hz=parsed.frequency_hz,
        power_factor=parsed.power_factor,
        pac1=parsed.pac1,
        pac2=parsed.pac2,
        fpot1=parsed.fpot1,
        fpot2=parsed.fpot2,
        pact=parsed.pact,
        raw_variables=parsed.raw_variables,
        raw_payload_redacted=parsed.raw_payload_redacted,
        payload_hash=parsed.payload_hash,
        repeated_payload=repeated,
        data_quality=parsed.data_quality,
        error_message=parsed.error_message,
        poll_duration_ms=poll_duration_ms,
        created_at=utc_now(),
    )
    db.add(sample)
    db.flush()
    update_aggregates_for_new_sample(db, previous=previous, current=sample)
    return sample
