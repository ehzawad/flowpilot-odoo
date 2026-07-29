from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=8)
def get_engine(
    database_url: str,
    pool_size: int = 5,
    max_overflow: int = 5,
    pool_timeout: int = 15,
) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
        )
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(
    database_url: str,
    *,
    organization_id: str | None = None,
) -> Iterator[Session]:
    session = get_session_factory(database_url)()
    try:
        if organization_id and session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
                {"organization_id": organization_id},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema(database_url: str) -> None:
    from flowpilot.db import models  # noqa: F401

    Base.metadata.create_all(get_engine(database_url))


def clear_engine_cache() -> None:
    """Discard cached engine objects between isolated tests or configuration changes."""
    get_engine.cache_clear()
