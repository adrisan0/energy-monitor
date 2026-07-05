from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models import EnergyAggregate
from app.services.aggregates import period_bounds
from app.services.exporter import iter_measurement_csv
from app.services.meter_parser import parse_meter_xml
from app.services.samples import store_parsed_payload
from app.services.tariffs import estimate_financials, get_or_create_tariff

XML = """
<root>
  <variable><id>pac1</id><value>0</value></variable>
  <variable><id>pac2</id><value>1200</value></variable>
  <variable><id>fpot1</id><value>0</value></variable>
  <variable><id>ssid</id><value>casa</value></variable>
</root>
"""


def test_daily_and_monthly_aggregation() -> None:
    with get_session_factory()() as db:
        first = parse_meter_xml(XML, timestamp_utc=datetime(2026, 7, 2, 10, 0, tzinfo=UTC))
        second = parse_meter_xml(XML, timestamp_utc=datetime(2026, 7, 2, 10, 1, tzinfo=UTC))
        store_parsed_payload(db, first, poll_duration_ms=12)
        store_parsed_payload(db, second, poll_duration_ms=10)
        db.commit()
        day = db.scalar(select(EnergyAggregate).where(EnergyAggregate.period == "day"))
        month = db.scalar(select(EnergyAggregate).where(EnergyAggregate.period == "month"))
        assert day is not None
        assert month is not None
        assert day.solar_kwh == Decimal("0.020000")
        assert month.solar_kwh == Decimal("0.020000")


def test_dst_day_boundary_in_spain_has_real_utc_duration() -> None:
    start, end = period_bounds(datetime(2026, 3, 29, 12, 0, tzinfo=UTC), "day")
    assert (end - start).total_seconds() == 23 * 3600


def test_tariff_economic_calculation() -> None:
    with get_session_factory()() as db:
        tariff = get_or_create_tariff(db)
        money = estimate_financials(
            tariff=tariff,
            local_start=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
            local_end=datetime(2026, 7, 3, 0, 0, tzinfo=UTC),
            grid_import_kwh=Decimal("10"),
            grid_export_kwh=Decimal("5"),
        )
        assert money["estimated_cost_eur"] > Decimal("0")
        assert money["compensation_eur"] == Decimal("0.300000")
        assert money["net_cost_eur"] > Decimal("0")


def test_csv_export_excludes_sensitive_payload() -> None:
    with get_session_factory()() as db:
        parsed = parse_meter_xml(XML, timestamp_utc=datetime(2026, 7, 2, 10, 0, tzinfo=UTC))
        store_parsed_payload(db, parsed, poll_duration_ms=12)
        db.commit()
        csv_text = "".join(iter_measurement_csv(db, start=None, end=None, data_quality=None))
        assert "ssid" not in csv_text
        assert "casa" not in csv_text
        assert "solar_w" in csv_text
