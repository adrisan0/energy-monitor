from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_engine_url: str | None = None


def _engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            kwargs["poolclass"] = StaticPool
    return kwargs


def init_engine(database_url: str | None = None) -> Engine:
    global _engine, _session_factory, _engine_url
    url = database_url or get_settings().database_url
    if _engine is not None and _engine_url == url:
        return _engine
    _engine = create_engine(url, **_engine_kwargs(url))
    _engine_url = url
    _session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
