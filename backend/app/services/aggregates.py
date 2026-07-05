from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timezone import db_utc, to_local
from app.models import EnergyAggregate, MeterSample
from app.services.calculations import DerivedPower, energy_from_average_power
from app.services.tariffs import estimate_financials, get_or_create_tariff

PERIODS = ("minute", "hour", "day", "month", "year")
ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")


def sample_to_derived(sample: MeterSample) -> DerivedPower | None:
    required = [
        sample.solar_w,
        sample.grid_import_w,
        sample.grid_export_w,
        sample.house_consumption_w,
        sample.solar_self_consumption_w,
    ]
    if sample.data_quality not in {"valid", "partial"} or any(value is None for value in required):
        return None
    return DerivedPower(
        solar_w=sample.solar_w or ZERO,
        grid_import_w=sample.grid_import_w or ZERO,
        grid_export_w=sample.grid_export_w or ZERO,
        house_consumption_w=sample.house_consumption_w or ZERO,
        solar_self_consumption_w=sample.solar_self_consumption_w or ZERO,
        solar_self_consumption_percent=sample.solar_self_consumption_percent,
    )


def update_aggregates_for_new_sample(
    db: Session,
    *,
    previous: MeterSample | None,
    current: MeterSample,
) -> None:
    current_power = sample_to_derived(current)
    previous_power = sample_to_derived(previous) if previous is not None else None

    if previous is None or previous_power is None or current_power is None:
        _mark_incomplete_for_timestamp(db, current.timestamp_utc, "missing_valid_neighbor")
        return

    previous_timestamp = db_utc(previous.timestamp_utc)
    current_timestamp = db_utc(current.timestamp_utc)
    elapsed_seconds = Decimal(str((current_timestamp - previous_timestamp).total_seconds()))
    if elapsed_seconds <= ZERO:
        _mark_incomplete_for_timestamp(db, current.timestamp_utc, "non_positive_elapsed")
        return
    if elapsed_seconds > Decimal(get_settings().max_complete_interval_seconds):
        _mark_incomplete_for_timestamp(db, current.timestamp_utc, "gap_too_large")
        return

    avg = DerivedPower(
        solar_w=(previous_power.solar_w + current_power.solar_w) / 2,
        grid_import_w=(previous_power.grid_import_w + current_power.grid_import_w) / 2,
        grid_export_w=(previous_power.grid_export_w + current_power.grid_export_w) / 2,
        house_consumption_w=(previous_power.house_consumption_w + current_power.house_consumption_w) / 2,
        solar_self_consumption_w=(
            previous_power.solar_self_consumption_w + current_power.solar_self_consumption_w
        )
        / 2,
        solar_self_consumption_percent=None,
    )

    for period in PERIODS:
        for start_utc, end_utc, seconds in _period_slices(previous_timestamp, current_timestamp, period):
            _add_slice(db, period, start_utc, end_utc, seconds, avg, current_power.house_consumption_w)


def _mark_incomplete_for_timestamp(db: Session, timestamp_utc: datetime, reason: str) -> None:
    del reason
    for period in PERIODS:
        start_utc, end_utc = period_bounds(timestamp_utc, period)
        aggregate = _get_or_create_aggregate(db, period, start_utc, end_utc)
        aggregate.incomplete_intervals += 1
        aggregate.is_complete = False


def _add_slice(
    db: Session,
    period: str,
    start_utc: datetime,
    end_utc: datetime,
    seconds: Decimal,
    avg: DerivedPower,
    current_house_power_w: Decimal,
) -> None:
    aggregate = _get_or_create_aggregate(db, period, start_utc, end_utc)
    aggregate.solar_kwh += energy_from_average_power(avg.solar_w, seconds)
    aggregate.grid_import_kwh += energy_from_average_power(avg.grid_import_w, seconds)
    aggregate.grid_export_kwh += energy_from_average_power(avg.grid_export_w, seconds)
    aggregate.house_consumption_kwh += energy_from_average_power(avg.house_consumption_w, seconds)
    aggregate.solar_self_consumption_kwh += energy_from_average_power(avg.solar_self_consumption_w, seconds)
    aggregate.sample_count += 1

    aggregate.max_power_w = (
        current_house_power_w if aggregate.max_power_w is None else max(aggregate.max_power_w, current_house_power_w)
    )
    aggregate.min_power_w = (
        current_house_power_w if aggregate.min_power_w is None else min(aggregate.min_power_w, current_house_power_w)
    )
    aggregate.self_sufficiency_percent = _percent(
        aggregate.solar_self_consumption_kwh, aggregate.house_consumption_kwh
    )
    aggregate.surplus_export_percent = _percent(aggregate.grid_export_kwh, aggregate.solar_kwh)

    tariff = get_or_create_tariff(db)
    money = estimate_financials(
        tariff=tariff,
        local_start=aggregate.period_start_local,
        local_end=aggregate.period_end_local,
        grid_import_kwh=aggregate.grid_import_kwh,
        grid_export_kwh=aggregate.grid_export_kwh,
    )
    aggregate.estimated_cost_eur = money["estimated_cost_eur"]
    aggregate.compensation_eur = money["compensation_eur"]
    aggregate.fixed_cost_eur = money["fixed_cost_eur"]
    aggregate.taxes_eur = money["taxes_eur"]
    aggregate.net_cost_eur = money["net_cost_eur"]


def _get_or_create_aggregate(db: Session, period: str, start_utc: datetime, end_utc: datetime) -> EnergyAggregate:
    aggregate = db.scalar(
        select(EnergyAggregate).where(
            EnergyAggregate.period == period,
            EnergyAggregate.period_start_utc == start_utc,
        )
    )
    if aggregate is not None:
        return aggregate

    aggregate = EnergyAggregate(
        period=period,
        period_start_utc=start_utc,
        period_end_utc=end_utc,
        period_start_local=to_local(start_utc),
        period_end_local=to_local(end_utc),
    )
    db.add(aggregate)
    db.flush()
    return aggregate


def _period_slices(start_utc: datetime, end_utc: datetime, period: str) -> Iterable[tuple[datetime, datetime, Decimal]]:
    cursor = start_utc.astimezone(UTC)
    final = end_utc.astimezone(UTC)
    while cursor < final:
        bucket_start, bucket_end = period_bounds(cursor, period)
        piece_end = min(bucket_end, final)
        if piece_end <= cursor:
            piece_end = final
        seconds = Decimal(str((piece_end - cursor).total_seconds()))
        yield bucket_start, bucket_end, seconds
        cursor = piece_end


def period_bounds(timestamp_utc: datetime, period: str) -> tuple[datetime, datetime]:
    local = to_local(timestamp_utc)
    if period == "minute":
        start_local = local.replace(second=0, microsecond=0)
        end_local = start_local + timedelta(minutes=1)
    elif period == "hour":
        start_local = local.replace(minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(hours=1)
    elif period == "day":
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
    elif period == "month":
        start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days = monthrange(start_local.year, start_local.month)[1]
        end_local = start_local + timedelta(days=days)
    elif period == "year":
        start_local = local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local.replace(year=start_local.year + 1)
    else:
        raise ValueError(f"Periodo no soportado: {period}")
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _percent(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= ZERO:
        return None
    return (numerator / denominator * ONE_HUNDRED).quantize(Decimal("0.001"))
