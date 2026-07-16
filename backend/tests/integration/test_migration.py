from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
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


def assert_phase_2a_schema(inspector) -> None:
    assert {"approved_materials", "concept_relationships", "context_review_events"} <= set(
        inspector.get_table_names()
    )
    assert {
        "reviewer_note",
        "submitted_at",
        "approved_at",
        "copied_from_context_version_id",
    } <= {column["name"] for column in inspector.get_columns("course_context_versions")}
    assert "description" in {column["name"] for column in inspector.get_columns("lessons")}
    assert {"malayalam_text", "sequence"} <= {
        column["name"] for column in inspector.get_columns("learning_objectives")
    }
    assert {"malayalam_explanation", "sequence"} <= {
        column["name"] for column in inspector.get_columns("glossary_terms")
    }
    assert {"normalized_alias"} <= {
        column["name"] for column in inspector.get_columns("term_aliases")
    }
    assert {"normalized_text", "source_note"} <= {
        column["name"] for column in inspector.get_columns("asr_misrecognitions")
    }
    assert {
        "concept_key",
        "malayalam_title",
        "definition",
        "malayalam_definition",
    } <= {column["name"] for column in inspector.get_columns("concepts")}
    assert {"malayalam_question_text", "sequence"} <= {
        column["name"] for column in inspector.get_columns("question_items")
    }
    assert "updated_at" not in {
        column["name"] for column in inspector.get_columns("context_review_events")
    }

    copied_foreign_key = next(
        foreign_key
        for foreign_key in inspector.get_foreign_keys("course_context_versions")
        if foreign_key["constrained_columns"] == ["copied_from_context_version_id"]
    )
    assert copied_foreign_key["options"].get("ondelete") == "SET NULL"
    for table_name in ("approved_materials", "concept_relationships", "context_review_events"):
        assert any(
            foreign_key["options"].get("ondelete") == "CASCADE"
            for foreign_key in inspector.get_foreign_keys(table_name)
        )

    expected_indexes = {
        "course_context_versions": {"ix_context_copied_from"},
        "learning_objectives": {"ix_objectives_lesson_sequence"},
        "glossary_terms": {"ix_glossary_lesson_sequence"},
        "term_aliases": {"ix_aliases_glossary"},
        "asr_misrecognitions": {"ix_misrecognitions_glossary"},
        "concepts": {"ix_concepts_lesson_sequence"},
        "approved_materials": {"ix_materials_lesson_sequence"},
        "concept_relationships": {
            "ix_concept_relationships_lesson",
            "ix_concept_relationships_source",
            "ix_concept_relationships_target",
        },
        "context_review_events": {"ix_review_events_context_created"},
        "generated_artifacts": {"ix_artifacts_context"},
        "question_items": {"ix_questions_lesson_sequence"},
    }
    for table_name, index_names in expected_indexes.items():
        assert index_names <= {index["name"] for index in inspector.get_indexes(table_name)}

    expected_constraints = {
        "glossary_terms": {"ck_glossary_terms_sequence", "uq_glossary_lesson_sequence"},
        "concepts": {"uq_concept_lesson_key", "uq_concept_lesson_sequence"},
        "approved_materials": {
            "ck_materials_sequence",
            "uq_material_lesson_sequence",
            "material_type",
            "material_language",
            "material_teacher_review_status",
        },
        "concept_relationships": {
            "ck_relationship_not_self",
            "ck_relationship_sequence",
            "uq_relationship_tuple",
            "uq_relationship_lesson_sequence",
            "concept_relationship_type",
        },
        "context_review_events": {"context_review_event_type"},
        "question_items": {
            "ck_question_items_sequence",
            "uq_question_lesson_sequence",
            "question_source_type",
        },
    }
    for table_name, constraint_names in expected_constraints.items():
        actual_names = {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        } | {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
        assert constraint_names <= actual_names


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


def test_phase_2a_migration_is_explicit_and_follows_phase_1() -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260716_0002_phase_2a_curriculum_schema.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert 'down_revision: str | None = "20260715_0001"' in source
    assert "op.create_table" in source
    assert "op.batch_alter_table" in source
    assert "Base.metadata" not in source
    assert "create_all" not in source
    assert "drop_all" not in source
    assert "app.models" not in source


def test_phase_2a_empty_database_lifecycle_and_schema_inspection(tmp_path) -> None:
    database_path = tmp_path / "phase-2a-lifecycle.db"
    config = migration_config(database_path)

    command.upgrade(config, "head")
    assert_phase_2a_schema(inspect(create_engine(f"sqlite:///{database_path.as_posix()}")))

    command.downgrade(config, "20260715_0001")
    phase_1_inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert "approved_materials" not in phase_1_inspector.get_table_names()
    assert "description" not in {
        column["name"] for column in phase_1_inspector.get_columns("lessons")
    }
    assert "copied_from_context_version_id" not in {
        column["name"] for column in phase_1_inspector.get_columns("course_context_versions")
    }

    command.upgrade(config, "head")
    assert_phase_2a_schema(inspect(create_engine(f"sqlite:///{database_path.as_posix()}")))

    command.downgrade(config, "base")
    base_inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert set(base_inspector.get_table_names()) <= {"alembic_version"}

    command.upgrade(config, "head")
    assert_phase_2a_schema(inspect(create_engine(f"sqlite:///{database_path.as_posix()}")))


def test_phase_2a_preserves_compatible_phase_1_parent_rows(tmp_path) -> None:
    database_path = tmp_path / "phase-2a-parent-rows.db"
    config = migration_config(database_path)
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    command.upgrade(config, "20260715_0001")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO courses "
                "(id, created_at, updated_at, title, subject, class_level, grade_band) "
                "VALUES ('course-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'Science', 'Science', 7, '5-7')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO course_context_versions "
                "(id, created_at, updated_at, course_id, version_number, teacher_review_status) "
                "VALUES ('context-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'course-1', 1, 'DRAFT')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters "
                "(id, created_at, updated_at, context_version_id, title, sequence) "
                "VALUES ('chapter-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'context-1', 'Plants', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO lessons "
                "(id, created_at, updated_at, chapter_id, title, sequence, primary_language) "
                "VALUES ('lesson-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'chapter-1', 'Photosynthesis', 1, 'ml')"
            )
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM courses")).scalar_one() == "course-1"
        assert (
            connection.execute(text("SELECT id FROM course_context_versions")).scalar_one()
            == "context-1"
        )
        assert connection.execute(text("SELECT id FROM chapters")).scalar_one() == "chapter-1"
        assert connection.execute(text("SELECT id FROM lessons")).scalar_one() == "lesson-1"
        assert connection.execute(
            text(
                "SELECT reviewer_note, submitted_at, approved_at, copied_from_context_version_id "
                "FROM course_context_versions"
            )
        ).one() == (None, None, None, None)
        assert connection.execute(text("SELECT description FROM lessons")).scalar_one() is None

    command.downgrade(config, "20260715_0001")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM courses")).scalar_one() == "course-1"
        assert (
            connection.execute(text("SELECT id FROM course_context_versions")).scalar_one()
            == "context-1"
        )
        assert connection.execute(text("SELECT id FROM chapters")).scalar_one() == "chapter-1"
        assert connection.execute(text("SELECT id FROM lessons")).scalar_one() == "lesson-1"


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
        concept = Concept(
            lesson_id=lesson.id,
            concept_key="inputs",
            title="Inputs",
            definition="Plants need inputs to make food.",
            sequence=1,
        )
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


