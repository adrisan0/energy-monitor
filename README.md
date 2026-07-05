# Energy Home Monitor

Aplicacion local para monitorizar una instalacion solar compartida por dos viviendas.

## Arranque rapido en Windows

1. Instala Docker Desktop.
2. Abre PowerShell en esta carpeta.
3. Ejecuta:

```powershell
Copy-Item .env.example .env
.\scripts\install-windows.ps1
```

Dashboard: `http://localhost:5173`  
API: `http://localhost:8000/api/v1/docs`

La configuracion inicial usa `SIMULATION_MODE=true`, por lo que arranca sin acceso al medidor fisico.

## Medidor real

Edita `.env`:

```env
SIMULATION_MODE=false
METER_URL=http://192.168.1.31/
METER_VALUES_PATH=/services/user/values.xml
METER_DEVICES_PATH=/services/user/devices.xml
METER_DEVICE_ID=wibeee
METER_POLL_INTERVAL_SECONDS=60
TIMEZONE=Europe/Madrid
```

Aplica cambios:

```powershell
docker compose up -d --build
```

Si `values.xml` responde vacio (`<values />`), la app ahora intenta descubrir ids adicionales desde `devices.xml`. Si aun asi no aparecen `pac1`, `pac2` y `fpot1`, el medidor esta exponiendo otro endpoint o un id distinto.

## Home Assistant

Integracion minima por REST API para consultar estado y encender/apagar entidades de Home Assistant desde esta app.

Edita `.env`:

```env
FEATURE_SMART_DEVICES=true
HOME_ASSISTANT_BASE_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=tu_long_lived_access_token
HOME_ASSISTANT_TIMEOUT_SECONDS=10
HOME_ASSISTANT_VERIFY_SSL=true
```

Configuracion de dispositivo recomendada en la tabla `devices`:

```json
{
  "adapter": "home_assistant",
  "entity_id": "switch.termo_padres",
  "power_entity_id": "sensor.termo_padres_power"
}
```

Endpoints nuevos:

```powershell
curl http://localhost:8000/api/v1/devices/3/state
curl -X POST http://localhost:8000/api/v1/devices/3/on -H "X-Admin-Token: change-me-local-admin-token"
curl -X POST http://localhost:8000/api/v1/devices/3/off -H "X-Admin-Token: change-me-local-admin-token"
```

## Flux LED

Tambien puedes usar dispositivos compatibles con `flux_led` / Magic Home en local, sin Home Assistant. La libreria oficial del proyecto `flux-led` soporta control LAN de estos controladores y en esta maquina `192.168.1.29:5577` ha respondido como `Controller RGB (0x33)`.

Para activarlo:

```env
FEATURE_SMART_DEVICES=true
```

Config de dispositivo recomendada:

```json
{
  "adapter": "flux_led",
  "ip_address": "192.168.1.29"
}
```

Ejemplo de configuracion del dispositivo de pruebas:

```powershell
curl -X PATCH http://localhost:8000/api/v1/devices/4 `
  -H "Content-Type: application/json" `
  -H "X-Admin-Token: change-me-local-admin-token" `
  -d '{
    "status": "active",
    "control_mode": "automatic",
    "active": true,
    "config": {
      "adapter": "flux_led",
      "ip_address": "192.168.1.29"
    }
  }'
