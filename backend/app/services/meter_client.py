from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import get_settings
from app.services.simulator import simulated_meter_xml


@dataclass(frozen=True)
class MeterFetchResult:
    payload: str
    duration_ms: int
    source: str


async def fetch_meter_payload() -> MeterFetchResult:
    settings = get_settings()
    start = time.perf_counter()
    if settings.simulation_mode:
        payload = simulated_meter_xml()
        return MeterFetchResult(
            payload=payload,
            duration_ms=int((time.perf_counter() - start) * 1000),
            source="simulator",
        )

    last_error: str | None = None

    timeout = httpx.Timeout(
        timeout=settings.meter_request_timeout_seconds,
        connect=settings.meter_request_timeout_seconds,
        read=settings.meter_request_timeout_seconds,
        write=settings.meter_request_timeout_seconds,
        pool=settings.meter_request_timeout_seconds,
    )
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=0, keepalive_expiry=0.0)
    headers = {"Connection": "close"}

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        headers=headers,
        follow_redirects=False,
    ) as client:
        device_ids = [settings.meter_device_id.strip()] if settings.meter_device_id and settings.meter_device_id.strip() else []
        if not device_ids:
            for discovered_id in await _discover_meter_device_ids(
                client,
                settings.meter_url,
                devices_path=settings.meter_devices_path,
            ):
                if discovered_id not in device_ids:
                    device_ids.append(discovered_id)

        candidate_urls = _meter_request_urls(
            settings.meter_url,
            values_path=settings.meter_values_path,
            device_ids=device_ids,
        )
        for attempt in range(settings.meter_request_attempts):
            for url in candidate_urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    last_error = f"{url}: {exc}"
                    continue

                payload = _extract_xml_payload(response.text)
                if payload is not None:
                    return MeterFetchResult(
                        payload=payload,
                        duration_ms=int((time.perf_counter() - start) * 1000),
                        source="meter",
                    )

                last_error = f"{url}: respuesta sin XML util"

            if attempt + 1 < settings.meter_request_attempts:
                await asyncio.sleep(settings.meter_request_retry_delay_seconds * (attempt + 1))

    detail = last_error or "sin respuesta del medidor"
    raise RuntimeError(f"No se pudo obtener XML del medidor: {detail}")


def _meter_request_urls(base_url: str, *, values_path: str, device_ids: list[str]) -> list[str]:
    urls: list[str] = []
    split = urlsplit(base_url)
    root_like = split.path in {"", "/"}

    if root_like:
        xml_url = urljoin(base_url.rstrip("/") + "/", values_path.lstrip("/"))
        urls.extend(_candidate_urls_with_optional_ids(xml_url, device_ids))
        if not device_ids:
            urls.append(base_url)
    else:
        urls.extend(_candidate_urls_with_optional_ids(base_url, device_ids))

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            deduped.append(url)
            seen.add(url)
    return deduped


def _candidate_urls_with_optional_ids(url: str, device_ids: list[str]) -> list[str]:
    if not device_ids:
        return [url]

    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    if "id" in query:
        return [url]

    urls: list[str] = []
    for candidate_id in device_ids:
        candidate_query = dict(query)
        candidate_query["id"] = candidate_id
        urls.append(urlunsplit((split.scheme, split.netloc, split.path, urlencode(candidate_query), split.fragment)))
    return urls


async def _discover_meter_device_ids(client: httpx.AsyncClient, base_url: str, *, devices_path: str) -> list[str]:
    split = urlsplit(base_url)
    if split.path not in {"", "/"}:
        return []

    devices_url = urljoin(base_url.rstrip("/") + "/", devices_path.lstrip("/"))
    try:
        response = await client.get(devices_url)
        response.raise_for_status()
    except httpx.HTTPError:
        return []

    payload = _extract_xml_payload(response.text)
    if payload is None:
        return []
    return _extract_device_ids(payload)


def _extract_xml_payload(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None

    markers = (
        stripped.find("<?xml"),
        stripped.find("<root"),
        stripped.find("<values"),
        stripped.find("<devices"),
    )
    xml_start = min((idx for idx in markers if idx >= 0), default=-1)
    if xml_start >= 0:
        stripped = stripped[xml_start:]
        for closing_tag in ("</root>", "</values>", "</devices>"):
            end_idx = stripped.rfind(closing_tag)
            if end_idx >= 0:
                candidate = stripped[: end_idx + len(closing_tag)]
                return None if _is_empty_values_payload(candidate) else candidate
        return None if _is_empty_values_payload(stripped) else stripped

    lowered = stripped.lower()
    if "<html" in lowered or "login.html" in lowered or "window.location.href" in lowered:
        return None
    return None


def _extract_device_ids(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ids: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1].lower()
        if tag in {"id", "deviceid", "identifier"} and node.text:
            value = node.text.strip()
            if value:
                ids.append(value)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in ids:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _is_empty_values_payload(xml_text: str) -> bool:
    normalized = "".join(xml_text.split()).lower()
    if normalized.startswith("<?xml"):
        declaration_end = normalized.find("?>")
        if declaration_end >= 0:
            normalized = normalized[declaration_end + 2 :]
    return normalized in {"<values/>", "<values></values>"}
