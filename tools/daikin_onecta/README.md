# Daikin ONECTA / LAN diagnostic

Paquete aislado para Energy Home. Incluye lecturas locales legacy y el cliente oficial ONECTA Cloud API v1. El script de diagnóstico solo hace lecturas; los métodos PATCH existen pero nunca se invocan durante el diagnóstico.

## Ejecutar

```powershell
cd tools/daikin_onecta
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
python scripts/diagnose.py
python scripts/discover_local.py --broadcast 192.168.1.255
python -m pytest
```

No se registran tokens, claves, cuerpos de token ni cabeceras. No pongas `.env` en git. Los métodos de control cambian el estado al invocarse; el script de diagnóstico no los llama.

## ONECTA

Contrato confirmado en el portal:

- API base: `https://api.onecta.daikineurope.com/v1`
- OAuth authorize: `https://idp.onecta.daikineurope.com/v1/oidc/authorize`
- OAuth token y refresh: `https://idp.onecta.daikineurope.com/v1/oidc/token`
- Scopes: `openid onecta:basic.integration`; `offline_access` es opcional.
- Bearer access token, válido una hora. El refresh token rota al usarse y su validez máxima es un año.
- Lectura: `GET /sites`, `GET /gateway-devices`, `GET /gateway-devices/{gatewayDeviceId}`.
- Escritura documentada: `PATCH /gateway-devices/{gatewayDeviceId}/management-points/{embeddedId}/characteristics/{name}`. Características de clima incluyen `onOffMode`, `operationMode` y `temperatureControl`.

En **My Apps** aún no hay una aplicación. Según la guía del portal: cuenta → **My Apps** → **New App**; nombre, estrategia **Onecta OIDC**, URI callback segura y descripción. Al crearla, el portal muestra el client secret una única vez: guárdalo en `.env` local y no lo compartas por chat. El portal rechaza URI con esquemas `http`, `ftp`, `ftps`, `file` y también `https://localhost`; el redirect URI usado al canjear el código debe coincidir exactamente con el registrado.

`scripts/oauth_callback.py` completa el flujo inicial: genera un `state` aleatorio, valida el valor devuelto, canjea el código y hace una primera lectura de `/gateway-devices`. Cifra client ID, client secret y refresh token con Windows DPAPI en `%LOCALAPPDATA%\EnergyHome\Daikin\credentials.dpapi`. `scripts/diagnose_cloud.py` renueva el token (guardando la rotación) y consulta el detalle de los equipos con GET. Ambos scripts omiten tokens, identificadores y respuestas sin filtrar en logs. El almacén DPAPI solo se puede abrir desde la misma cuenta de Windows. No compartas el client secret por chat.

Después de completar OAuth en tu propia instalación, ejecuta `python scripts/diagnose_cloud.py` para renovar el token y hacer lecturas GET. No subas su salida ni credenciales específicas de una cuenta al repositorio. Los refresh tokens no necesitan que el túnel siga abierto mientras continúen válidos. Para autorizar o reautorizar:

1. Ejecuta `python scripts/start_tunnel.py` y registra la nueva URL en **My Apps** como `https://<nuevo-host>.trycloudflare.com/oauth/daikin/callback`.
2. En PowerShell configura el `.env` que contiene el client ID/secret y la URI exacta registrada:

   ```powershell
   $env:DAIKIN_ENV_FILE = 'C:\ruta\local\.env'
   $env:DAIKIN_REDIRECT_URI = 'https://<nuevo-host>.trycloudflare.com/oauth/daikin/callback'
   ```

3. Ejecuta `python scripts/oauth_callback.py`.

ONECTA muestra en su pantalla de consentimiento los permisos solicitados por cada app. `onecta:basic.integration` puede permitir consultar y controlar dispositivos; `offline_access` permite renovar tokens. Revisa el texto del portal antes de autorizar. El callback y el diagnóstico incluidos aquí solo hacen lecturas.

## Adaptación a Energy Home

`DaikinClient` y `LegacyLocalDaikin` ofrecen superficies separadas que pueden envolverse detrás de un `ClimateProvider` asíncrono. Inyecta el proveedor mediante configuración para cambiar entre local y cloud. No se ha modificado la app FastAPI existente.

`discover_local.py` usa el broadcast Daikin `DAIKIN_UDP/common/basic_info` en UDP/30050 y luego consulta solo endpoints GET de lectura por HTTP y HTTPS con validación TLS normal. No modifica parámetros ni estado; ajusta `--broadcast` a la subred local.
