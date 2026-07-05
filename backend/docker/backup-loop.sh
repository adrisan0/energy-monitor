#!/usr/bin/env sh
set -eu

interval="${BACKUP_SCHEDULE_SECONDS:-86400}"

while true; do
  python -m app.services.backup run-scheduled || true
  sleep "$interval"
done
