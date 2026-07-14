#!/usr/bin/env bash

set -euo pipefail

log() {
  printf '[recover-wibeee] %s\n' "$*"
}

fail() {
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
  --meter-ip IP             IP esperada del medidor tras volver a tu LAN. Por defecto: 192.168.1.43
  --ap-password CLAVE       Clave del AP del Wibeee si la tuviera.
  --open-browser            Abre en el navegador la IP local detectada del Wibeee.
  --keep-wibeee             No vuelve automaticamente a la Wi-Fi de casa al terminar.
  --dry-run                 Solo muestra acciones, no cambia nada.
  -h, --help                Muestra esta ayuda.

Variables opcionales para automatizar la reconfiguracion cuando conozcamos la llamada real:
  WIBEEE_CONFIG_URL         URL absoluta o ruta relativa sobre la IP local del Wibeee.
  WIBEEE_CONFIG_METHOD      GET o POST. Por defecto: POST.
  WIBEEE_CONFIG_DATA        Datos a enviar. Si empieza por @ se lee de un fichero.
  WIBEEE_CONFIG_CONTENT_TYPE  Content-Type. Por defecto: application/x-www-form-urlencoded

Ejemplos:
  ./scripts/recover-wibeee.sh --ssid-pattern 'WIBEEE.*3C:F4:AE' --home-connection 'Mi casa 2G'
  WIBEEE_CONFIG_URL=/goform/saveWifi WIBEEE_CONFIG_DATA='ssid=Casa&password=secreta' ./scripts/recover-wibeee.sh --ssid-exact 'WIBEEE_3C:F4:AE'
EOF
}

SSID_PATTERN='WIBEEE'
SSID_EXACT=''
WIFI_IFACE=''
HOME_CONNECTION=''
METER_IP='192.168.1.43'
AP_PASSWORD=''
OPEN_BROWSER=0
KEEP_WIBEEE=0
DRY_RUN=0
CONFIG_URL="${WIBEEE_CONFIG_URL:-}"
CONFIG_METHOD="${WIBEEE_CONFIG_METHOD:-POST}"
CONFIG_DATA="${WIBEEE_CONFIG_DATA:-}"
CONFIG_CONTENT_TYPE="${WIBEEE_CONFIG_CONTENT_TYPE:-application/x-www-form-urlencoded}"
ORIGINAL_CONNECTION=''
ORIGINAL_IFACE=''

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

run() {
  log "$*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
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

scan_for_wibeee_ssid() {
  local iface="$1"
  local list
  run nmcli dev wifi rescan ifname "$iface"
  list="$(nmcli -t -f SSID device wifi list ifname "$iface" | sed '/^$/d' || true)"
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
    run nmcli dev wifi connect "$ssid" password "$AP_PASSWORD" ifname "$iface"
  else
    run nmcli dev wifi connect "$ssid" ifname "$iface"
  fi
}

find_wibeee_ip() {
  local candidates=(
    '192.168.4.1'
    '10.10.10.1'
    '192.168.44.1'
  )
  local ip
  for ip in "${candidates[@]}"; do
    if curl -fsS --max-time 5 "http://$ip/" >/dev/null 2>&1; then
      printf '%s\n' "$ip"
      return 0
    fi
  done
  return 1
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
    run curl -fsS --max-time 15 -X "$CONFIG_METHOD" -H "Content-Type: $CONFIG_CONTENT_TYPE" --data-binary "@$data_file" -o "$response_file" "$url"
  elif [[ -n "$CONFIG_DATA" ]]; then
    run curl -fsS --max-time 15 -X "$CONFIG_METHOD" -H "Content-Type: $CONFIG_CONTENT_TYPE" --data "$CONFIG_DATA" -o "$response_file" "$url"
  else
    run curl -fsS --max-time 15 -X "$CONFIG_METHOD" -o "$response_file" "$url"
  fi
  log "Respuesta guardada temporalmente en $response_file"
}

restore_home_wifi() {
  if [[ "$KEEP_WIBEEE" -eq 1 ]]; then
    log "Se mantiene la conexion al Wibeee por peticion explicita."
    return 0
  fi
  if [[ -z "$HOME_CONNECTION" ]]; then
    return 0
  fi
  run nmcli connection up "$HOME_CONNECTION"
}

wait_for_meter() {
  local tries=30
  local delay=5
  local url="http://$METER_IP/"
  local i

  for ((i = 1; i <= tries; i++)); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      log "El medidor ya responde otra vez en $url"
      return 0
    fi
    log "Esperando a que vuelva el medidor ($i/$tries)..."
    sleep "$delay"
  done
  log "El medidor no ha vuelto aun a $url"
  return 1
}

main() {
  local ssid
  local iface
  local wibeee_ip

  iface="$(detect_wifi_iface)"
  [[ -n "$iface" ]] || fail "No he podido detectar una interfaz Wi-Fi"
  WIFI_IFACE="$iface"
  ORIGINAL_IFACE="$iface"

  ORIGINAL_CONNECTION="$(detect_active_connection "$iface" || true)"
  if [[ -z "$HOME_CONNECTION" ]]; then
    HOME_CONNECTION="$ORIGINAL_CONNECTION"
  fi

  log "Interfaz Wi-Fi: $iface"
  [[ -n "$HOME_CONNECTION" ]] && log "Conexion a restaurar: $HOME_CONNECTION"

  ssid="$(scan_for_wibeee_ssid "$iface")"
  [[ -n "$ssid" ]] || fail "No encuentro un SSID de Wibeee que encaje con el patron indicado"
  log "SSID encontrado: $ssid"

  connect_to_ssid "$iface" "$ssid"
  sleep 3

  wibeee_ip="$(find_wibeee_ip || true)"
  [[ -n "$wibeee_ip" ]] || fail "Conectado al SSID del Wibeee, pero no encuentro su IP local conocida"
  log "IP local detectada del Wibeee: $wibeee_ip"

  maybe_open_browser "$wibeee_ip"
  perform_configuration_call "$wibeee_ip" || true

  restore_home_wifi
  if [[ "$KEEP_WIBEEE" -eq 0 && -n "$HOME_CONNECTION" ]]; then
    sleep 5
    wait_for_meter || true
  fi

  log "Proceso terminado."
}

main "$@"
