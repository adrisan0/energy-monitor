from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class DaikinDevice(BaseModel):
    """Provider-neutral representation; preserves unknown API fields."""

    model_config = ConfigDict(extra="allow")
    id: str = Field(validation_alias=AliasChoices("id", "_id"))
    name: str | None = None


class DeviceStatus(BaseModel):
    """Normalized common climate values plus the source payload."""

    model_config = ConfigDict(extra="allow")
    device_id: str
    temperature_setpoint: float | None = None
    room_temperature: float | None = None
    operating_mode: str | None = None
    is_on: bool | None = None
    raw: dict[str, Any] = {}
