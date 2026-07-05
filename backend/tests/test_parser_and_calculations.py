from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services.calculations import calculate_power, integrate_energy
from app.services.meter_parser import parse_meter_xml


def test_confirmed_export_case() -> None:
    derived = calculate_power(Decimal("2954.41"), Decimal("3409.05"), Decimal("-1.000"))
    assert derived.solar_w == Decimal("3409.050")
    assert derived.grid_export_w == Decimal("2954.410")
    assert derived.grid_import_w == Decimal("0.000")
    assert derived.house_consumption_w == Decimal("454.640")


def test_xml_parser_redacts_sensitive_fields() -> None:
    parsed = parse_meter_xml(
        """
        <root>
          <variable><id>pac1</id><value>2954.41</value></variable>
          <variable><id>pac2</id><value>3409.05</value></variable>
          <variable><id>fpot1</id><value>-1.000</value></variable>
          <variable><id>securKey</id><value>abc123</value></variable>
          <variable><id>ssid</id><value>mi-wifi</value></variable>
        </root>
        """
    )
    assert parsed.data_quality == "valid"
    assert "abc123" not in parsed.raw_payload_redacted
    assert "mi-wifi" not in parsed.raw_payload_redacted
    assert parsed.raw_variables["securKey"] == "[REDACTED]"


def test_invalid_sentinel_discards_calculations() -> None:
    parsed = parse_meter_xml(
        """
        <root>
          <variable><id>pac1</id><value>9223372036854775807</value></variable>
          <variable><id>pac2</id><value>3409.05</value></variable>
          <variable><id>fpot1</id><value>-1.000</value></variable>
        </root>
        """
    )
    assert parsed.data_quality == "invalid"
    assert parsed.derived is None


def test_corrupt_xml_returns_invalid_payload() -> None:
    parsed = parse_meter_xml("<root><variable>")
    assert parsed.data_quality == "invalid"
    assert parsed.error_message is not None


def test_parser_strips_nul_bytes_before_parsing() -> None:
    parsed = parse_meter_xml(
        "<values><variable><id>pac1</id><value>10\x00</value></variable><variable><id>pac2</id><value>20</value></variable><variable><id>fpot1</id><value>1.000</value></variable></values>"
    )
    assert parsed.data_quality == "valid"
    assert parsed.pac1 == Decimal("10")


def test_energy_uses_real_elapsed_seconds() -> None:
    previous = calculate_power(Decimal("0"), Decimal("1000"), Decimal("0"))
    current = calculate_power(Decimal("0"), Decimal("1000"), Decimal("0"))
    interval = integrate_energy(
        datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
        datetime(2026, 7, 2, 10, 1, 30, tzinfo=UTC),
        previous,
        current,
        max_complete_interval_seconds=180,
    )
    assert interval.is_complete
    assert interval.solar_kwh == Decimal("0.025000")


def test_large_gap_is_incomplete_and_not_interpolated() -> None:
    power = calculate_power(Decimal("0"), Decimal("1000"), Decimal("0"))
    interval = integrate_energy(
        datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
        datetime(2026, 7, 2, 10, 10, tzinfo=UTC),
        power,
        power,
        max_complete_interval_seconds=180,
    )
    assert not interval.is_complete
    assert interval.solar_kwh == Decimal("0")
    assert interval.reason == "gap_too_large"
