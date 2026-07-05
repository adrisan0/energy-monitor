from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TariffSettings

ZERO = Decimal("0")


def get_or_create_tariff(db: Session) -> TariffSettings:
    tariff = db.scalar(select(TariffSettings).order_by(TariffSettings.id.asc()).limit(1))
    if tariff is None:
        tariff = TariffSettings(
            mode="flat",
            surplus_compensation_eur_per_kwh=Decimal("0.060000"),
            monthly_fixed_cost_eur=Decimal("29.00"),
            notes="Valores iniciales configurables. No equivalen necesariamente a la factura real.",
        )
        db.add(tariff)
        db.flush()
    return tariff


def price_for_timestamp(tariff: TariffSettings, local_timestamp: datetime) -> Decimal:
    if tariff.mode == "time_of_use":
        hour = local_timestamp.hour
        if 10 <= hour < 14 or 18 <= hour < 22:
            return tariff.peak_price_eur_per_kwh
        if 8 <= hour < 10 or 14 <= hour < 18 or 22 <= hour < 24:
            return tariff.shoulder_price_eur_per_kwh
        return tariff.valley_price_eur_per_kwh
    return tariff.flat_price_eur_per_kwh


def estimate_financials(
    *,
    tariff: TariffSettings,
    local_start: datetime,
    local_end: datetime,
    grid_import_kwh: Decimal,
    grid_export_kwh: Decimal,
) -> dict[str, Decimal]:
    elapsed_seconds = Decimal(str(max((local_end - local_start).total_seconds(), 0)))
    days = elapsed_seconds / Decimal("86400")
    variable_cost = grid_import_kwh * price_for_timestamp(tariff, local_start)
    compensation = grid_export_kwh * tariff.surplus_compensation_eur_per_kwh
    fixed_monthly = tariff.monthly_fixed_cost_eur + tariff.meter_rental_monthly_eur
    fixed_cost = fixed_monthly * days / Decimal("30.4375")
    electricity_tax = (variable_cost + fixed_cost) * tariff.electricity_tax_percent / Decimal("100")
    vat_base = variable_cost + fixed_cost + electricity_tax - compensation
    vat = max(vat_base, ZERO) * tariff.vat_percent / Decimal("100")
    taxes = electricity_tax + vat
    net = variable_cost + fixed_cost + taxes - compensation
    return {
        "estimated_cost_eur": variable_cost,
        "compensation_eur": compensation,
        "fixed_cost_eur": fixed_cost,
        "taxes_eur": taxes,
        "net_cost_eur": net,
    }
