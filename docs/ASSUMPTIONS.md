# Supuestos de la version inicial

- La aplicacion corre localmente y no depende de servicios cloud.
- `SIMULATION_MODE=true` es el valor por defecto para permitir arranque sin medidor fisico.
- El medidor real devuelve XML HTTP en `METER_URL`.
- `pac1`, `pac2` y `fpot1` son campos criticos para calculos energeticos.
- Un intervalo superior a `MAX_COMPLETE_INTERVAL_SECONDS` se marca incompleto y no se interpola.
- Los costes son estimaciones configurables y no pretenden igualar una factura real.
- Los periodos punta/llano/valle son configurables en precio; la asignacion horaria se mantiene simple en esta version.
- Las identificaciones de electrodomesticos procedentes de la pinza global se presentan como hipotesis, no como certezas.
- Sonoff S61S y TP-Link HS100 son candidatos futuros, no dispositivos instalados.
