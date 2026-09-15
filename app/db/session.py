from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.base import Base


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite:///"):
        database_path = Path(url.removeprefix("sqlite:///"))
        if str(database_path) != ":memory:":
            database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, future=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine or create_database_engine(),
        class_=Session,
        expire_on_commit=False,
    )


engine = create_database_engine()
SessionLocal = create_session_factory(engine)


def init_db(target_engine: Engine | None = None) -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(target_engine or engine)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

