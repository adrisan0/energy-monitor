# Seguridad

La version inicial esta pensada para red local.

- No publicar puertos en el router.
- Usar `API_WRITE_TOKEN` para operaciones sensibles.
- Mantener `.env` fuera de Git.
- El XML se redacta antes de guardarse o exponerse.
- Campos como `securKey`, SSID, MAC, IP interna, contrasenas y tokens se sustituyen por `[REDACTED]`.
- Las exportaciones CSV no incluyen XML crudo ni secretos.

Acceso remoto futuro recomendado: Tailscale.
