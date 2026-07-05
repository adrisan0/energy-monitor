from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import desc, select, text

from app.core.config import get_settings
from app.core.timezone import local_zone, to_local, to_utc, utc_now
from app.db.session import get_session_factory, init_engine
from app.models import MeterSample
from app.services.backup import run_backup
from app.services.exporter import iter_measurement_csv

app = typer.Typer(help="Consola local de Energy Home Monitor")
backup_app = typer.Typer(help="Operaciones de backup")
system_app = typer.Typer(help="Estado del sistema")
app.add_typer(backup_app, name="backup")
app.add_typer(system_app, name="system")
console = Console()


def _ensure_db() -> None:
    init_engine()


@app.command()
def status(as_json: Annotated[bool, typer.Option("--json", help="Salida JSON")] = False) -> None:
    """Muestra la ultima lectura calculada."""
    _ensure_db()
    with get_session_factory()() as db:
        sample = _latest_usable_sample(db) or db.scalar(select(MeterSample).order_by(desc(MeterSample.timestamp_utc)).limit(1))
        if sample is None:
            _print({"status": "sin_lecturas"}, as_json)
            return
        payload = _sample_payload(sample)
        payload["seconds_since_last_reading"] = (utc_now() - _aware(sample.timestamp_utc)).total_seconds()
        _print(payload, as_json)


@app.command()
def watch(
    as_json: Annotated[bool, typer.Option("--json", help="Salida JSON")] = False,
    once: Annotated[bool, typer.Option("--once", help="Solo una iteracion")] = False,
) -> None:
    """Actualiza el estado cada 60 segundos por defecto."""
    interval = get_settings().meter_poll_interval_seconds
    while True:
        status(as_json=as_json)
        if once:
            return
        time.sleep(interval)


@app.command()
def raw(as_json: Annotated[bool, typer.Option("--json", help="Salida JSON")] = False) -> None:
    """Muestra el ultimo XML redactado y variables derivadas."""
    _ensure_db()
    with get_session_factory()() as db:
        sample = db.scalar(select(MeterSample).order_by(desc(MeterSample.timestamp_utc)).limit(1))
        if sample is None:
            _print({"status": "sin_payloads"}, as_json)
            return
        payload = {
            "id": sample.id,
            "timestamp_utc": sample.timestamp_utc.isoformat(),
            "data_quality": sample.data_quality,
            "raw_variables": sample.raw_variables,
            "raw_payload_redacted": sample.raw_payload_redacted,
            "calculated": _sample_payload(sample),
        }
        _print(payload, as_json, raw_xml=sample.raw_payload_redacted)


