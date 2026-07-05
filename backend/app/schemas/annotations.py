from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.common import OrmModel


class AnnotationCreate(BaseModel):
    appliance_name: str
    home_area: str | None = None
    appliance_type: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    approx_power_w: Decimal | None = None
    comment: str | None = None
    source: str = "manual"
    confidence: str = "confirmed_manual"


class AnnotationUpdate(BaseModel):
    appliance_name: str | None = None
    home_area: str | None = None
    appliance_type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    approx_power_w: Decimal | None = None
    comment: str | None = None
    source: str | None = None
    confidence: str | None = None


class AnnotationRead(AnnotationCreate, OrmModel):
    id: int
    created_at: datetime
    updated_at: datetime
