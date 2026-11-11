from __future__ import annotations

import argparse
import ipaddress
import json
import secrets
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlencode


class WibeeeRecoveryState(StrEnum):
    OPERATIVE = "operative"
    HOME_UNREACHABLE = "home_unreachable"
    FAILURE_CONFIRMED = "failure_confirmed"
    AP_DETECTED = "ap_detected"
    AP_CONNECTING = "ap_connecting"
    CONFIGURING = "configuring"
    REBOOT_EXPECTED = "reboot_expected"
    RECONNECTING_HOME = "reconnecting_home"
    SEARCHING_HOME_METER = "searching_home_meter"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    COOLDOWN = "cooldown"


SENSITIVE_QUERY_KEYS = {
    "pwd",
    "pass",
    "password",
    "key",
    "token",
    "wibeee_target_wifi_password",
    "target_password",
}


@dataclass(frozen=True)
class WibeeeWifiConfig:
    ssid: str
    password: str
    security: int
    typekey: int = 2


@dataclass(frozen=True)
class WibeeeNetworkConfig:
    name: str = "WIBEEE"
    dhcp: bool = True
    ip: str = "192.168.1.150"
    gateway: str = "192.168.1.1"
    subnet: str = "255.255.255.0"
    dns1: str = "8.8.8.8"
    dns2: str = "8.8.4.4"


def ipv4_to_hex(value: str) -> str:
    return "".join(f"{octet:02x}" for octet in ipaddress.IPv4Address(value).packed)


def port_to_hex(value: int | str) -> str:
    port = int(value)
    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    return f"{port:x}"


def security_to_code(value: str | int) -> int:
    if isinstance(value, int):
        if value not in {0, 1, 2, 3, 5, 6}:
            raise ValueError(f"unsupported WiBeee security code: {value}")
        return value

    normalized = value.strip().upper().replace("_", "-")
    if normalized in {"0", "OPEN", "NONE", "--"}:
        return 0
    if normalized in {"1", "WEP", "WEP-64", "WEP 64 BITS"}:
        return 1
    if normalized in {"2", "WEP-128", "WEP 128 BITS"}:
        return 2
    if normalized in {"3", "WPA", "WPA-PSK"}:
        return 3
    if normalized in {"5", "WPA2", "WPA2-PSK", "WPA2 PERSONAL"}:
        return 5
    if normalized in {"6", "WPA/WPA2", "WPA-WPA2", "WPA/WPA2-PSK", "MIXED", "WPA WPA2"}:
        return 6
    if "WPA3" in normalized or "802.1X" in normalized or "ENTERPRISE" in normalized:
        raise ValueError("WPA3/EAP networks are not supported by the observed WiBeee firmware")
    if "WPA2" in normalized and "WPA" in normalized:
        return 6
    if "WPA2" in normalized:
        return 5
    if "WPA" in normalized:
        return 3
    if "WEP" in normalized:
        return 1
    raise ValueError(f"unsupported Wi-Fi security value: {value}")


def cache_buster() -> str:
    return str(secrets.randbelow(900_000) + 100_000)


def build_path(path: str, params: dict[str, str | int | bool]) -> str:
    encoded = urlencode({key: _query_value(value) for key, value in params.items()}, doseq=False)
    return f"{path}?{encoded}" if encoded else path


def login_path(username: str, password: str, *, request_id: str | None = None) -> str:
    params: dict[str, str | int | bool] = {"user": username, "pwd": password}
    if request_id is not None:
        params["id"] = request_id
    return build_path("/en/loginRedirect.html", params)


def scan_paths(*, request_id: str | None = None, rnd: str | None = None) -> list[str]:
    request_id = request_id or cache_buster()
    rnd = rnd or cache_buster()
    return [
        build_path("/scan.cgi", {"scan": 1, "id": request_id}),
        build_path("/scan.cgi", {"getAllBss": 1, "id": request_id}),
        build_path("/scanallresults.xml", {"rnd": rnd}),
    ]