@app.command()
def history(
    day: Annotated[str | None, typer.Option("--day", help="today, yesterday o YYYY-MM-DD")] = None,
    from_: Annotated[datetime | None, typer.Option("--from", help="Inicio ISO")] = None,
    to: Annotated[datetime | None, typer.Option("--to", help="Fin ISO")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Salida JSON")] = False,
) -> None:
    """Consulta lecturas historicas."""
    _ensure_db()
    start, end = _history_range(day, from_, to)
    with get_session_factory()() as db:
        rows = list(
            db.scalars(
                select(MeterSample)
                .where(MeterSample.timestamp_utc >= start, MeterSample.timestamp_utc <= end)
                .order_by(MeterSample.timestamp_utc.asc())
                .limit(500)
            )
        )
        payload = [_sample_payload(row) for row in rows]
        _print({"start": start.isoformat(), "end": end.isoformat(), "count": len(rows), "items": payload}, as_json)


@app.command("export")
def export_cmd(
    output: Annotated[Path, typer.Option("--output", "-o", help="Archivo CSV")],
    from_: Annotated[datetime | None, typer.Option("--from", help="Inicio ISO")] = None,
    to: Annotated[datetime | None, typer.Option("--to", help="Fin ISO")] = None,
) -> None:
    """Exporta lecturas a CSV sin campos sensibles."""
    _ensure_db()
    with get_session_factory()() as db:
        start, end = _history_range(None, from_, to)
        output.write_text(
            "".join(iter_measurement_csv(db, start=start, end=end, data_quality=None)),
            encoding="utf-8",
        )
    console.print(f"CSV exportado: {output}")


@backup_app.command("run")
def backup_run(as_json: Annotated[bool, typer.Option("--json", help="Salida JSON")] = False) -> None:
    """Ejecuta un backup manual comprimido."""
    _ensure_db()
    with get_session_factory()() as db:
        record = run_backup(db)
        db.commit()
        _print(
            {
                "filename": record.filename,
                "status": record.status,
                "path": record.path,
                "size_bytes": record.size_bytes,
                "checksum_sha256": record.checksum_sha256,
                "error_message": record.error_message,
            },
            as_json,
        )


@system_app.command("check")
def system_check(as_json: Annotated[bool, typer.Option("--json", help="Salida JSON")] = False) -> None:
    """Comprueba base de datos y estado basico del medidor."""
    _ensure_db()
    with get_session_factory()() as db:
        db.execute(text("select 1"))
        sample = db.scalar(select(MeterSample).order_by(desc(MeterSample.timestamp_utc)).limit(1))
        payload = {
            "database": "ok",
            "latest_sample_at": sample.timestamp_utc.isoformat() if sample else None,
            "latest_data_quality": sample.data_quality if sample else None,
            "simulation_mode": get_settings().simulation_mode,
        }
        _print(payload, as_json)


def _history_range(
    day: str | None,
    from_value: datetime | None,
    to_value: datetime | None,
) -> tuple[datetime, datetime]:
    if day:
        local_now = to_local(utc_now())
        if day == "today":
            local_day = local_now.date()
        elif day == "yesterday":
            local_day = (local_now - timedelta(days=1)).date()
        else:
            local_day = datetime.fromisoformat(day).date()
        start_local = datetime.combine(local_day, datetime.min.time(), tzinfo=local_zone())
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)
    end = to_utc(to_value) if to_value else utc_now()
    start = to_utc(from_value) if from_value else end - timedelta(hours=24)
    return start, end


def _sample_payload(sample: MeterSample) -> dict[str, object]:
    return {
        "id": sample.id,
        "timestamp": sample.timestamp_local.isoformat(),
        "solar_w": _float(sample.solar_w),
        "grid_import_w": _float(sample.grid_import_w),
        "grid_export_w": _float(sample.grid_export_w),
        "house_consumption_w": _float(sample.house_consumption_w),
        "solar_self_consumption_w": _float(sample.solar_self_consumption_w),
        "solar_self_consumption_percent": _float(sample.solar_self_consumption_percent),
        "data_quality": sample.data_quality,
        "poll_duration_ms": sample.poll_duration_ms,
    }


def _latest_usable_sample(db: Any) -> MeterSample | None:
    return db.scalar(
        select(MeterSample)
        .where(MeterSample.data_quality.in_(["valid", "partial"]))
        .order_by(desc(MeterSample.timestamp_utc))
        .limit(1)
    )


def _print(payload: Mapping[str, object], as_json: bool, raw_xml: str | None = None) -> None:
    if as_json:
        console.print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    if raw_xml:
        console.rule("XML redactado")
        console.print(raw_xml)
        console.rule("Valores")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Campo")
    table.add_column("Valor")
    for key, value in payload.items():
        if key == "items" and isinstance(value, list):
            table.add_row(key, f"{len(value)} filas")
        else:
            rendered = (
                json.dumps(value, ensure_ascii=False, default=str)
                if isinstance(value, (dict, list))
                else str(value)
            )
            table.add_row(str(key), rendered)
    console.print(table)


def _float(value: Any) -> float | None:
    return None if value is None else float(value)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def entrypoint() -> None:
    app()


if __name__ == "__main__":
    entrypoint()
