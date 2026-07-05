from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SIMULATION_MODE"] = "true"
os.environ["API_WRITE_TOKEN"] = "test-token"
os.environ["BACKUP_DIR"] = str(Path.cwd() / ".test-backups")

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session_factory, init_engine
from app.services.bootstrap import ensure_initial_data


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None, None, None]:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("SIMULATION_MODE", "true")
    monkeypatch.setenv("API_WRITE_TOKEN", "test-token")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    get_settings.cache_clear()
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with get_session_factory()() as db:
        ensure_initial_data(db)
        db.commit()
    yield
    Base.metadata.drop_all(get_engine())
