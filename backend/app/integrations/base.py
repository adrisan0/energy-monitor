from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DeviceState:
    online: bool
    is_on: bool | None = None
    power_w: Decimal | None = None
    raw: dict[str, Any] | None = None


class DeviceAdapter(ABC):
    """Contrato para integraciones futuras. No controla dispositivos en la v0.1."""

    @abstractmethod
    async def get_state(self) -> DeviceState:
        raise NotImplementedError

    @abstractmethod
    async def turn_on(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def turn_off(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_power(self) -> Decimal | None:
        raise NotImplementedError

    async def set_rgb(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        raise NotImplementedError

    async def set_rgb_blink(self, r: int, g: int, b: int, brightness: int | None = None) -> None:
        raise NotImplementedError
