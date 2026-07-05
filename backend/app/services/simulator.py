from __future__ import annotations

import math
import random
from datetime import datetime
from decimal import Decimal

from app.core.timezone import to_local, utc_now


def simulated_meter_xml(timestamp_utc: datetime | None = None) -> str:
    now = to_local(timestamp_utc or utc_now())
    seconds = now.hour * 3600 + now.minute * 60 + now.second
    day_fraction = seconds / 86400

    daylight = max(0.0, math.sin((day_fraction - 0.25) * math.pi / 0.50))
    cloud = 0.72 + 0.22 * math.sin(seconds / 1900) + 0.08 * math.sin(seconds / 470)
    solar = max(0.0, 4300.0 * daylight * cloud)

    base = 280 + 80 * math.sin(seconds / 1300)
    evening = 650 if 19 <= now.hour <= 22 else 0
    morning = 420 if 7 <= now.hour <= 9 else 0
    washer = _pulse(now.hour, now.minute, 11, 20, 70, 900)
    dishwasher = _pulse(now.hour, now.minute, 15, 10, 80, 1100)
    heater = _pulse(now.hour, now.minute, 13, 5, 50, 1800) + _pulse(now.hour, now.minute, 21, 0, 45, 1800)
    computer = 450 if 17 <= now.hour <= 23 else 80
    random.seed(now.date().isoformat() + str(now.hour))
    noise = random.uniform(-65, 65)
    consumption = max(120.0, base + evening + morning + washer + dishwasher + heater + computer + noise)

    net_grid = consumption - solar
    fpot1 = Decimal("1.000") if net_grid > 0 else Decimal("-1.000")
    pac1 = Decimal(str(abs(net_grid))).quantize(Decimal("0.01"))
    pac2 = Decimal(str(solar)).quantize(Decimal("0.01"))
    voltage = Decimal(str(236.5 + math.sin(seconds / 500) * 2.2)).quantize(Decimal("0.01"))
    current = (pac1 / voltage).quantize(Decimal("0.01")) if voltage else Decimal("0.00")

    return f"""<root>
  <variable><id>pac1</id><value>{pac1}</value></variable>
  <variable><id>pac2</id><value>{pac2}</value></variable>
  <variable><id>fpot1</id><value>{fpot1}</value></variable>
  <variable><id>fpot2</id><value>1.000</value></variable>
  <variable><id>vrms1</id><value>{voltage}</value></variable>
  <variable><id>irms1</id><value>{current}</value></variable>
  <variable><id>freq1</id><value>50.00</value></variable>
  <variable><id>pact</id><value>{Decimal(str(consumption)).quantize(Decimal("0.01"))}</value></variable>
  <variable><id>ssid</id><value>red-local</value></variable>
  <variable><id>securKey</id><value>super-secret</value></variable>
</root>"""


def _pulse(hour: int, minute: int, start_hour: int, start_minute: int, duration_minutes: int, watts: int) -> float:
    current = hour * 60 + minute
    start = start_hour * 60 + start_minute
    if start <= current < start + duration_minutes:
        return float(watts)
    return 0.0
