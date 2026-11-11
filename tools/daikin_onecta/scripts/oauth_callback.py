"""Local ONECTA OIDC callback for a temporary Cloudflare Quick Tunnel.

The callback validates OAuth state, exchanges the authorization code using the
documented ONECTA token endpoint, stores credentials encrypted with Windows
DPAPI, then performs read-only device enumeration. It never logs query strings
or token payloads.
"""
from __future__ import annotations

import ctypes
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from dotenv import dotenv_values


AUTHORIZE_URL = "https://idp.onecta.daikineurope.com/v1/oidc/authorize"
TOKEN_URL = "https://idp.onecta.daikineurope.com/v1/oidc/token"
API_BASE = "https://api.onecta.daikineurope.com/v1"
CALLBACK_PATH = "/oauth/daikin/callback"
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765


class DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes) -> tuple[DataBlob, object]:
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def protect(data: bytes) -> bytes:
    """Encrypt data for the current Windows user via DPAPI."""
    if os.name != "nt":
        raise RuntimeError("El almacenamiento DPAPI requiere Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source, keepalive = _blob(data)
    target = DataBlob()
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(DataBlob), wintypes.LPCWSTR,
                                         ctypes.POINTER(DataBlob), ctypes.c_void_p,
                                         ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(ctypes.byref(source), "Energy Home Daikin", None,
                                    None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)
        del keepalive


def unprotect(data: bytes) -> bytes:
    """Decrypt data protected for the current Windows user via DPAPI."""
    if os.name != "nt":
        raise RuntimeError("El almacenamiento DPAPI requiere Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source, keepalive = _blob(data)
    target = DataBlob()
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(DataBlob),
                                          ctypes.POINTER(wintypes.LPWSTR),
                                          ctypes.POINTER(DataBlob), ctypes.c_void_p,
                                          ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None,
                                      None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)
        del keepalive


def data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    directory = base / "EnergyHome" / "Daikin"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def config() -> dict[str, str]:
    path = Path(os.environ.get("DAIKIN_ENV_FILE", data_dir() / ".env"))
    if not path.exists():
        if os.environ.get("DAIKIN_ENV_FILE"):
            raise RuntimeError(f"No existe el archivo de configuración indicado: {path}")
        path.write_text(
            "DAIKIN_CLIENT_ID=\nDAIKIN_CLIENT_SECRET=\n"
            f"DAIKIN_REDIRECT_URI={os.environ.get('DAIKIN_REDIRECT_URI', '')}\n",
            encoding="utf-8",
        )
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    values = {k: str(v or "") for k, v in dotenv_values(path).items()}
    # Permit a one-run redirect override when an existing project .env contains
    # a different callback. This does not alter the user's source config file.
    if os.environ.get("DAIKIN_REDIRECT_URI"):
        values["DAIKIN_REDIRECT_URI"] = os.environ["DAIKIN_REDIRECT_URI"]
    for key in ("DAIKIN_CLIENT_ID", "DAIKIN_CLIENT_SECRET", "DAIKIN_REDIRECT_URI"):
        if not values.get(key):
            raise RuntimeError(f"Falta {key} en {path}")
    values["DAIKIN_REDIRECT_URI"] = values["DAIKIN_REDIRECT_URI"].rstrip("/")
    if not values["DAIKIN_REDIRECT_URI"].startswith("https://") or not values["DAIKIN_REDIRECT_URI"].endswith(CALLBACK_PATH):
        raise RuntimeError(f"DAIKIN_REDIRECT_URI debe ser una URL HTTPS terminada en {CALLBACK_PATH}")
    return values


def save_tokens(config_values: dict[str, str], token_values: dict[str, object]) -> Path:
    payload = json.dumps({
        "client_id": config_values["DAIKIN_CLIENT_ID"],
        "client_secret": config_values["DAIKIN_CLIENT_SECRET"],
        "redirect_uri": config_values["DAIKIN_REDIRECT_URI"],
        "refresh_token": token_values["refresh_token"],
        "saved_at": int(time.time()),
    }, separators=(",", ":")).encode("utf-8")
    path = data_dir() / "credentials.dpapi"
    temp = path.with_suffix(".tmp")
    temp.write_bytes(protect(payload))
    os.replace(temp, path)
    # The temporary setup file is needed only for the initial exchange. Keep
    # the redirect URI but remove plaintext client credentials after DPAPI save.
    env_path = data_dir() / ".env"
    env_path.write_text(
        "DAIKIN_CLIENT_ID=\nDAIKIN_CLIENT_SECRET=\n"
        f"DAIKIN_REDIRECT_URI={config_values['DAIKIN_REDIRECT_URI']}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass
    return path


def authorize(config_values: dict[str, str], state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": config_values["DAIKIN_CLIENT_ID"],
        "redirect_uri": config_values["DAIKIN_REDIRECT_URI"],
        "scope": "openid onecta:basic.integration offline_access",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(config_values: dict[str, str], code: str) -> dict[str, object]:
    # Daikin's official portal example sends OAuth token parameters in the URL.
    params = {
        "grant_type": "authorization_code",
        "client_id": config_values["DAIKIN_CLIENT_ID"],
        "client_secret": config_values["DAIKIN_CLIENT_SECRET"],
        "code": code,
        "redirect_uri": config_values["DAIKIN_REDIRECT_URI"],
    }
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        response = client.post(TOKEN_URL, params=params)
    if response.is_error:
        raise RuntimeError(f"ONECTA token exchange returned HTTP {response.status_code}")
    result = response.json()
    if not isinstance(result, dict) or not result.get("access_token") or not result.get("refresh_token"):
        raise RuntimeError("La respuesta de token no contiene los tokens esperados.")
    return result


def list_devices(access_token: str) -> int:
    with httpx.Client(timeout=15.0) as client:
        response = client.get(f"{API_BASE}/gateway-devices",
                              headers={"Authorization": f"Bearer {access_token}"})
    if response.is_error:
        raise RuntimeError(f"ONECTA device listing returned HTTP {response.status_code}")
    data = response.json()
    rows = data if isinstance(data, list) else data.get("items", data.get("gatewayDevices", data.get("data")))
    if not isinstance(rows, list):
        raise RuntimeError("ONECTA devolvió una respuesta no reconocida al listar equipos.")
    return len(rows)


def run() -> int:
    try:
        cfg = config()
    except Exception as exc:
        print(f"Configuración incompleta: {exc}", file=sys.stderr)
        return 2

    expected_state = secrets.token_urlsafe(32)
    done = threading.Event()
    result: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path, _, query = self.path.partition("?")
            if path == "/health":
                self._reply(200, "Receptor OAuth de Energy Home listo.")
                return
            if path != CALLBACK_PATH:
                self._reply(404, "No encontrado.")
                return
            params = urllib.parse.parse_qs(query, keep_blank_values=True)
            received_state = params.get("state", [""])[0]
            if not secrets.compare_digest(received_state, expected_state):
                self._reply(400, "Respuesta OAuth rechazada: state no válido.")
                result["error"] = "state mismatch"
                done.set()
                return
            if params.get("error"):
                result["error"] = "El usuario o ONECTA canceló la autorización."
                self._reply(400, "Autorización cancelada.")
                done.set()
                return
            code = params.get("code", [""])[0]
            if not code:
                result["error"] = "ONECTA no devolvió código de autorización."
                self._reply(400, "Falta el código de autorización.")
                done.set()
                return
            try:
                tokens = exchange_code(cfg, code)
                saved = save_tokens(cfg, tokens)
                count = list_devices(str(tokens["access_token"]))
                result.update(ok=True, devices=count, saved_path=str(saved))
                self._reply(200, f"Conexión ONECTA verificada. Equipos detectados: {count}. Puedes cerrar esta ventana.")
            except Exception as exc:
                result["error"] = str(exc)
                self._reply(502, "ONECTA no completó la conexión. Revisa la consola local; no se han mostrado tokens.")
            finally:
                done.set()

        def _reply(self, status: int, message: str) -> None:
            body = ("<!doctype html><meta charset='utf-8'><title>Energy Home Daikin</title>"
                    f"<h1>{message}</h1>").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            # Never log callback paths because their query contains state and code.
            return

    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), Handler)
    server.timeout = 0.5
    print("Callback local listo. URL de autorización:")
    url = authorize(cfg, expected_state)
    print(url)
    print("Abre esa URL y revisa el consentimiento de ONECTA antes de aceptarlo.")
    threading.Thread(target=lambda: server.serve_forever(poll_interval=0.25), daemon=True).start()
    if os.environ.get("DAIKIN_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        while not done.wait(0.5):
            pass
    except KeyboardInterrupt:
        print("Flujo OAuth interrumpido; no se guardaron credenciales.")
        return 130
    finally:
        server.shutdown()
        server.server_close()
    if result.get("ok"):
        print(f"ONECTA autenticado. Equipos: {result['devices']}. Credenciales DPAPI guardadas en {result['saved_path']}.")
        return 0
    print(f"No se completó OAuth: {result.get('error', 'error desconocido')}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(run())
