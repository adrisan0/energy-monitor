Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Energy Home Monitor - instalacion Windows"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker no esta disponible. Instala Docker Desktop y vuelve a ejecutar."
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Creado .env desde .env.example. Revisa POSTGRES_PASSWORD y API_WRITE_TOKEN."
}

docker compose build
docker compose up -d

Write-Host "Dashboard: http://localhost:5173"
Write-Host "API:       http://localhost:8000/api/v1/docs"
Write-Host "CLI:       docker compose exec backend energyctl status"
