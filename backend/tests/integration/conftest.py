from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.api.dependencies import get_session
from app.db.session import create_db_engine
from app.main import create_app


@dataclass(frozen=True)
class MigratedApiHarness:
    """A real API client backed by an Alembic-migrated temporary SQLite database."""

    app: FastAPI
    client: TestClient
    session_factory: sessionmaker[Session]


def _migration_config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@pytest.fixture()
def migrated_api(tmp_path: Path) -> Generator[MigratedApiHarness, None, None]:
    """Provide a file-backed, foreign-key-enforced database upgraded to Alembic head."""

    database_path = tmp_path / "api.db"
    command.upgrade(_migration_config(database_path), "head")
    engine = create_db_engine(f"sqlite:///{database_path.as_posix()}")
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield MigratedApiHarness(app=app, client=client, session_factory=session_factory)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
