#!/usr/bin/env sh
set -eu

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

echo "Dashboard: http://localhost:5173"
echo "API:       http://localhost:8000/api/v1/docs"
