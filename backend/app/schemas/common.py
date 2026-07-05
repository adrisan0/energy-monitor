from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    simulation_mode: bool
