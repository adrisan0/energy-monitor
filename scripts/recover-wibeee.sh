#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log() {
  printf '[recover-wibeee] %s\n' "$*" >&2
}

state() {
  local name="$1"
  local detail="${2:-}"
  local timestamp
  timestamp="$(date -Is)"
  if [[ -n "$detail" ]]; then
    log "state=$name detail=$detail ts=$timestamp"
  else
    log "state=$name ts=$timestamp"
  fi
  if [[ -n "${STATE_FILE:-}" && "$DRY_RUN" -eq 0 ]]; then
    printf '{"state":"%s","detail":"%s","timestamp":"%s"}\n' "$name" "$(printf '%s' "$detail" | sed 's/"/'\''/g')" "$timestamp" >"$STATE_FILE"
  fi
}

fail() {
  state failed "$*"
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Falta el comando requerido: $1"
}

usage() {
  cat <<'EOF'
Uso:
  ./scripts/recover-wibeee.sh [opciones]

Opciones:
  --ssid-pattern PATRON     Patron del SSID del Wibeee. Por defecto: WIBEEE
  --ssid-exact SSID         SSID exacto del Wibeee.
  --wifi-iface IFACE        Interfaz Wi-Fi a usar. Si no se indica, intenta detectarla.
  --home-connection NOMBRE  Conexion de NetworkManager a restaurar al final.
  --meter-ip IP             IP esperada del medidor tras volver a tu LAN. Por defecto: host de METER_URL o 192.168.1.43
  --ap-password CLAVE       Clave del AP del Wibeee si la tuviera.
  --target-ssid SSID        Wi-Fi destino para el Wibeee. Por defecto: la red actual del host.
  --target-password CLAVE   Clave de la Wi-Fi destino. Por defecto: WIBEEE_TARGET_WIFI_PASSWORD del .env.
  --auto                    Usa la llamada interna conocida del Wibeee para reasignar Wi-Fi.
  --monitor                 Vigila periodicamente y dispara recuperacion cuando vea el AP del Wibeee.
  --monitor-interval SEG    Intervalo de vigilancia. Por defecto: 30.
  --force                   En modo --auto ejecuta una recuperacion aunque el medidor responda en la LAN.
  --open-browser            Abre en el navegador la IP local detectada del Wibeee.
  --keep-wibeee             No vuelve automaticamente a la Wi-Fi de casa al terminar.
  --dry-run                 Solo muestra acciones, no cambia nada.
  -h, --help                Muestra esta ayuda.

Variables opcionales:
  WIBEEE_TARGET_WIFI_PASSWORD  Clave de la Wi-Fi destino para el modo --auto.
  WIBEEE_TARGET_WIFI_SSID      SSID destino fijo. Si no se define, usa la red actual del host.
  WIBEEE_AP_PREFIX             Prefijo del SSID de rescate. Por defecto: WIBEEE
  WIBEEE_MONITOR_INTERVAL      Intervalo para --monitor. Por defecto: 30
  WIBEEE_PORTAL_IP             IP del portal interno. Por defecto: 192.168.1.150
  WIBEEE_PORTAL_TIMEOUT        Timeout HTTP en segundos. Por defecto: 5
  WIBEEE_LOGIN_USER            Usuario del portal si el firmware lo exige.
  WIBEEE_LOGIN_PASSWORD        Password del portal si el firmware lo exige.
  WIBEEE_WIFI_SECURITY         Seguridad destino: OPEN, WPA-PSK, WPA2-PSK, WPA/WPA2-PSK Mixed o codigo 0/1/2/3/5/6.
  WIBEEE_WIFI_TYPEKEY          Formato de clave. Por defecto: 2 (Pass Phrase).
  WIBEEE_RECOVERY_COOLDOWN_SECONDS  Enfriamiento tras intento. Por defecto: 900.
  WIBEEE_RECOVERY_MAX_ATTEMPTS      Intentos por ejecucion. Por defecto: 2.
  WIBEEE_FAILURE_CONFIRMATION_ATTEMPTS Fallos LAN antes de confirmar recuperacion. Por defecto: 3.
  WIBEEE_LOCK_FILE             Bloqueo local. Por defecto: /tmp/energy-monitor-wibeee-recovery.lock
  WIBEEE_STATE_FILE            Estado local. Por defecto: /tmp/energy-monitor-wibeee-recovery.json

Variables opcionales para automatizacion manual avanzada:
  WIBEEE_CONFIG_URL         URL absoluta o ruta relativa sobre la IP local del Wibeee.
  WIBEEE_CONFIG_METHOD      GET o POST. Por defecto: POST.
  WIBEEE_CONFIG_DATA        Datos a enviar. Si empieza por @ se lee de un fichero.
  WIBEEE_CONFIG_CONTENT_TYPE  Content-Type. Por defecto: application/x-www-form-urlencoded

Ejemplos:
  ./scripts/recover-wibeee.sh --ssid-pattern 'WIBEEE.*3C:F4:AE' --home-connection 'Mi casa 2G'
  ./scripts/recover-wibeee.sh --auto
  ./scripts/recover-wibeee.sh --monitor --auto
  WIBEEE_CONFIG_URL=/goform/saveWifi WIBEEE_CONFIG_DATA='ssid=Casa&password=secreta' ./scripts/recover-wibeee.sh --ssid-exact 'WIBEEE_3C:F4:AE'
EOF
}

