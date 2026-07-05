from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import OrmModel


class DeviceRead(OrmModel):
    id: int
    name: str
    manufacturer: str | None
    model: str | None
    type: str
    zone: str | None
    ip_address: str | None
    status: str
    measurement_capable: bool
    max_power_w: float | None
    active: bool
    control_mode: str
    config: dict[str, Any]
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DeviceStateRead(OrmModel):
    online: bool
    is_on: bool | None
    power_w: float | None
    raw: dict[str, Any] | None = None


class DeviceUpdate(OrmModel):
    name: str | None = Field(default=None, max_length=120)
    zone: str | None = Field(default=None, max_length=120)
    ip_address: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=32)
    max_power_w: float | None = None
    active: bool | None = None
    control_mode: str | None = Field(default=None, max_length=32)
    config: dict[str, Any] | None = None


class DeviceColorUpdate(OrmModel):
    rgb: list[int] = Field(min_length=3, max_length=3)
    brightness: int | None = Field(default=None, ge=0, le=255)


class DeviceModeUpdate(OrmModel):
    mode: str = Field(pattern="^(manual|automatic)$")
