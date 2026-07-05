from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import subprocess
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.timezone import utc_now
from app.db.session import get_session_factory, init_engine
from app.models import BackupRecord


def run_backup(db: Session) -> BackupRecord:
    settings = get_settings()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    created_at = utc_now()
    filename = f"energy_{created_at.strftime('%Y%m%dT%H%M%SZ')}.sql.gz"
    path = settings.backup_dir / filename
    record = BackupRecord(filename=filename, path=str(path), status="running", created_at=created_at)
    db.add(record)
    db.flush()

    try:
        if settings.database_url.startswith("sqlite"):
            _write_sqlite_placeholder(path)
        else:
            _pg_dump_to_gzip(path)
        size = path.stat().st_size
        if size <= 0:
            raise RuntimeError("El backup se creo vacio")
        record.size_bytes = size
        record.checksum_sha256 = _sha256(path)
        record.status = "ok"
        record.finished_at = utc_now()
        rotate_backups(db)
    except Exception as exc:  # noqa: BLE001
        record.status = "error"
        record.error_message = str(exc)
        record.finished_at = utc_now()
    db.flush()
    return record


def rotate_backups(db: Session) -> None:
    settings = get_settings()
    cutoff = utc_now() - timedelta(days=settings.backup_retention_days)
    old_records = list(
        db.scalars(
            select(BackupRecord).where(
                BackupRecord.created_at < cutoff,
                BackupRecord.status == "ok",
            )
        )
    )
    for record in old_records:
        path = Path(record.path)
        if path.exists():
            path.unlink()
        record.status = "rotated"
        record.finished_at = utc_now()


def list_backup_files(db: Session) -> list[BackupRecord]:
    return list(db.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(200)))


def _pg_dump_to_gzip(path: Path) -> None:
    settings = get_settings()
    env = os.environ.copy()
    env["PGPASSWORD"] = settings.postgres_password
    command = [
        "pg_dump",
        "-h",
        settings.postgres_host,
        "-p",
        str(settings.postgres_port),
        "-U",
        settings.postgres_user,
        "-d",
        settings.postgres_db,
        "--no-owner",
        "--no-acl",
    ]
    with path.open("wb") as output, gzip.GzipFile(fileobj=output, mode="wb") as gz_file:
        proc = subprocess.run(command, env=env, capture_output=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))
        gz_file.write(proc.stdout)


def _write_sqlite_placeholder(path: Path) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as file:
        file.write("-- sqlite test backup placeholder\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run-scheduled"])
    parser.parse_args()
    setup_logging()
    init_engine()
    with get_session_factory()() as db:
        run_backup(db)
        db.commit()


if __name__ == "__main__":
    cli()