def network_config_path(config: WibeeeNetworkConfig, *, request_id: str | None = None) -> str:
    return build_path(
        "/config_value",
        {
            "name": config.name,
            "dhcp": str(config.dhcp).lower(),
            "ip": ipv4_to_hex(config.ip),
            "gw": ipv4_to_hex(config.gateway),
            "subnet": ipv4_to_hex(config.subnet),
            "dns1": ipv4_to_hex(config.dns1),
            "dns2": ipv4_to_hex(config.dns2),
            "id": request_id or cache_buster(),
        },
    )


def wifi_config_paths(config: WibeeeWifiConfig, *, request_id: str | None = None) -> list[str]:
    first_id = request_id or cache_buster()
    second_id = cache_buster()
    return [
        build_path(
            "/config_value",
            {
                "ssid": config.ssid,
                "security": config.security,
                "typekey": config.typekey,
                "id": first_id,
            },
        ),
        build_path("/config_value", {"pass": config.password, "id": second_id}),
    ]


def server_config_path(server: str, port: int | str, *, request_id: str | None = None) -> str:
    return build_path(
        "/configura_server",
        {
            "URLServidor": server,
            "portServidor": port_to_hex(port),
            "id": request_id or cache_buster(),
        },
    )


def reset_path(*, request_id: str | None = None) -> str:
    return build_path("/config_value", {"reset": "true", "id": request_id or cache_buster()})


def redact_url(value: str) -> str:
    if "?" not in value:
        return value
    path, query = value.split("?", 1)
    parts: list[str] = []
    for item in query.split("&"):
        if "=" not in item:
            parts.append(item)
            continue
        key, raw_value = item.split("=", 1)
        parts.append(f"{key}=<redacted>" if key.lower() in SENSITIVE_QUERY_KEYS else f"{key}={raw_value}")
    return f"{path}?{'&'.join(parts)}"


def looks_like_successful_login(html: str) -> bool:
    lowered = html.lower()
    if "loginerror" in lowered or "incorrect" in lowered or "invalid" in lowered:
        return False
    return "/en/index.html" in lowered or "index.html" in lowered


def _query_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Build WiBeee firmware HTTP paths without logging secrets.")
    sub = parser.add_subparsers(dest="command", required=True)

    wifi = sub.add_parser("wifi-paths")
    wifi.add_argument("--ssid", required=True)
    wifi.add_argument("--password", required=True)
    wifi.add_argument("--security", required=True)
    wifi.add_argument("--typekey", default="2")

    network = sub.add_parser("network-path")
    network.add_argument("--name", default="WIBEEE")
    network.add_argument("--dhcp", default="true")
    network.add_argument("--ip", required=True)
    network.add_argument("--gateway", required=True)
    network.add_argument("--subnet", required=True)
    network.add_argument("--dns1", required=True)
    network.add_argument("--dns2", required=True)

    login = sub.add_parser("login-path")
    login.add_argument("--username", required=True)
    login.add_argument("--password", required=True)

    sub.add_parser("scan-paths")
    sub.add_parser("reset-path")

    redact = sub.add_parser("redact")
    redact.add_argument("url")

    args = parser.parse_args()
    if args.command == "wifi-paths":
        paths = wifi_config_paths(
            WibeeeWifiConfig(
                ssid=args.ssid,
                password=args.password,
                security=security_to_code(args.security),
                typekey=int(args.typekey),
            )
        )
        print(json.dumps(paths))
    elif args.command == "network-path":
        path = network_config_path(
            WibeeeNetworkConfig(
                name=args.name,
                dhcp=args.dhcp.lower() == "true",
                ip=args.ip,
                gateway=args.gateway,
                subnet=args.subnet,
                dns1=args.dns1,
                dns2=args.dns2,
            )
        )
        print(path)
    elif args.command == "login-path":
        print(login_path(args.username, args.password))
    elif args.command == "scan-paths":
        print(json.dumps(scan_paths()))
    elif args.command == "reset-path":
        print(reset_path())
    elif args.command == "redact":
        print(redact_url(args.url))


if __name__ == "__main__":
    _main()
