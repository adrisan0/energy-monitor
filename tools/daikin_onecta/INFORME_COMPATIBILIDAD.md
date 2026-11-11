# Informe de compatibilidad Daikin — 11 de noviembre de 2026

## Resumen

- **ONECTA Cloud:** el flujo OAuth y las lecturas documentadas de dispositivos y detalles de gestión funcionaron en una ejecución real.
- **Acceso local:** el descubrimiento UDP identificó adaptadores Daikin, pero no se confirmó una API local de control.
- **Control:** no se envió ningún PATCH ni comando que cambie el estado de un equipo.
- **Integración:** el cliente y los diagnósticos están aislados en este paquete; el backend FastAPI de Energy Home no se ha modificado.

## Compatibilidad local

Se utilizó el broadcast Daikin documentado para descubrimiento, sin barrido de puertos. Los GET a `/common/basic_info` y `/aircon/get_control_info` devolvieron HTTP 404 en los candidatos. El GET HTTPS a `/common/basic_info` agotó el tiempo de espera con validación TLS activa. Por tanto, no se ha confirmado control local para esos adaptadores.

Las direcciones privadas, identificadores y otros detalles de la red doméstica se conservaron solo en el informe local del usuario y se omiten aquí.

## ONECTA Cloud

El portal oficial documenta API v1, OIDC Authorization Code, `GET /sites`, `GET /gateway-devices` y `GET /gateway-devices/{gatewayDeviceId}`. La prueba real completó OAuth, enumeró dispositivos y leyó sus puntos de gestión mediante GET. Los nombres, cantidades y estados concretos se omiten de esta copia pública porque son datos del hogar.

La autorización concedida por la persona usuaria permite leer el estado y controlar dispositivos desde la app. El código de diagnóstico incluido en este paquete solo hace GET. El refresh token se cifra con Windows DPAPI fuera del repositorio.

## Verificación y límites

- Tests del paquete: **3 pasaron**.
- Descubrimiento mDNS `_dkapi._tcp.local` y SSDP `ssdp:all`: sin respuestas observadas.
- La vía cloud quedó verificada; la vía local no quedó confirmada.
- Los métodos de escritura de la API existen en el cliente, pero esta sesión no los invocó.
- Los límites globales de peticiones no aparecen especificados en la guía consultada; el cliente aplica pausas configurables, reintentos acotados y respeta `Retry-After` en HTTP 429.

## Fuentes

- Portal oficial: https://developer.cloud.daikineurope.com
- Guía ONECTA Cloud API v1: https://developer.cloud.daikineurope.com/docs/84e709f1-9d33-47e1-a93c-7f5cb8b8f12b/authorization
- Especificación API v1: https://developer.cloud.daikineurope.com/spec/84e709f1-9d33-47e1-a93c-7f5cb8b8f12b/510c971e-5942-4bbb-baad-2f9c1745df08
- Portal oficial Daikin Developer: https://www.daikin.eu/en_us/product-group/control-systems/daikin-developer-portal.html
- Home Assistant Daikin AC: https://www.home-assistant.io/integrations/daikin/
- PyDaikin: https://github.com/fredrike/pydaikin
