#!/usr/bin/env sh
set -eu

service_name="wibeee-recover.service"

env_value() {
  key="$1"
  if [ ! -f .env ]; then
    return 1
  fi
  grep -E "^${key}=" .env | tail -n1 | cut -d= -f2-
}

install_wibeee_recovery_service() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd no esta disponible; no se instala $service_name." >&2
    return 0
  fi
  if ! command -v nmcli >/dev/null 2>&1; then
    echo "NetworkManager/nmcli no esta disponible; no se instala $service_name." >&2
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo no esta disponible; instala $service_name manualmente." >&2
    return 0
  fi

  repo_root="$(pwd)"
  sed \
    -e "s|__REPO_ROOT__|$repo_root|g" \
    deploy/systemd/$service_name | sudo tee /etc/systemd/system/$service_name >/dev/null

  sudo systemctl daemon-reload
  sudo systemctl enable "$service_name"
  sudo systemctl restart "$service_name"
  echo "Recuperacion WiBeee activada: systemctl status $service_name"
}

disable_wibeee_recovery_service() {
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$service_name" >/dev/null 2>&1; then
    sudo systemctl disable --now "$service_name" >/dev/null 2>&1 || true
    echo "Recuperacion WiBeee desactivada por WIBEEE_RECOVERY_ENABLED=false."
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker no esta disponible." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env desde .env.example. Revisa POSTGRES_PASSWORD y API_WRITE_TOKEN."
fi

docker compose build
docker compose up -d

if [ "$(env_value WIBEEE_RECOVERY_ENABLED || echo false)" = "true" ]; then
  install_wibeee_recovery_service
else
  disable_wibeee_recovery_service
fi

echo "Dashboard: http://localhost:5173"
echo "API:       http://localhost:8000/api/v1/docs"
