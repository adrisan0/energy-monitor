from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.timezone import local_date_time, utc_now
from app.services.calculations import DerivedPower, calculate_power, is_invalid_decimal
from app.services.redaction import REDACTED, is_sensitive_field, redact_mapping, redact_xml

REQUIRED_FIELDS = ("pac1", "pac2", "fpot1")


@dataclass(frozen=True)
class ParsedMeterPayload:
    timestamp_utc: datetime
    timestamp_local: datetime
    raw_variables: dict[str, Any]
    raw_payload_redacted: str
    payload_hash: str
    data_quality: str
    error_message: str | None
    derived: DerivedPower | None
    pac1: Decimal | None
    pac2: Decimal | None
    fpot1: Decimal | None
    fpot2: Decimal | None
    pact: Decimal | None
    voltage_v: Decimal | None
    current_a: Decimal | None
    frequency_hz: Decimal | None
    power_factor: Decimal | None


def parse_meter_xml(xml_text: str, *, timestamp_utc: datetime | None = None) -> ParsedMeterPayload:
    xml_text = xml_text.replace("\x00", "")
    timestamp = timestamp_utc or utc_now()
    timestamp_local, _, _ = local_date_time(timestamp)
    payload_hash = hashlib.sha256(xml_text.encode("utf-8", errors="replace")).hexdigest()
    redacted_xml = redact_xml(xml_text)

    try:
        variables = _extract_variables(xml_text)
    except ET.ParseError as exc:
        return ParsedMeterPayload(
            timestamp_utc=timestamp,
            timestamp_local=timestamp_local,
            raw_variables={},
            raw_payload_redacted=redacted_xml,
            payload_hash=payload_hash,
            data_quality="invalid",
            error_message=f"xml_corrupto: {exc}",
            derived=None,
            pac1=None,
            pac2=None,
            fpot1=None,
            fpot2=None,
            pact=None,
            voltage_v=None,
            current_a=None,
            frequency_hz=None,
            power_factor=None,
        )

    parsed_values: dict[str, Decimal | str | None] = {}
    invalid_fields: list[str] = []
    for key, value in variables.items():
        if is_sensitive_field(key):
            parsed_values[key] = REDACTED
            continue
        parsed = _to_decimal_or_text(value)
        if parsed == Decimal("9223372036854775807"):
            parsed_values[key] = None
            invalid_fields.append(key)
        else:
            parsed_values[key] = parsed

    raw_variables = redact_mapping({key: _json_safe(value) for key, value in parsed_values.items()})
    pac1 = _decimal_value(parsed_values.get("pac1"))
    pac2 = _decimal_value(parsed_values.get("pac2"))
    fpot1 = _decimal_value(parsed_values.get("fpot1"))
    fpot2 = _decimal_value(parsed_values.get("fpot2"))
    pact = _decimal_value(parsed_values.get("pact"))
    voltage_v = _decimal_value(parsed_values.get("vrms1") or parsed_values.get("voltage_v"))
    current_a = _decimal_value(parsed_values.get("irms1") or parsed_values.get("current_a"))
    frequency_hz = _decimal_value(parsed_values.get("freq1") or parsed_values.get("frequency_hz"))
    power_factor = fpot1

    missing = [field for field in REQUIRED_FIELDS if is_invalid_decimal(_decimal_value(parsed_values.get(field)))]
    if missing:
        reason_bits = []
        if invalid_fields:
            reason_bits.append(f"valores_invalidos={','.join(invalid_fields)}")
        reason_bits.append(f"faltan_campos={','.join(missing)}")
        return ParsedMeterPayload(
            timestamp_utc=timestamp,
            timestamp_local=timestamp_local,
            raw_variables=raw_variables,
            raw_payload_redacted=redacted_xml,
            payload_hash=payload_hash,
            data_quality="invalid",
            error_message="; ".join(reason_bits),
            derived=None,
            pac1=pac1,
            pac2=pac2,
            fpot1=fpot1,
            fpot2=fpot2,
            pact=pact,
            voltage_v=voltage_v,
            current_a=current_a,
            frequency_hz=frequency_hz,
            power_factor=power_factor,
        )

    assert pac1 is not None
    assert pac2 is not None
    assert fpot1 is not None
    quality = "partial" if invalid_fields else "valid"
    message = f"valores_invalidos={','.join(invalid_fields)}" if invalid_fields else None

    return ParsedMeterPayload(
        timestamp_utc=timestamp,
        timestamp_local=timestamp_local,
        raw_variables=raw_variables,
        raw_payload_redacted=redacted_xml,
        payload_hash=payload_hash,
        data_quality=quality,
        error_message=message,
        derived=calculate_power(pac1=pac1, pac2=pac2, fpot1=fpot1),
        pac1=pac1,
        pac2=pac2,
        fpot1=fpot1,
        fpot2=fpot2,
        pact=pact,
        voltage_v=voltage_v,
        current_a=current_a,
        frequency_hz=frequency_hz,
        power_factor=power_factor,
    )


def _extract_variables(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    variables: dict[str, str] = {}
    for variable in root.findall(".//variable"):
        id_node = variable.find("id")
        value_node = variable.find("value")
        if id_node is not None and id_node.text:
            variables[id_node.text.strip()] = "" if value_node is None or value_node.text is None else value_node.text.strip()

    if not variables:
        for child in root.iter():
            tag = _strip_namespace(child.tag)
            if child.text and tag not in {"variable", "id", "value"}:
                variables[tag] = child.text.strip()
    return variables


def _to_decimal_or_text(value: str) -> Decimal | str | None:
    if value == "":
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return value


def _decimal_value(value: Decimal | str | None) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    return None


def _json_safe(value: Decimal | str | None) -> str | None:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag
