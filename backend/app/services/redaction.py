from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_FIELD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"secur",
        r"secret",
        r"ssid",
        r"wifi",
        r"password",
        r"passwd",
        r"\bpass\b",
        r"token",
        r"api[_-]?key",
        r"\bkey\b",
        r"\bmac\b",
        r"ip(addr(ess)?)?$",
        r"gateway",
        r"netmask",
        r"dns",
    ]
]

SECRET_VALUE_PATTERNS = [
    re.compile(r"([A-F0-9]{2}:){5}[A-F0-9]{2}", re.IGNORECASE),
    re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[0-1])|192\.168)\.\d{1,3}\.\d{1,3}\b"),
]


def is_sensitive_field(name: str | None) -> bool:
    if not name:
        return False
    normalized = name.strip()
    return any(pattern.search(normalized) for pattern in SENSITIVE_FIELD_PATTERNS)


def redact_scalar(field_name: str | None, value: Any) -> Any:
    if value is None:
        return None
    if is_sensitive_field(field_name):
        return REDACTED
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_VALUE_PATTERNS:
            redacted = pattern.sub(REDACTED, redacted)
        return redacted
    return value


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in values.items():
        if isinstance(value, Mapping):
            output[key] = redact_mapping(value)
        elif isinstance(value, list):
            output[key] = [redact_mapping(item) if isinstance(item, Mapping) else redact_scalar(key, item) for item in value]
        else:
            output[key] = redact_scalar(key, value)
    return output


def redact_xml(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        redacted = xml_text
        for pattern in SECRET_VALUE_PATTERNS:
            redacted = pattern.sub(REDACTED, redacted)
        return redacted

    for variable in root.iter():
        tag_name = _strip_namespace(variable.tag)
        if is_sensitive_field(tag_name):
            variable.text = REDACTED
            continue

        if tag_name == "variable":
            id_node = variable.find("id")
            value_node = variable.find("value")
            variable_id = id_node.text if id_node is not None else None
            if value_node is not None and is_sensitive_field(variable_id):
                value_node.text = REDACTED
        elif variable.text:
            variable.text = str(redact_scalar(tag_name, variable.text))

    return ET.tostring(root, encoding="unicode")


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag
