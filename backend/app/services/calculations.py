from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

INVALID_SENTINEL = Decimal("9223372036854775807")
ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
KWH_DIVISOR = Decimal("3600000")


@dataclass(frozen=True)
class DerivedPower:
    solar_w: Decimal
    grid_import_w: Decimal
    grid_export_w: Decimal
    house_consumption_w: Decimal
    solar_self_consumption_w: Decimal
    solar_self_consumption_percent: Decimal | None


@dataclass(frozen=True)
class IntervalEnergy:
    solar_kwh: Decimal
    grid_import_kwh: Decimal
    grid_export_kwh: Decimal
    house_consumption_kwh: Decimal
    solar_self_consumption_kwh: Decimal
    elapsed_seconds: Decimal
    is_complete: bool
    reason: str | None = None


def is_invalid_decimal(value: Decimal | None) -> bool:
    return value is None or value == INVALID_SENTINEL


def quantize_decimal(value: Decimal, places: str = "0.001") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def calculate_power(pac1: Decimal, pac2: Decimal, fpot1: Decimal) -> DerivedPower:
    solar_w = max(pac2, ZERO)
    channel_1_power = max(pac1, ZERO)
    grid_export_w = channel_1_power if fpot1 < ZERO else ZERO
    grid_import_w = channel_1_power if fpot1 > ZERO else ZERO
    house_consumption_w = solar_w + grid_import_w - grid_export_w
    solar_self_consumption_w = min(solar_w, house_consumption_w)
    solar_self_consumption_w = max(solar_self_consumption_w, ZERO)

    percent = None
    if solar_w > ZERO:
        percent = quantize_decimal((solar_self_consumption_w / solar_w) * ONE_HUNDRED, "0.001")

    return DerivedPower(
        solar_w=quantize_decimal(solar_w),
        grid_import_w=quantize_decimal(grid_import_w),
        grid_export_w=quantize_decimal(grid_export_w),
        house_consumption_w=quantize_decimal(house_consumption_w),
        solar_self_consumption_w=quantize_decimal(solar_self_consumption_w),
        solar_self_consumption_percent=percent,
    )


def energy_from_average_power(avg_power_w: Decimal, elapsed_seconds: Decimal) -> Decimal:
    if avg_power_w <= ZERO or elapsed_seconds <= ZERO:
        return ZERO
    return quantize_decimal(avg_power_w * elapsed_seconds / KWH_DIVISOR, "0.000001")


def integrate_energy(
    previous_timestamp: datetime,
    current_timestamp: datetime,
    previous: DerivedPower,
    current: DerivedPower,
    *,
    max_complete_interval_seconds: int,
) -> IntervalEnergy:
    elapsed = Decimal(str((current_timestamp - previous_timestamp).total_seconds()))
    if elapsed <= ZERO:
        return _empty_interval(elapsed, "non_positive_elapsed")
    if elapsed > Decimal(max_complete_interval_seconds):
        return _empty_interval(elapsed, "gap_too_large")

    return IntervalEnergy(
        solar_kwh=energy_from_average_power((previous.solar_w + current.solar_w) / 2, elapsed),
        grid_import_kwh=energy_from_average_power((previous.grid_import_w + current.grid_import_w) / 2, elapsed),
        grid_export_kwh=energy_from_average_power((previous.grid_export_w + current.grid_export_w) / 2, elapsed),
        house_consumption_kwh=energy_from_average_power(
            (previous.house_consumption_w + current.house_consumption_w) / 2, elapsed
        ),
        solar_self_consumption_kwh=energy_from_average_power(
            (previous.solar_self_consumption_w + current.solar_self_consumption_w) / 2, elapsed
        ),
        elapsed_seconds=elapsed,
        is_complete=True,
    )


def _empty_interval(elapsed: Decimal, reason: str) -> IntervalEnergy:
    return IntervalEnergy(
        solar_kwh=ZERO,
        grid_import_kwh=ZERO,
        grid_export_kwh=ZERO,
        house_consumption_kwh=ZERO,
        solar_self_consumption_kwh=ZERO,
        elapsed_seconds=elapsed,
        is_complete=False,
        reason=reason,
    )
