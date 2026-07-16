from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def create_db_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine_options = {"connect_args": connect_args}
    if url in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool
    database_engine = create_engine(url, **engine_options)
    if url.startswith("sqlite"):

        @event.listens_for(database_engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return database_engine


def get_session() -> Generator[Session, None, None]:
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=create_db_engine(),
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
