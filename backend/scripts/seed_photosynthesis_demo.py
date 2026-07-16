from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.session import create_db_engine
from app.demo.photosynthesis_fixture import DemoFixtureConflictError, seed_photosynthesis_demo


def _at_alembic_head(engine) -> bool:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    expected = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    return current == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or reset the Shravya Photosynthesis demo.")
    parser.add_argument("--reset", action="store_true", help="Restore only the locked demo course.")
    args = parser.parse_args(argv)
    engine = None
    try:
        engine = create_db_engine(get_settings().database_url)
        if not _at_alembic_head(engine):
            print(
                "Database is not at Alembic head. Run: python -m alembic upgrade head",
                file=sys.stderr,
            )
            return 1
        session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
        try:
            result = seed_photosynthesis_demo(session, reset=args.reset)
        finally:
            session.close()
        state = "created" if result.created else "reused"
        print("Shravya Photosynthesis demo ready")
        print(f"Course: {result.course_id}")
        print(f"Approved context v1: {result.context_v1_id}")
        print(f"Draft context v2: {result.context_v2_id}")
        print("Student-visible version: 1")
        print("Artifact state: ready")
        print(f"Fixture: {state}")
        return 0
    except DemoFixtureConflictError:
        print("Demo baseline conflict. Re-run this command with --reset.", file=sys.stderr)
        return 1
    except Exception:
        print("Demo setup failed. Check database setup and try again.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
