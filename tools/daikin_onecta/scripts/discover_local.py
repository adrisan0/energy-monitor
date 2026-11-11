"""Non-invasive Daikin UDP discovery and legacy read-only API check."""
from __future__ import annotations

import argparse
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


DISCOVERY_PAYLOAD = b"DAIKIN_UDP/common/basic_info"


def parse_fields(payload: bytes) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in payload.decode("ascii", "replace").strip().split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            fields[key] = value
    return fields


def discover(broadcast: str, timeout: float = 2.0) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.25)
        sock.sendto(DISCOVERY_PAYLOAD, (broadcast, 30050))
        end_at = time.monotonic() + timeout
        while time.monotonic() < end_at:
            try:
                payload, (address, _port) = sock.recvfrom(2048)
            except socket.timeout:
                continue
            fields = parse_fields(payload)
            if fields.get("ret") == "OK":
                found[address] = fields
    return found


def check_read(host: str, path: str, scheme: str) -> tuple[int | None, str]:
    try:
        with urlopen(f"{scheme}://{host}{path}", timeout=1.5) as response:
            return response.status, response.read(600).decode("utf-8", "replace")
    except HTTPError as exc:
        return exc.code, exc.read(600).decode("utf-8", "replace")
    except (TimeoutError, URLError, OSError) as exc:
        return None, type(exc).__name__


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broadcast", default="255.255.255.255", help="IPv4 broadcast address for the LAN")
    args = parser.parse_args()
    devices = discover(args.broadcast)
    if not devices:
        print("No Daikin discovery replies received.")
        return
    for host, fields in sorted(devices.items()):
        labels = ("type", "reg", "ver", "adp_kind", "adp_mode", "method", "ssid")
        summary = " ".join(f"{key}={fields[key]}" for key in labels if fields.get(key))
        print(f"Discovered {host}: {summary}")
        for scheme, path in (("http", "/common/basic_info"),
                             ("http", "/aircon/get_control_info"),
                             ("https", "/common/basic_info")):
            status, detail = check_read(host, path, scheme)
            if status is None:
                print(f"  GET {scheme}://{host}{path}: no response ({detail})")
            else:
                print(f"  GET {scheme}://{host}{path}: HTTP {status}; {detail[:180]}")


if __name__ == "__main__":
    main()