def test_phase_2a_database_constraints_and_delete_actions(tmp_path) -> None:
    database_path = tmp_path / "phase-2a-integrity.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(
            text(
                "INSERT INTO courses "
                "(id, created_at, updated_at, title, subject, class_level, grade_band) "
                "VALUES ('course-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'Science', 'Science', 7, '5-7')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO course_context_versions "
                "(id, created_at, updated_at, course_id, version_number, teacher_review_status) "
                "VALUES ('context-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'course-1', 1, 'DRAFT'), "
                "('context-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'course-1', 2, 'DRAFT')"
            )
        )
        connection.execute(
            text(
                "UPDATE course_context_versions SET copied_from_context_version_id = 'context-1' "
                "WHERE id = 'context-2'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters "
                "(id, created_at, updated_at, context_version_id, title, sequence) "
                "VALUES ('chapter-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'context-2', 'Plants', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO lessons "
                "(id, created_at, updated_at, chapter_id, title, sequence, primary_language) "
                "VALUES ('lesson-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "'chapter-1', 'Photosynthesis', 1, 'ml')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO concepts "
                "(id, created_at, updated_at, lesson_id, concept_key, title, definition, sequence) "
                "VALUES ('concept-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                "'plant-inputs', 'Plant inputs', 'Plants need inputs.', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO approved_materials "
                "(id, created_at, updated_at, lesson_id, title, material_type, source_label, "
                "content, language, sequence, teacher_review_status) "
                "VALUES ('material-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                "'Teacher note', 'teacher_note', 'Teacher', 'Approved text.', "
                "'bilingual', 1, 'DRAFT')"
            )
        )

    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO approved_materials "
                    "(id, created_at, updated_at, lesson_id, title, material_type, source_label, "
                    "content, language, sequence, teacher_review_status) "
                    "VALUES ('material-duplicate', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                    "'lesson-1', "
                    "'Duplicate', 'teacher_note', 'Teacher', 'Text.', 'en', 1, 'DRAFT')"
                )
            )
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO approved_materials "
                    "(id, created_at, updated_at, lesson_id, title, material_type, source_label, "
                    "content, language, sequence, teacher_review_status) "
                    "VALUES ('material-zero', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                    "'Invalid order', 'teacher_note', 'Teacher', 'Text.', 'en', 0, 'DRAFT')"
                )
            )
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO concept_relationships "
                    "(id, created_at, updated_at, lesson_id, source_concept_id, target_concept_id, "
                    "relationship_type, sequence) "
                    "VALUES ('relationship-self', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                    "'lesson-1', "
                    "'concept-1', 'concept-1', 'related_to', 1)"
                )
            )
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO question_items "
                    "(id, created_at, updated_at, lesson_id, source_type, source_label, "
                    "question_text, "
                    "sequence, teacher_review_status) "
                    "VALUES ('question-invalid-source', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                    "'lesson-1', 'unapproved_source', 'Teacher', 'What do plants need?', 1, "
                    "'DRAFT')"
                )
            )
        connection.rollback()
        connection.execute(text("DELETE FROM course_context_versions WHERE id = 'context-1'"))
        connection.commit()
        assert (
            connection.execute(
                text(
                    "SELECT copied_from_context_version_id FROM course_context_versions "
                    "WHERE id = 'context-2'"
                )
            ).scalar_one()
            is None
        )
        connection.execute(text("DELETE FROM lessons WHERE id = 'lesson-1'"))
        connection.commit()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM approved_materials WHERE id = 'material-1'")
            ).scalar_one()
            == 0
        )
