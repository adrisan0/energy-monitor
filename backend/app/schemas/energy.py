from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import OrmModel


class AggregateRead(OrmModel):
    id: int
    period: str
    period_start_utc: datetime
    period_end_utc: datetime
    period_start_local: datetime
    period_end_local: datetime
    solar_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float
    house_consumption_kwh: float
    solar_self_consumption_kwh: float
    self_sufficiency_percent: float | None
    surplus_export_percent: float | None
    max_power_w: float | None
    min_power_w: float | None
    estimated_cost_eur: float
    compensation_eur: float
    fixed_cost_eur: float
    taxes_eur: float
    net_cost_eur: float
    sample_count: int
    incomplete_intervals: int
    is_complete: bool


class EnergySummary(BaseModel):
    start: datetime
    end: datetime
    solar_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float
    house_consumption_kwh: float
    solar_self_consumption_kwh: float
    self_sufficiency_percent: float | None
    surplus_export_percent: float | None
    estimated_cost_eur: float
    compensation_eur: float
    fixed_cost_eur: float
    taxes_eur: float
    net_cost_eur: float
    incomplete_intervals: int
    note: str


class EnergyComparison(BaseModel):
    current: EnergySummary
    previous: EnergySummary
    delta_net_cost_eur: float
    delta_house_consumption_kwh: float
