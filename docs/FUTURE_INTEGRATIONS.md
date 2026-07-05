# Integraciones futuras

La version inicial no controla enchufes, Telegram, Alexa ni Home Assistant. La arquitectura ya incluye:

- `DeviceAdapter` como contrato async.
- tabla `devices` con configuracion JSON y estado.
- flags `FEATURE_AUTOMATIONS`, `FEATURE_TELEGRAM` y `FEATURE_SMART_DEVICES`, todos desactivados por defecto.

Reglas candidatas para una fase posterior:

- Si exportacion > X W durante Y minutos, encender termo.
- Si importacion > X W durante Y minutos, apagar termo.
- Si hay excedente estable al mediodia, recomendar lavadora o lavavajillas.

El Sonoff S61S se trata solo como candidato futuro para el termo y medicion individual. No se asume instalado, emparejado ni configurado.