```

Pruebas:

```powershell
curl http://localhost:8000/api/v1/devices/4/state
curl -X POST http://localhost:8000/api/v1/devices/4/on -H "X-Admin-Token: change-me-local-admin-token"
curl -X POST http://localhost:8000/api/v1/devices/4/off -H "X-Admin-Token: change-me-local-admin-token"
```

## Telegram

El worker puede arrancar un bot de Telegram para controlar la lampara `flux_led` activa, cambiar perfiles de visualizacion y recibir alertas de importacion.

Activalo en `.env`:

```env
FEATURE_TELEGRAM=true
TELEGRAM_BOT_TOKEN=token_de_botfather
TELEGRAM_BOT_TOKENS=token_extra_1,token_extra_2
TELEGRAM_ALLOWED_CHAT_IDS=123456789
TELEGRAM_IMPORT_ALERT_MIN_W=200
TELEGRAM_IMPORT_ALERT_HOLD_SECONDS=120
TELEGRAM_ALERT_COOLDOWN_SECONDS=900
```

Reinicia:

```powershell
docker compose up -d --build worker backend
```

Comandos principales:

```text
/status
/modo_consumo
/modo_importacion
/modo_precio
/excedente_on
/excedente_off
/blink_on
/blink_off
/auto
/manual
/on
/off
/apply
```

El primer token atiende comandos y botones. `TELEGRAM_BOT_TOKENS` es opcional y permite tokens extra separados por coma o punto y coma para enviar avisos por varios bots. El mensaje de status incluye lectura solar, consumo, importacion/exportacion, modo de control, perfil activo, flags de excedente/parpadeo y estado real de la lampara. Las alertas avisan si estas importando por encima del umbral configurado y lo destacan si ocurre en hora punta. El modo precio usa una tarifa 2.0TD simplificada: valle 0-8 h y fines de semana, llano 8-10 / 14-18 / 22-24 h, punta 10-14 / 18-22 h.

## CLI

```powershell
docker compose exec backend energyctl status
docker compose exec backend energyctl watch
docker compose exec backend energyctl raw
docker compose exec backend energyctl history --day today
docker compose exec backend energyctl history --from 2026-07-01 --to 2026-07-02
docker compose exec backend energyctl export --from 2026-07-01 --to 2026-07-02 --output /tmp/energy.csv
docker compose exec backend energyctl backup run
docker compose exec backend energyctl system check
curl http://localhost:8000/api/v1/latest
```

## TP-Link como termo

El enchufe `TP-Link HS100 termo` puede funcionar en modo automatico como "bateria termica":

- Enciende solo con excedente sostenido.
- Se apaga cuando se pierde el excedente durante el tiempo configurado.
- No enciende en hora punta si esa opcion esta marcada.
- Si no hubo suficiente sol, fuerza un minimo diario dentro de una ventana de apoyo configurable.

La configuracion se hace desde la pestaña `Enchufes` de la app.
Esta logica vive en el `worker` y funciona igual en Windows o en Ubuntu mientras Docker Compose y la conectividad LAN hacia el enchufe sigan disponibles.

## Servicios Docker

- `postgres`: base de datos persistente.
- `backend`: FastAPI, OpenAPI y CLI.
- `worker`: polling del medidor o simulador.
- `frontend`: React, Vite, Tailwind y ECharts.
- `backup`: backups diarios comprimidos.

## Seguridad local

Las operaciones sensibles como `PUT /api/v1/tariff` y `POST /api/v1/backups/run` requieren `X-Admin-Token` con el valor de `API_WRITE_TOKEN`.

No se abren puertos del router. Para acceso remoto futuro se recomienda Tailscale; no se recomienda port forwarding directo.

## Firewall Windows

Permite Docker Desktop en redes privadas. Si accedes desde otro equipo de la LAN, abre los puertos locales `5173` y `8000` solo para red privada.

## Backups

El servicio `backup` ejecuta una copia diaria mediante `pg_dump`, la comprime en `.sql.gz` y rota archivos antiguos segun `BACKUP_RETENTION_DAYS`.

Backup manual:

```powershell
docker compose exec backend energyctl backup run
```

Restauracion documentada:

```powershell
docker compose stop backend worker backup frontend
docker compose exec -T postgres dropdb -U energy energy
docker compose exec -T postgres createdb -U energy energy
Get-Content .\backups\energy_YYYYMMDDTHHMMSSZ.sql.gz | docker compose exec -T postgres sh -c "gunzip -c | psql -U energy -d energy"
docker compose up -d
```

Si el backup esta en el volumen Docker `backups_data`, copialo antes con `docker cp`.

## Migracion a Ubuntu

1. Instala Docker Engine y el plugin Compose.
2. Copia el repositorio y el archivo `.env`.
3. Copia o restaura el volumen de Postgres/backups.
4. Ejecuta:

```bash
chmod +x scripts/install-linux.sh
./scripts/install-linux.sh
```

## Desarrollo

Backend:

```bash
cd backend
pip install -e ".[dev]"
pytest
ruff check .
mypy app
```

Frontend:

```bash
cd frontend
npm install
npm run build
```

## Integraciones futuras

Las integraciones Sonoff S61S, TP-Link HS100, MQTT, Home Assistant, Alexa y Telegram estan modeladas pero desactivadas por defecto mediante feature flags.

Consulta `docs/FUTURE_INTEGRATIONS.md`.