load_dotenv() {
  local env_file=".env"
  [[ -f "$env_file" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

load_dotenv

default_meter_ip() {
  if [[ -n "${METER_URL:-}" ]]; then
    printf '%s\n' "$METER_URL" | sed -nE 's#^https?://([^/:]+).*$#\1#p' | head -n1
    return 0
  fi
  printf '192.168.1.43\n'
}

SSID_PATTERN="${WIBEEE_AP_PREFIX:-WIBEEE}"
SSID_EXACT=''
WIFI_IFACE=''
HOME_CONNECTION=''
METER_IP="$(default_meter_ip)"
AP_PASSWORD=''
TARGET_SSID="${WIBEEE_TARGET_WIFI_SSID:-}"
TARGET_PASSWORD="${WIBEEE_TARGET_WIFI_PASSWORD:-}"
AUTO_CONFIG=0
MONITOR_MODE=0
MONITOR_INTERVAL="${WIBEEE_MONITOR_INTERVAL:-30}"
FORCE_RECOVERY=0
OPEN_BROWSER=0
KEEP_WIBEEE=0
DRY_RUN=0
CONFIG_URL="${WIBEEE_CONFIG_URL:-}"
CONFIG_METHOD="${WIBEEE_CONFIG_METHOD:-POST}"
CONFIG_DATA="${WIBEEE_CONFIG_DATA:-}"
CONFIG_CONTENT_TYPE="${WIBEEE_CONFIG_CONTENT_TYPE:-application/x-www-form-urlencoded}"
PORTAL_IP="${WIBEEE_PORTAL_IP:-192.168.1.150}"
PORTAL_TIMEOUT="${WIBEEE_PORTAL_TIMEOUT:-5}"
LOGIN_USER="${WIBEEE_LOGIN_USER:-}"
LOGIN_PASSWORD="${WIBEEE_LOGIN_PASSWORD:-}"
WIFI_SECURITY="${WIBEEE_WIFI_SECURITY:-WPA2-PSK}"
WIFI_TYPEKEY="${WIBEEE_WIFI_TYPEKEY:-2}"
RECOVERY_COOLDOWN_SECONDS="${WIBEEE_RECOVERY_COOLDOWN_SECONDS:-900}"
RECOVERY_MAX_ATTEMPTS="${WIBEEE_RECOVERY_MAX_ATTEMPTS:-2}"
FAILURE_CONFIRMATION_ATTEMPTS="${WIBEEE_FAILURE_CONFIRMATION_ATTEMPTS:-3}"
VALIDATION_ATTEMPTS="${WIBEEE_VALIDATION_ATTEMPTS:-30}"
VALIDATION_INTERVAL="${WIBEEE_VALIDATION_INTERVAL:-5}"
LOCK_FILE="${WIBEEE_LOCK_FILE:-/tmp/energy-monitor-wibeee-recovery.lock}"
STATE_FILE="${WIBEEE_STATE_FILE:-/tmp/energy-monitor-wibeee-recovery.json}"
COOLDOWN_FILE="${WIBEEE_COOLDOWN_FILE:-/tmp/energy-monitor-wibeee-recovery.cooldown}"
DEVICE_NAME="${WIBEEE_DEVICE_NAME:-WIBEEE}"
WIBEEE_DHCP="${WIBEEE_DHCP:-true}"
WIBEEE_STATIC_IP="${WIBEEE_STATIC_IP:-$PORTAL_IP}"
WIBEEE_GATEWAY="${WIBEEE_GATEWAY:-192.168.1.1}"
WIBEEE_SUBNET="${WIBEEE_SUBNET:-255.255.255.0}"
WIBEEE_DNS1="${WIBEEE_DNS1:-8.8.8.8}"
WIBEEE_DNS2="${WIBEEE_DNS2:-8.8.4.4}"
WIBEEE_MAC="${WIBEEE_MAC:-}"
WIBEEE_AP_HOST_ADDRESS="${WIBEEE_AP_HOST_ADDRESS:-192.168.1.151/24}"
ORIGINAL_CONNECTION=''
ORIGINAL_IFACE=''
ORIGINAL_SSID=''
CONNECTED_TO_WIBEEE=0

while (($# > 0)); do
  case "$1" in
    --ssid-pattern)
      SSID_PATTERN="${2:-}"
      shift 2
      ;;
    --ssid-exact)
      SSID_EXACT="${2:-}"
      shift 2
      ;;
    --wifi-iface)
      WIFI_IFACE="${2:-}"
      shift 2
      ;;
    --home-connection)
      HOME_CONNECTION="${2:-}"
      shift 2
      ;;
    --meter-ip)
      METER_IP="${2:-}"
      shift 2
      ;;
    --ap-password)
      AP_PASSWORD="${2:-}"
      shift 2
      ;;
    --target-ssid)
      TARGET_SSID="${2:-}"
      shift 2
      ;;
    --target-password)
      TARGET_PASSWORD="${2:-}"
      shift 2
      ;;
    --auto)
      AUTO_CONFIG=1
      shift
      ;;
    --monitor)
      MONITOR_MODE=1
      shift
      ;;
    --monitor-interval)
      MONITOR_INTERVAL="${2:-}"
      shift 2
      ;;
    --force)
      FORCE_RECOVERY=1
      shift
      ;;
    --open-browser)
      OPEN_BROWSER=1
      shift
      ;;
    --keep-wibeee)
      KEEP_WIBEEE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Opcion no reconocida: $1"
      ;;
  esac
