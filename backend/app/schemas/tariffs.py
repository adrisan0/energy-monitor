from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel


class TariffBase(BaseModel):
    mode: str = Field(default="flat", pattern="^(flat|time_of_use|future_pvpc)$")
    flat_price_eur_per_kwh: Decimal = Decimal("0.180000")
    peak_price_eur_per_kwh: Decimal = Decimal("0.240000")
    shoulder_price_eur_per_kwh: Decimal = Decimal("0.170000")
    valley_price_eur_per_kwh: Decimal = Decimal("0.120000")
    surplus_compensation_eur_per_kwh: Decimal = Decimal("0.060000")
    monthly_fixed_cost_eur: Decimal = Decimal("29.00")
    meter_rental_monthly_eur: Decimal = Decimal("0.00")
    electricity_tax_percent: Decimal = Decimal("5.1127")
    vat_percent: Decimal = Decimal("21.0000")
    billing_start_date: date | None = None
    notes: str | None = None


class TariffRead(TariffBase, OrmModel):
    id: int
    created_at: datetime
    updated_at: datetime


class TariffUpdate(TariffBase):
    pass
