from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from alembic import command
from app.contracts.enums import ConceptState
from app.db.base import Base
from app.models.foundation import (
    Chapter,
    Concept,
    Course,
    CourseContextVersion,
    LearnerConceptState,
    LocalLearnerProfile,
)


def migration_config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def test_initial_migration_is_explicit_and_reversible(tmp_path) -> None:
    database_path = tmp_path / "migration.db"
    config = migration_config(database_path)
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260715_0001_phase_1_foundation.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert "op.create_table" in source
    assert "op.create_index" in source
    assert "Base.metadata" not in source
    assert "create_all" not in source
    assert "drop_all" not in source

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {
        "courses",
        "generated_artifacts",
        "transcript_quality_reasons",
        "term_suggestions",
    } <= tables
    assert {column["name"] for column in inspector.get_columns("generated_artifacts")} >= {
        "source_status",
        "uncertainty_status",
        "uncertainty_note",
        "generation_status",
    }
    assert any(
        constraint["name"] == "ck_courses_class_level"
        for constraint in inspector.get_check_constraints("courses")
    )
    assert any(
        constraint["name"] == "ck_courses_grade_band"
        for constraint in inspector.get_check_constraints("courses")
    )
    assert any(
        constraint["name"] == "ck_transcript_segments_end"
        for constraint in inspector.get_check_constraints("transcript_segments")
    )
    assert any(
        foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in inspector.get_foreign_keys("lessons")
    )
    assert any(
        index["name"] == "ix_artifacts_lesson"
        for index in inspector.get_indexes("generated_artifacts")
    )

    command.downgrade(config, "base")
    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert set(inspector.get_table_names()) <= {"alembic_version"}

    command.upgrade(config, "head")
    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert "generated_artifacts" in inspector.get_table_names()


def test_migrated_schema_matches_metadata_and_persists_concept_state_values(tmp_path) -> None:
    database_path = tmp_path / "parity.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, Base.metadata) == []

    with Session(engine) as session:
        course = Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
        session.add(course)
        session.flush()
        context = CourseContextVersion(course_id=course.id, version_number=1)
        session.add(context)
        session.flush()
        chapter = Chapter(context_version_id=context.id, title="Plants", sequence=1)
        session.add(chapter)
        session.flush()
        from app.models.foundation import Lesson

        lesson = Lesson(chapter_id=chapter.id, title="Photosynthesis", sequence=1)
        profile = LocalLearnerProfile(local_key="parity-profile")
        session.add_all([lesson, profile])
        session.flush()
        concept = Concept(lesson_id=lesson.id, title="Inputs", sequence=1)
        session.add(concept)
        session.flush()
        state = LearnerConceptState(
            learner_profile_id=profile.id,
            concept_id=concept.id,
            state=ConceptState.NOT_STARTED,
        )
        session.add(state)
        session.commit()
        assert state.state is ConceptState.NOT_STARTED