done

require_cmd nmcli
require_cmd curl
require_cmd flock
if [[ "$AUTO_CONFIG" -eq 1 ]]; then
  require_cmd python3
fi

run() {
  log "$*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

protocol() {
  PYTHONPATH="${PYTHONPATH:-}:$REPO_ROOT/backend" python3 -m app.services.wibeee_protocol "$@"
}

redact_url() {
  protocol redact "$1"
}

curl_get() {
  local url="$1"
  local output="${2:-/dev/null}"
  local allow_failure="${3:-0}"
  local redacted
  redacted="$(redact_url "$url")"
  log "HTTP GET $redacted"
  if curl -fsS --http1.1 --connect-timeout "$PORTAL_TIMEOUT" --max-time "$PORTAL_TIMEOUT" \
    -H 'Connection: close' -o "$output" "$url"; then
    return 0
  fi
  if [[ "$allow_failure" -eq 1 ]]; then
    log "HTTP GET expected_disconnect_or_timeout url=$redacted"
    return 0
  fi
  return 1
}

with_recovery_lock() {
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    state cooldown "otra recuperacion ya esta en curso"
    exit 0
  fi
}

cooldown_active() {
  [[ -f "$COOLDOWN_FILE" ]] || return 1
  local next_allowed
  local now
  next_allowed="$(cat "$COOLDOWN_FILE" 2>/dev/null || printf '0')"
  now="$(date +%s)"
  [[ "$next_allowed" =~ ^[0-9]+$ ]] || return 1
  if ((now < next_allowed)); then
    state cooldown "siguiente intento permitido en $((next_allowed - now))s"
    return 0
  fi
  return 1
}

mark_cooldown() {
  local now
  now="$(date +%s)"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    printf '%s\n' "$((now + RECOVERY_COOLDOWN_SECONDS))" >"$COOLDOWN_FILE"
  fi
}

clear_cooldown() {
  [[ "$DRY_RUN" -eq 0 ]] && rm -f "$COOLDOWN_FILE"
}

notify_recovery() {
  local status="$1"
  local message="$2"
  if [[ -n "${WIBEEE_NOTIFY_COMMAND:-}" ]]; then
    WIBEEE_RECOVERY_STATUS="$status" WIBEEE_RECOVERY_MESSAGE="$message" bash -c "$WIBEEE_NOTIFY_COMMAND" || true
  fi
}

cleanup_connection() {
  local exit_code=$?
  if [[ "$CONNECTED_TO_WIBEEE" -eq 1 && "$KEEP_WIBEEE" -eq 0 && -n "$HOME_CONNECTION" ]]; then
    log "Cleanup: restaurando conexion domestica tras salida codigo $exit_code"
    nmcli connection up "$HOME_CONNECTION" >/dev/null 2>&1 || true
  fi
  return "$exit_code"
}

detect_wifi_iface() {
  if [[ -n "$WIFI_IFACE" ]]; then
    printf '%s\n' "$WIFI_IFACE"
    return 0
  fi
  nmcli -t -f DEVICE,TYPE,STATE device status | awk -F: '$2=="wifi" && $3!="unavailable" {print $1; exit}'
}

detect_active_connection() {
  local iface="$1"
  nmcli -t -f NAME,DEVICE,TYPE connection show --active | awk -F: -v iface="$iface" '$2==iface && $3=="802-11-wireless" {print $1; exit}'
}

detect_active_ssid() {
  local iface="$1"
  nmcli -t -f ACTIVE,SSID,DEVICE dev wifi list | \
    awk -F: -v iface="$iface" '$1=="yes" && $3==iface {print $2; exit}'
}

infer_saved_home_ssid() {
  nmcli -t -f NAME,TYPE,802-11-wireless.ssid connection show | \
    awk -F: -v pattern="$SSID_PATTERN" '
      $2=="802-11-wireless" && $3 != "" && $3 !~ pattern {
        print $3
        exit
      }
    '
}

scan_for_wibeee_ssid() {
  local iface="$1"
  local list
  run nmcli dev wifi rescan ifname "$iface"
  list="$(nmcli -t -f SSID device wifi list ifname "$iface" | sed 's/\\:/:/g' | sed '/^$/d' || true)"
  if [[ -n "$SSID_EXACT" ]]; then
    printf '%s\n' "$list" | awk -v ssid="$SSID_EXACT" '$0==ssid {print; exit}'
    return 0
  fi
  printf '%s\n' "$list" | grep -E -m1 "$SSID_PATTERN" || true
}

connect_to_ssid() {
  local iface="$1"
  local ssid="$2"
  if [[ -n "$AP_PASSWORD" ]]; then
    if run nmcli dev wifi connect "$ssid" password "$AP_PASSWORD" ifname "$iface"; then
      return 0
    fi
  else
    if run nmcli dev wifi connect "$ssid" ifname "$iface"; then
      return 0
    fi
  fi
  log "Conexion DHCP al AP fallida; reintentando con IP manual $WIBEEE_AP_HOST_ADDRESS sin ruta por defecto"
  if ! nmcli connection show "$ssid" >/dev/null 2>&1; then
    nmcli connection add type wifi ifname "$iface" con-name "$ssid" ssid "$ssid"
  fi
  nmcli connection modify "$ssid" ipv4.method manual ipv4.addresses "$WIBEEE_AP_HOST_ADDRESS" ipv4.never-default yes ipv6.method disabled
  if [[ -n "$AP_PASSWORD" ]]; then
    nmcli connection modify "$ssid" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$AP_PASSWORD"
  else
    nmcli connection modify "$ssid" wifi-sec.key-mgmt none
  fi
  run nmcli connection up "$ssid" ifname "$iface"
}

find_wibeee_ip() {
  local candidates=(
    "$PORTAL_IP"
    '192.168.4.1'
    '10.10.10.1'
    '192.168.44.1'
  )
  local ip
  for ip in "${candidates[@]}"; do
    if curl -fsS --http1.1 --connect-timeout "$PORTAL_TIMEOUT" --max-time "$PORTAL_TIMEOUT" \
      -H 'Connection: close' "http://$ip/" >/dev/null 2>&1; then
      printf '%s\n' "$ip"
      return 0
    fi
  done
  return 1
}

home_meter_urls() {
  local base="http://$METER_IP"
  local values_path="${METER_VALUES_PATH:-/services/user/values.xml}"
  local device_id="${METER_DEVICE_ID:-}"
  base="${base%/}"
  if [[ -n "$device_id" ]]; then
    printf '%s%s?id=%s\n' "$base" "$values_path" "$device_id"
  else
    printf '%s%s\n' "$base" "$values_path"
    printf '%s/\n' "$base"
  fi
}

meter_payload_valid() {
  local url
  local response
  response="$(mktemp)"
  while IFS= read -r url; do
    if curl -fsS --http1.1 --connect-timeout 3 --max-time "${METER_REQUEST_TIMEOUT_SECONDS:-5}" \
      -H 'Connection: close' -o "$response" "$url" >/dev/null 2>&1; then
      if grep -Eq '<(root|values)[ >]' "$response" && ! grep -Eq '<values[[:space:]]*/>|<values></values>' "$response"; then
        rm -f "$response"
        return 0
      fi
    fi
  done < <(home_meter_urls)
  rm -f "$response"
  return 1
}

confirm_home_failure() {
  local i
  state home_unreachable "validando fallo del medidor en LAN"
  for ((i = 1; i <= FAILURE_CONFIRMATION_ATTEMPTS; i++)); do
    if meter_payload_valid; then
      state operative "lectura LAN valida; no se recupera"
      return 1
    fi
    log "Fallo LAN confirmado parcialmente ($i/$FAILURE_CONFIRMATION_ATTEMPTS)"
    sleep 2
  done
  state failure_confirmed "sin lectura valida tras $FAILURE_CONFIRMATION_ATTEMPTS intentos"
  return 0
}

maybe_open_browser() {
  local ip="$1"
  if [[ "$OPEN_BROWSER" -ne 1 ]]; then
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    run xdg-open "http://$ip/"
  else
    log "No encuentro xdg-open; abre manualmente http://$ip/"
  fi
}

perform_configuration_call() {
  local ip="$1"
  local url="$CONFIG_URL"
  local response_file

  if [[ -z "$url" ]]; then
    log "No hay WIBEEE_CONFIG_URL. Me quedo en modo diagnostico."
    return 2
  fi

  if [[ "$url" != http://* && "$url" != https://* ]]; then
    url="http://$ip/${url#/}"
  fi

  response_file="$(mktemp)"
  if [[ "$CONFIG_DATA" == @* ]]; then
    local data_file="${CONFIG_DATA#@}"
    [[ -f "$data_file" ]] || fail "No existe el fichero de datos $data_file"
    log "HTTP $CONFIG_METHOD $(redact_url "$url") con fichero de datos manual redactado"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      curl -fsS --http1.1 --connect-timeout "$PORTAL_TIMEOUT" --max-time 15 \
        -X "$CONFIG_METHOD" -H "Content-Type: $CONFIG_CONTENT_TYPE" -H 'Connection: close' \
        --data-binary "@$data_file" -o "$response_file" "$url"
    fi
  elif [[ -n "$CONFIG_DATA" ]]; then
    log "HTTP $CONFIG_METHOD $(redact_url "$url") con datos manuales redactados"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      curl -fsS --http1.1 --connect-timeout "$PORTAL_TIMEOUT" --max-time 15 \
        -X "$CONFIG_METHOD" -H "Content-Type: $CONFIG_CONTENT_TYPE" -H 'Connection: close' \
        --data "$CONFIG_DATA" -o "$response_file" "$url"
    fi
  else
    curl_get "$url" "$response_file" 0
  fi
  log "Respuesta guardada temporalmente en $response_file"
}

detect_wifi_security() {
  local iface="$1"
  local target_ssid="$2"
  nmcli -t -f SSID,SECURITY device wifi list ifname "$iface" | \
    awk -F: -v ssid="$target_ssid" '
      {
        raw=$0
        gsub(/\\:/, "\001", raw)
        split(raw, parts, ":")
        current=parts[1]
        gsub(/\001/, ":", current)
        if (current == ssid) {
          sec=substr(raw, length(parts[1]) + 2)
          gsub(/\001/, ":", sec)
          print sec
          exit
        }
      }
    '
}

security_to_code() {
  protocol wifi-paths --ssid test --password test --security "$1" >/dev/null || fail "No reconozco la seguridad de la Wi-Fi destino: $1"
  protocol wifi-paths --ssid test --password test --security "$1" | python3 -c 'import json, re, sys; p=json.load(sys.stdin)[0]; print(re.search(r"security=([^&]+)", p).group(1))'
}

login_wibeee() {
  local ip="$1"
  local login_url
  local response
  if [[ -z "$LOGIN_USER" && -z "$LOGIN_PASSWORD" ]]; then
    return 0
  fi
  [[ -n "$LOGIN_USER" && -n "$LOGIN_PASSWORD" ]] || fail "WIBEEE_LOGIN_USER y WIBEEE_LOGIN_PASSWORD deben definirse juntos"
  response="$(mktemp)"
  login_url="http://$ip$(protocol login-path --username "$LOGIN_USER" --password "$LOGIN_PASSWORD")"
  if ! curl_get "$login_url" "$response" 0; then
    rm -f "$response"
    fail "El login HTTP del Wibeee fallo"
  fi
  if ! PYTHONPATH="${PYTHONPATH:-}:$REPO_ROOT/backend" python3 - "$response" <<'PY'
import pathlib
import sys
from app.services.wibeee_protocol import looks_like_successful_login

raise SystemExit(0 if looks_like_successful_login(pathlib.Path(sys.argv[1]).read_text(errors="ignore")) else 1)
PY
  then
    rm -f "$response"
    fail "El Wibeee no confirmo un login valido"
  fi
  rm -f "$response"
}

scan_wibeee_networks() {
  local ip="$1"
  local paths
  local path
  paths="$(protocol scan-paths | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)))')"
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    curl_get "http://$ip$path" /dev/null 1 || true
  done <<<"$paths"
}

auto_configure_wibeee() {
  local ip="$1"
  local iface="$2"
  local target_ssid="$3"
  local target_password="$4"
  local security
  local security_code
  local paths
  local path
  local network_path

  state configuring "login y preparacion"
  login_wibeee "$ip"
  scan_wibeee_networks "$ip"

  security="${WIFI_SECURITY:-}"
  if [[ -z "$security" || "$security" == "auto" || "$security" == "AUTO" ]]; then
    security="$(detect_wifi_security "$iface" "$target_ssid")"
    [[ -n "$security" ]] || fail "No veo la Wi-Fi destino '$target_ssid' en el escaneo actual"
  fi
  security_code="$(security_to_code "$security")"

  network_path="$(protocol network-path \
    --name "$DEVICE_NAME" \
    --dhcp "$WIBEEE_DHCP" \
    --ip "$WIBEEE_STATIC_IP" \
    --gateway "$WIBEEE_GATEWAY" \
    --subnet "$WIBEEE_SUBNET" \
    --dns1 "$WIBEEE_DNS1" \
    --dns2 "$WIBEEE_DNS2")"
  curl_get "http://$ip$network_path" /dev/null 0

  paths="$(protocol wifi-paths --ssid "$target_ssid" --password "$target_password" --security "$security_code" --typekey "$WIFI_TYPEKEY" | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)))')"
  while IFS= read -r path; do
    [[ -n "$path" ]] || continue
    curl_get "http://$ip$path" /dev/null 0
  done <<<"$paths"

  state reboot_expected "enviando reset; el corte de conexion posterior es esperado"
  curl_get "http://$ip$(protocol reset-path)" /dev/null 1
}

restore_home_wifi() {
  if [[ "$KEEP_WIBEEE" -eq 1 ]]; then
    log "Se mantiene la conexion al Wibeee por peticion explicita."
    return 0
  fi
  if [[ -z "$HOME_CONNECTION" ]]; then
    return 0
  fi
  state reconnecting_home "restaurando conexion $HOME_CONNECTION"
  run nmcli connection up "$HOME_CONNECTION"
}

find_meter_ip_from_mac() {
  [[ -n "$WIBEEE_MAC" ]] || return 1
  ip neigh show | awk -v mac="${WIBEEE_MAC,,}" 'tolower($0) ~ mac {print $1; exit}'
}

wait_for_meter() {
  local tries="$VALIDATION_ATTEMPTS"
  local delay="$VALIDATION_INTERVAL"
  local i
  local found_ip

  for ((i = 1; i <= tries; i++)); do
    found_ip="$(find_meter_ip_from_mac || true)"
    if [[ -n "$found_ip" && "$found_ip" != "$METER_IP" ]]; then
      log "Nueva IP posible del Wibeee detectada por MAC: $found_ip"
      METER_IP="$found_ip"
    fi
    state validating "probando endpoint de lectura ($i/$tries)"
    if meter_payload_valid; then
      state completed "lectura valida recuperada en http://$METER_IP"
      clear_cooldown
      return 0
    fi
    state searching_home_meter "esperando lectura valida ($i/$tries)"
    sleep "$delay"
  done
  state failed "el medidor no volvio con lectura valida en http://$METER_IP"
  return 1
}

recover_once() {
  local ssid
  local iface
  local wibeee_ip
  local target_ssid
  local attempt

  with_recovery_lock
  if [[ "$FORCE_RECOVERY" -ne 1 ]]; then
    cooldown_active && return 0
    confirm_home_failure || return 0
  else
    state failure_confirmed "recuperacion manual forzada"
  fi
  mark_cooldown
  notify_recovery started "Recuperacion WiBeee iniciada"

  iface="$(detect_wifi_iface)"
  [[ -n "$iface" ]] || fail "No he podido detectar una interfaz Wi-Fi"
  WIFI_IFACE="$iface"
  ORIGINAL_IFACE="$iface"

  ORIGINAL_CONNECTION="$(detect_active_connection "$iface" || true)"
  ORIGINAL_SSID="$(detect_active_ssid "$iface" || true)"
  if [[ -z "$HOME_CONNECTION" ]]; then
    HOME_CONNECTION="$ORIGINAL_CONNECTION"
  fi
  if [[ -z "$TARGET_SSID" && ( -z "$ORIGINAL_SSID" || "$ORIGINAL_SSID" =~ ^${SSID_PATTERN} ) ]]; then
    TARGET_SSID="$(infer_saved_home_ssid || true)"
  fi
  trap cleanup_connection EXIT

  log "Interfaz Wi-Fi: $iface"
  [[ -n "$HOME_CONNECTION" ]] && log "Conexion a restaurar: $HOME_CONNECTION"
  [[ -n "$ORIGINAL_SSID" ]] && log "SSID actual del host: $ORIGINAL_SSID"

  for ((attempt = 1; attempt <= RECOVERY_MAX_ATTEMPTS; attempt++)); do
    ssid="$(scan_for_wibeee_ssid "$iface")"
    if [[ -n "$ssid" ]]; then
      break
    fi
    state home_unreachable "AP del Wibeee no encontrado ($attempt/$RECOVERY_MAX_ATTEMPTS)"
    sleep "$MONITOR_INTERVAL"
  done
  [[ -n "$ssid" ]] || fail "No encuentro un SSID de Wibeee que encaje con el patron indicado"
  state ap_detected "SSID encontrado: $ssid"

  state ap_connecting "conectando temporalmente al AP"
  connect_to_ssid "$iface" "$ssid"
  CONNECTED_TO_WIBEEE=1
  sleep 3

  wibeee_ip="$(find_wibeee_ip || true)"
  [[ -n "$wibeee_ip" ]] || fail "Conectado al SSID del Wibeee, pero no encuentro su IP local conocida"
  log "IP local detectada del Wibeee: $wibeee_ip"

  maybe_open_browser "$wibeee_ip"
  if [[ "$AUTO_CONFIG" -eq 1 ]]; then
    target_ssid="${TARGET_SSID:-$ORIGINAL_SSID}"
    [[ -n "$target_ssid" ]] || fail "No he podido inferir la SSID destino"
    if [[ "$target_ssid" == "$ssid" || "$target_ssid" =~ ^${SSID_PATTERN} ]]; then
      fail "La SSID destino coincide con el AP del Wibeee; conecta antes el host a tu Wi-Fi real o fija --target-ssid"
    fi
    [[ -n "$TARGET_PASSWORD" ]] || fail "Falta WIBEEE_TARGET_WIFI_PASSWORD en .env o --target-password"
    log "Reconfigurando Wibeee hacia la red '$target_ssid'"
    auto_configure_wibeee "$wibeee_ip" "$iface" "$target_ssid" "$TARGET_PASSWORD"
  else
    perform_configuration_call "$wibeee_ip" || true
  fi

  restore_home_wifi
  CONNECTED_TO_WIBEEE=0
  if [[ "$KEEP_WIBEEE" -eq 0 && -n "$HOME_CONNECTION" ]]; then
    sleep 5
    if wait_for_meter; then
      notify_recovery completed "Recuperacion WiBeee completada"
    else
      notify_recovery failed "Recuperacion WiBeee fallida; requiere revision"
      return 1
    fi
  fi

  log "Proceso terminado."
}

monitor_loop() {
  while true; do
    if recover_once; then
      log "Ciclo de vigilancia completado. Esperando siguiente ciclo."
    fi
    sleep "$MONITOR_INTERVAL"
  done
}

main() {
  if [[ "$MONITOR_MODE" -eq 1 ]]; then
    if [[ "${WIBEEE_RECOVERY_ENABLED:-false}" != "true" ]]; then
      state cooldown "recuperacion automatica desactivada; define WIBEEE_RECOVERY_ENABLED=true"
      while true; do
        sleep 3600
      done
    fi
    monitor_loop
    return 0
  fi
  recover_once
}

main "$@"
