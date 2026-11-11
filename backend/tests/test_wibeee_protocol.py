import pytest

from app.services.wibeee_protocol import (
    WibeeeNetworkConfig,
    WibeeeRecoveryState,
    WibeeeWifiConfig,
    ipv4_to_hex,
    login_path,
    looks_like_successful_login,
    network_config_path,
    port_to_hex,
    redact_url,
    reset_path,
    scan_paths,
    security_to_code,
    server_config_path,
    wifi_config_paths,
)


def test_ipv4_and_port_are_encoded_as_observed_by_firmware() -> None:
    assert ipv4_to_hex("192.168.1.150") == "c0a80196"
    assert ipv4_to_hex("192.168.1.1") == "c0a80101"
    assert ipv4_to_hex("255.255.255.0") == "ffffff00"
    assert ipv4_to_hex("8.8.8.8") == "08080808"
    assert port_to_hex(8080) == "1f90"


def test_security_mapping_uses_observed_wibeee_codes() -> None:
    assert security_to_code("OPEN") == 0
    assert security_to_code("WEP 64 Bits") == 1
    assert security_to_code("WEP 128 Bits") == 2
    assert security_to_code("WPA-PSK") == 3
    assert security_to_code("WPA2-PSK") == 5
    assert security_to_code("WPA/WPA2-PSK Mixed") == 6
    assert security_to_code("WPA1 WPA2") == 6


def test_unsupported_enterprise_security_fails_closed() -> None:
    with pytest.raises(ValueError, match="not supported"):
        security_to_code("WPA3 Enterprise 802.1X")


def test_wifi_paths_encode_special_characters_and_do_not_inline_spaces() -> None:
    paths = wifi_config_paths(
        WibeeeWifiConfig(
            ssid="Casa 2G ñ & symbols",
            password="p@ ss+ñ&=",
            security=5,
            typekey=2,
        ),
        request_id="123",
    )

    assert paths[0].startswith("/config_value?ssid=Casa+2G+%C3%B1+%26+symbols&security=5&typekey=2&id=123")
    assert paths[1].startswith("/config_value?pass=p%40+ss%2B%C3%B1%26%3D&id=")


def test_network_and_server_paths_match_observed_format() -> None:
    path = network_config_path(
        WibeeeNetworkConfig(
            name="WIBEEE",
            dhcp=True,
            ip="192.168.1.150",
            gateway="192.168.1.1",
            subnet="255.255.255.0",
            dns1="8.8.8.8",
            dns2="8.8.4.4",
        ),
        request_id="77",
    )
    assert path == (
        "/config_value?name=WIBEEE&dhcp=true&ip=c0a80196&gw=c0a80101&subnet=ffffff00"
        "&dns1=08080808&dns2=08080404&id=77"
    )
    assert server_config_path("www.smilics.com", 8080, request_id="88") == (
        "/configura_server?URLServidor=www.smilics.com&portServidor=1f90&id=88"
    )


def test_login_scan_and_reset_paths() -> None:
    assert login_path("admin", "secret", request_id="1") == "/en/loginRedirect.html?user=admin&pwd=secret&id=1"
    assert scan_paths(request_id="2", rnd="3") == [
        "/scan.cgi?scan=1&id=2",
        "/scan.cgi?getAllBss=1&id=2",
        "/scanallresults.xml?rnd=3",
    ]
    assert reset_path(request_id="4") == "/config_value?reset=true&id=4"


def test_login_validation_requires_redirect_to_index_without_error_markers() -> None:
    assert looks_like_successful_login("<script>window.location.href='/en/index.html'</script>")
    assert not looks_like_successful_login("<html>loginError</html>")


def test_secret_redaction_covers_sensitive_query_keys() -> None:
    assert redact_url("/config_value?ssid=Casa&pass=secret&id=1") == "/config_value?ssid=Casa&pass=<redacted>&id=1"
    assert redact_url("/en/loginRedirect.html?user=admin&pwd=secret") == (
        "/en/loginRedirect.html?user=admin&pwd=<redacted>"
    )


def test_recovery_state_sequence_names_cover_operational_flow() -> None:
    assert [state.value for state in WibeeeRecoveryState] == [
        "operative",
        "home_unreachable",
        "failure_confirmed",
        "ap_detected",
        "ap_connecting",
        "configuring",
        "reboot_expected",
        "reconnecting_home",
        "searching_home_meter",
        "validating",
        "completed",
        "failed",
        "cooldown",
    ]
