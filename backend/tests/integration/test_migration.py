# ruff: noqa: E501

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
    ConceptGlossaryTermLink,
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
    engine.dispose()


def test_phase_4c_local_stt_evidence_migration_lifecycle(tmp_path) -> None:
    database_path = tmp_path / "local-stt-evidence.db"
    config = migration_config(database_path)

    command.upgrade(config, "20260721_0004")
    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert "transcription_run_evidence" not in inspector.get_table_names()
    assert "audio_format" not in {
        column["name"] for column in inspector.get_columns("lecture_audio")
    }

    command.upgrade(config, "20260723_0005")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = inspect(engine)
    assert "transcription_run_evidence" in inspector.get_table_names()
    assert {
        "source_sha256",
        "model_identifier",
        "raw_provider_output_json",
        "inference_seconds",
    } <= {column["name"] for column in inspector.get_columns("transcription_run_evidence")}
    assert {
        "audio_format",
        "sample_rate_hz",
        "channel_count",
        "sample_width_bits",
        "frame_count",
    } <= {column["name"] for column in inspector.get_columns("lecture_audio")}
    assert "ix_transcription_evidence_source_sha256" in {
        index["name"] for index in inspector.get_indexes("transcription_run_evidence")
    }
    assert {
        ("transcript_revision_id", "transcript_revisions", "CASCADE"),
        ("source_lecture_audio_id", "lecture_audio", "CASCADE"),
    } <= {
        (
            foreign_key["constrained_columns"][0],
            foreign_key["referred_table"],
            foreign_key["options"].get("ondelete"),
        )
        for foreign_key in inspector.get_foreign_keys("transcription_run_evidence")
    }
    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, Base.metadata) == []
    engine.dispose()

    command.downgrade(config, "20260721_0004")
    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert "transcription_run_evidence" not in inspector.get_table_names()
    assert "audio_format" not in {
        column["name"] for column in inspector.get_columns("lecture_audio")
    }

    command.upgrade(config, "20260723_0005")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM transcription_run_evidence")).scalar_one()
            == 0
        )
        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, Base.metadata) == []
    engine.dispose()


def test_phase_4b2a_recovery_pack_migration_enforces_context_owned_concepts(tmp_path) -> None:
    database_path = tmp_path / "recovery-packs.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260717_0003")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.execute(
            text(
                "INSERT INTO courses (id, created_at, updated_at, title, subject, class_level, grade_band) "
                "VALUES ('course-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'Science', 'Science', 7, '5-7')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO course_context_versions (id, created_at, updated_at, course_id, version_number, teacher_review_status) "
                "VALUES ('context-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'course-1', 1, 'APPROVED'), "
                "('context-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'course-1', 2, 'DRAFT')"
            )
        )
        for context_id, chapter_id, lesson_id, concept_id in (
            ("context-1", "chapter-1", "lesson-1", "concept-1"),
            ("context-2", "chapter-2", "lesson-2", "concept-2"),
        ):
            connection.execute(
                text(
                    "INSERT INTO chapters (id, created_at, updated_at, context_version_id, title, sequence) "
                    "VALUES (:chapter_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :context_id, 'Plants', 1)"
                ),
                {"chapter_id": chapter_id, "context_id": context_id},
            )
            connection.execute(
                text(
                    "INSERT INTO lessons (id, created_at, updated_at, chapter_id, title, sequence, primary_language) "
                    "VALUES (:lesson_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :chapter_id, 'Photosynthesis', 1, 'ml')"
                ),
                {"lesson_id": lesson_id, "chapter_id": chapter_id},
            )
            connection.execute(
                text(
                    "INSERT INTO concepts (id, created_at, updated_at, lesson_id, concept_key, title, definition, sequence) "
                    "VALUES (:concept_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :lesson_id, :concept_id, 'Concept', 'Definition', 1)"
                ),
                {"concept_id": concept_id, "lesson_id": lesson_id},
            )

    command.upgrade(config, "20260721_0004")

    ownership_trigger_names = {
        "trg_concepts_context_version_insert",
        "trg_concepts_context_version_update",
        "trg_lessons_concept_context_version_update",
        "trg_chapters_concept_context_version_update",
    }

    def current_ownership_trigger_names(connection) -> set[str]:
        return set(
            connection.scalars(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND name IN ("
                    "'trg_concepts_context_version_insert', "
                    "'trg_concepts_context_version_update', "
                    "'trg_lessons_concept_context_version_update', "
                    "'trg_chapters_concept_context_version_update'"
                    ")"
                )
            )
        )

    def insert_pack(connection, pack_id: str, context_id: str, concept_id: str) -> None:
        connection.execute(
            text(
                "INSERT INTO concept_recovery_packs "
                "(id, created_at, updated_at, context_version_id, concept_id, cue_en, cue_ml, "
                "example_en, example_ml, alternate_explanation_en, alternate_explanation_ml, teacher_review_status) "
                "VALUES (:pack_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :context_id, :concept_id, "
                "'Cue', 'സൂചന', 'Example', 'ഉദാഹരണം', 'Alternate', 'മറ്റൊരു വിശദീകരണം', 'DRAFT')"
            ),
            {"pack_id": pack_id, "context_id": context_id, "concept_id": concept_id},
        )

    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert current_ownership_trigger_names(connection) == ownership_trigger_names
        assert (
            connection.execute(
                text("SELECT context_version_id FROM concepts WHERE id = 'concept-1'")
            ).scalar_one()
            == "context-1"
        )
        connection.execute(
            text(
                "INSERT INTO concepts "
                "(id, created_at, updated_at, lesson_id, context_version_id, concept_key, title, definition, sequence) "
                "VALUES ('concept-valid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                "'context-1', 'concept-valid', 'Valid concept', 'Definition', 2)"
            )
        )
        connection.commit()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO concepts "
                    "(id, created_at, updated_at, lesson_id, context_version_id, concept_key, title, definition, sequence) "
                    "VALUES ('concept-invalid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                    "'context-2', 'concept-invalid', 'Invalid concept', 'Definition', 3)"
                )
            )
        connection.rollback()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM concepts WHERE id = 'concept-invalid'")
            ).scalar_one()
            == 0
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "UPDATE concepts SET context_version_id = 'context-2' WHERE id = 'concept-valid'"
                )
            )
        connection.rollback()
        assert (
            connection.execute(
                text("SELECT context_version_id FROM concepts WHERE id = 'concept-valid'")
            ).scalar_one()
            == "context-1"
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE lessons SET chapter_id = 'chapter-2' WHERE id = 'lesson-1'")
            )
        connection.rollback()
        assert (
            connection.execute(
                text("SELECT chapter_id FROM lessons WHERE id = 'lesson-1'")
            ).scalar_one()
            == "chapter-1"
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE chapters SET context_version_id = 'context-2' WHERE id = 'chapter-1'")
            )
        connection.rollback()
        assert (
            connection.execute(
                text("SELECT context_version_id FROM chapters WHERE id = 'chapter-1'")
            ).scalar_one()
            == "context-1"
        )
        connection.execute(
            text("UPDATE concepts SET title = 'Refined concept' WHERE id = 'concept-valid'")
        )
        connection.commit()
        assert (
            connection.execute(
                text("SELECT title FROM concepts WHERE id = 'concept-valid'")
            ).scalar_one()
            == "Refined concept"
        )
        insert_pack(connection, "pack-1", "context-1", "concept-1")
        insert_pack(connection, "pack-2", "context-2", "concept-2")
        connection.commit()
        for pack_id, context_id, concept_id in (
            ("pack-duplicate", "context-1", "concept-1"),
            ("pack-cross-1", "context-1", "concept-2"),
            ("pack-cross-2", "context-2", "concept-1"),
        ):
            with pytest.raises(IntegrityError):
                insert_pack(connection, pack_id, context_id, concept_id)
            connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "UPDATE concept_recovery_packs SET concept_id = 'concept-2' WHERE id = 'pack-1'"
                )
            )
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "UPDATE concept_recovery_packs SET context_version_id = 'context-2' "
                    "WHERE id = 'pack-1'"
                )
            )
        connection.rollback()
        connection.execute(text("DELETE FROM concepts WHERE id = 'concept-1'"))
        connection.commit()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM concept_recovery_packs WHERE id = 'pack-1'")
            ).scalar_one()
            == 0
        )
    command.downgrade(config, "20260717_0003")
    with engine.connect() as connection:
        assert current_ownership_trigger_names(connection) == set()
    command.upgrade(config, "20260721_0004")
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert current_ownership_trigger_names(connection) == ownership_trigger_names
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO concepts "
                    "(id, created_at, updated_at, lesson_id, context_version_id, concept_key, title, definition, sequence) "
                    "VALUES ('concept-invalid-reupgrade', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-2', "
                    "'context-1', 'concept-invalid-reupgrade', 'Invalid concept', 'Definition', 2)"
                )
            )
        connection.rollback()
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE concepts SET context_version_id = 'context-1' WHERE id = 'concept-2'")
            )
        connection.rollback()
        assert (
            connection.execute(
                text("SELECT context_version_id FROM concepts WHERE id = 'concept-2'")
            ).scalar_one()
            == "context-2"
        )
        with pytest.raises(IntegrityError):
            insert_pack(connection, "pack-cross-reupgrade", "context-1", "concept-2")
        connection.rollback()
        insert_pack(connection, "pack-cascade", "context-2", "concept-2")
        connection.commit()
        connection.execute(text("DELETE FROM course_context_versions WHERE id = 'context-2'"))
        connection.commit()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM concept_recovery_packs WHERE id = 'pack-cascade'")
            ).scalar_one()
            == 0
        )
    engine.dispose()

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
                "(id, created_at, updated_at, lesson_id, context_version_id, concept_key, title, definition, sequence) "
                "VALUES ('concept-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                "'context-2', 'plant-inputs', 'Plant inputs', 'Plants need inputs.', 1)"
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


def _insert_phase_2_parent_graph(connection) -> None:
    connection.execute(
        text(
            "INSERT INTO courses (id, created_at, updated_at, title, subject, class_level, grade_band) "
            "VALUES ('course-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'Science', 'Science', 7, '5-7')"
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
            "INSERT INTO chapters (id, created_at, updated_at, context_version_id, title, sequence) "
            "VALUES ('chapter-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-1', 'Plants', 1)"
        )
    )
    connection.execute(
        text(
            "INSERT INTO lessons (id, created_at, updated_at, chapter_id, title, sequence, primary_language) "
            "VALUES ('lesson-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'chapter-1', 'Photosynthesis', 1, 'ml')"
        )
    )


def test_phase_3b_backfills_populated_legacy_audio_and_job_rows(tmp_path) -> None:
    database_path = tmp_path / "phase-3b-populated-legacy.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260716_0002")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        _insert_phase_2_parent_graph(connection)
        connection.execute(
            text(
                "INSERT INTO lecture_audio "
                "(id, created_at, updated_at, lesson_id, storage_path, mime_type, source_status) "
                "VALUES ('audio-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', 'legacy.wav', 'audio/wav', 'DEMO')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO transcript_revisions "
                "(id, created_at, updated_at, lecture_audio_id, revision_number, source_status, language) "
                "VALUES ('revision-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'audio-1', 1, 'DEMO', 'ml')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO processing_jobs "
                "(id, created_at, updated_at, lesson_id, job_type, entity_id, status, progress_message, retry_count) "
                "VALUES ('job-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', 'TRANSCRIPTION', 'audio-1', "
                "'PROCESSING', 'legacy', 0)"
            )
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT original_filename, byte_size, length(sha256), duration_ms, workflow_status "
                "FROM lecture_audio WHERE id = 'audio-1'"
            )
        ).one() == ("legacy-recording.wav", 1, 64, 1, "UPLOADED")
        assert connection.execute(
            text(
                "SELECT provider_name, provenance_label, teacher_review_status "
                "FROM transcript_revisions WHERE id = 'revision-1'"
            )
        ).one() == (
            "legacy-migrated",
            "Legacy transcript record — provenance unavailable",
            "DRAFT",
        )
        assert (
            connection.execute(
                text("SELECT status FROM processing_jobs WHERE id = 'job-1'")
            ).scalar_one()
            == "RUNNING"
        )


@pytest.mark.parametrize(
    ("head_status", "legacy_status"),
    [("QUEUED", "QUEUED"), ("RUNNING", "PROCESSING"), ("SUCCEEDED", "COMPLETED")],
)
def test_phase_3b_job_status_downgrade_and_reupgrade_is_reversible(
    tmp_path, head_status: str, legacy_status: str
) -> None:
    database_path = tmp_path / f"phase-3b-{head_status}.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260716_0002")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        _insert_phase_2_parent_graph(connection)
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO processing_jobs "
                "(id, created_at, updated_at, lesson_id, job_type, entity_id, status, progress_message, retry_count) "
                "VALUES ('job-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', 'TRANSCRIPTION', 'audio-1', "
                ":status, 'phase-3b', 0)"
            ),
            {"status": head_status},
        )
    command.downgrade(config, "20260716_0002")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT status FROM processing_jobs WHERE id = 'job-1'")
            ).scalar_one()
            == legacy_status
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT status FROM processing_jobs WHERE id = 'job-1'")
            ).scalar_one()
            == head_status
        )
        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, Base.metadata) == []
    engine.dispose()


def test_phase_3b_archives_duplicate_legacy_jobs_without_fabricating_entity_ids(tmp_path) -> None:
    database_path = tmp_path / "phase-3b-duplicate-jobs.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260716_0002")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        _insert_phase_2_parent_graph(connection)
        for job_id, status, error_code, retry_count in (
            ("job-a", "PROCESSING", None, 0),
            ("job-b", "COMPLETED", "legacy-complete", 2),
            ("job-c", "FAILED", "legacy-failure", 3),
        ):
            connection.execute(
                text(
                    "INSERT INTO processing_jobs "
                    "(id, created_at, updated_at, lesson_id, job_type, entity_id, status, "
                    "progress_message, error_code, retry_count) VALUES "
                    f"('{job_id}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                    "'TRANSCRIPTION', 'audio-1', :status, 'legacy duplicate', :error_code, "
                    ":retry_count)"
                ),
                {"status": status, "error_code": error_code, "retry_count": retry_count},
            )

    command.upgrade(config, "head")
    with engine.begin() as connection:
        assert connection.execute(
            text("SELECT entity_id, status FROM processing_jobs WHERE id = 'job-a'")
        ).one() == ("audio-1", "RUNNING")
        assert connection.execute(
            text(
                "SELECT id, original_entity_id, status, error_code, retry_count, "
                "result_transcript_revision_id, archived_reason "
                "FROM legacy_processing_job_archive ORDER BY id"
            )
        ).all() == [
            ("job-b", "audio-1", "COMPLETED", "legacy-complete", 2, None, "duplicate_legacy_job"),
            ("job-c", "audio-1", "FAILED", "legacy-failure", 3, None, "duplicate_legacy_job"),
        ]
        connection.execute(
            text(
                "UPDATE legacy_processing_job_archive SET result_transcript_revision_id = "
                "'historical-result-only' WHERE id = 'job-b'"
            )
        )
        assert (
            connection.execute(
                text(
                    "SELECT result_transcript_revision_id FROM legacy_processing_job_archive WHERE id = 'job-b'"
                )
            ).scalar_one()
            == "historical-result-only"
        )
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM processing_jobs WHERE entity_id LIKE '%-legacy-%'")
            ).scalar_one()
            == 0
        )

    engine.dispose()
    command.downgrade(config, "20260716_0002")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT entity_id, status FROM processing_jobs WHERE id = 'job-b'")
        ).one() == ("audio-1", "COMPLETED")
        assert connection.execute(
            text("SELECT entity_id, status FROM processing_jobs WHERE id = 'job-c'")
        ).one() == ("audio-1", "FAILED")
        assert "legacy_processing_job_archive" not in inspect(connection).get_table_names()

    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT original_entity_id FROM legacy_processing_job_archive WHERE id = 'job-b'"
                )
            ).scalar_one()
            == "audio-1"
        )
        # The migration documents that archive-only historical result text has
        # no Phase 2 storage location and is therefore NULL after re-upgrade.
        assert (
            connection.execute(
                text(
                    "SELECT result_transcript_revision_id FROM legacy_processing_job_archive "
                    "WHERE id = 'job-b'"
                )
            ).scalar_one()
            is None
        )
        migration_context = MigrationContext.configure(connection)
        assert compare_metadata(migration_context, Base.metadata) == []
    engine.dispose()


@pytest.mark.parametrize(
    ("table_name", "statement"),
    [
        (
            "recording_deletion_tombstones",
            "INSERT INTO recording_deletion_tombstones "
            "(id, created_at, updated_at, recording_id, context_version_id, cleanup_type, "
            "media_relative_path, status) VALUES "
            "('pending-delete', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'recording-1', "
            "'context-1', 'RECORDING_DELETION', 'lesson-1/pending.wav', 'DELETE_PENDING')",
        ),
        (
            "media_upload_intents",
            "INSERT INTO media_upload_intents "
            "(id, created_at, updated_at, lesson_id, temporary_relative_path, "
            "final_relative_path, sha256, byte_size, status) VALUES "
            "('pending-upload', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
            "'lesson-1/pending.uploading', 'lesson-1/pending.wav', printf('%064d', 1), 1, 'PREPARED')",
        ),
        (
            "media_upload_intents",
            "INSERT INTO media_upload_intents "
            "(id, created_at, updated_at, lesson_id, temporary_relative_path, "
            "final_relative_path, sha256, byte_size, status) VALUES "
            "('placed-upload', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
            "'lesson-1/placed.uploading', 'lesson-1/placed.wav', printf('%064d', 2), 2, 'MEDIA_PLACED')",
        ),
        (
            "media_upload_intents",
            "INSERT INTO media_upload_intents "
            "(id, created_at, updated_at, lesson_id, temporary_relative_path, "
            "final_relative_path, sha256, byte_size, status) VALUES "
            "('committed-upload', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
            "'lesson-1/committed.uploading', 'lesson-1/committed.wav', printf('%064d', 3), 3, 'RECORDING_COMMITTED')",
        ),
        (
            "media_upload_intents",
            "INSERT INTO media_upload_intents "
            "(id, created_at, updated_at, lesson_id, temporary_relative_path, "
            "final_relative_path, sha256, byte_size, status, conflict_code) VALUES "
            "('conflict-upload', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
            "'lesson-1/conflict.uploading', 'lesson-1/conflict.wav', printf('%064d', 4), 4, "
            "'RECOVERY_CONFLICT', 'media_identity_mismatch')",
        ),
        (
            "recording_deletion_tombstones",
            "INSERT INTO recording_deletion_tombstones "
            "(id, created_at, updated_at, recording_id, context_version_id, cleanup_type, "
            "media_relative_path, status, cleanup_owner_token) VALUES "
            "('claimed-delete', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'recording-2', "
            "'context-1', 'RECORDING_DELETION', 'lesson-1/claimed.wav', 'CLEANUP_CLAIMED', 'owner')",
        ),
        (
            "recording_deletion_tombstones",
            "INSERT INTO recording_deletion_tombstones "
            "(id, created_at, updated_at, recording_id, context_version_id, cleanup_type, "
            "media_relative_path, status, conflict_code) VALUES "
            "('conflict-delete', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'recording-3', "
            "'context-1', 'RECORDING_DELETION', 'lesson-1/conflict.wav', 'RECOVERY_CONFLICT', "
            "'media_identity_mismatch')",
        ),
    ],
)
def test_phase_3b_downgrade_blocks_pending_cleanup_without_schema_mutation(
    tmp_path, table_name: str, statement: str
) -> None:
    database_path = tmp_path / f"pending-{table_name}.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        _insert_phase_2_parent_graph(connection)
        connection.execute(text(statement))
    engine.dispose()

    with pytest.raises(RuntimeError, match="cleanup is pending"):
        command.downgrade(config, "20260716_0002")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert table_name in inspect(connection).get_table_names()
        assert connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() == 1
    engine.dispose()


def test_phase_3b_downgrade_allows_completed_deletion_receipts(tmp_path) -> None:
    database_path = tmp_path / "completed-receipt.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recording_deletion_tombstones "
                "(id, created_at, updated_at, recording_id, context_version_id, cleanup_type, "
                "media_relative_path, status, completed_at) VALUES "
                "('completed-delete', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'recording-1', "
                "'context-1', 'RECORDING_DELETION', NULL, 'COMPLETED', CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    # A completed receipt carries no pending media path; it is intentionally
    # removable with the Phase 3B cleanup table during a downgrade.
    command.downgrade(config, "20260716_0002")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert "recording_deletion_tombstones" not in inspect(connection).get_table_names()
    engine.dispose()


def test_concept_glossary_term_link_schema_enforces_context_and_cascades(tmp_path) -> None:
    database_path = tmp_path / "concept-glossary-links.db"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        _insert_phase_2_parent_graph(connection)
        connection.execute(
            text(
                "INSERT INTO concepts "
                "(id, created_at, updated_at, lesson_id, context_version_id, concept_key, title, definition, sequence) "
                "VALUES ('concept-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                "'context-1', 'plant-inputs', 'Plant inputs', 'Plants need inputs.', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO glossary_terms "
                "(id, created_at, updated_at, lesson_id, canonical_term, definition, sequence) "
                "VALUES ('glossary-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-1', "
                "'Water', 'Water reaches the leaf.', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO concept_glossary_term_links "
                "(id, created_at, updated_at, context_version_id, concept_id, glossary_term_id, sequence) "
                "VALUES ('link-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-1', "
                "'concept-1', 'glossary-1', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO course_context_versions "
                "(id, created_at, updated_at, course_id, version_number, teacher_review_status) "
                "VALUES ('context-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'course-1', 2, 'DRAFT')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO chapters (id, created_at, updated_at, context_version_id, title, sequence) "
                "VALUES ('chapter-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-2', 'Plants', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO lessons (id, created_at, updated_at, chapter_id, title, sequence, primary_language) "
                "VALUES ('lesson-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'chapter-2', 'Photosynthesis', 1, 'ml')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO concepts "
                "(id, created_at, updated_at, lesson_id, context_version_id, concept_key, title, definition, sequence) "
                "VALUES ('concept-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-2', "
                "'context-2', 'oxygen', 'Oxygen', 'Oxygen is released.', 1)"
            )
        )

    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        for statement in (
            "INSERT INTO concept_glossary_term_links "
            "(id, created_at, updated_at, context_version_id, concept_id, glossary_term_id, sequence) "
            "VALUES ('link-duplicate', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-1', "
            "'concept-1', 'glossary-1', 2)",
            "INSERT INTO concept_glossary_term_links "
            "(id, created_at, updated_at, context_version_id, concept_id, glossary_term_id, sequence) "
            "VALUES ('link-zero', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-1', "
            "'concept-1', 'glossary-1', 0)",
            "INSERT INTO concept_glossary_term_links "
            "(id, created_at, updated_at, context_version_id, concept_id, glossary_term_id, sequence) "
            "VALUES ('link-cross-context', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-1', "
            "'concept-2', 'glossary-1', 1)",
        ):
            with pytest.raises(IntegrityError):
                connection.execute(text(statement))
            connection.rollback()

        connection.execute(text("DELETE FROM lessons WHERE id = 'lesson-1'"))
        connection.commit()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM concept_glossary_term_links WHERE id = 'link-1'")
            ).scalar_one()
            == 0
        )
        connection.execute(
            text(
                "INSERT INTO glossary_terms "
                "(id, created_at, updated_at, lesson_id, canonical_term, definition, sequence) "
                "VALUES ('glossary-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'lesson-2', "
                "'Oxygen', 'Oxygen is released.', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO concept_glossary_term_links "
                "(id, created_at, updated_at, context_version_id, concept_id, glossary_term_id, sequence) "
                "VALUES ('link-2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'context-2', "
                "'concept-2', 'glossary-2', 1)"
            )
        )
        connection.commit()
        connection.execute(text("DELETE FROM course_context_versions WHERE id = 'context-2'"))
        connection.commit()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM concept_glossary_term_links WHERE id = 'link-2'")
            ).scalar_one()
            == 0
        )

    inspector = inspect(engine)
    assert ConceptGlossaryTermLink.__tablename__ in inspector.get_table_names()
    assert "ix_concept_glossary_term_link_context_glossary" in {
        index["name"] for index in inspector.get_indexes(ConceptGlossaryTermLink.__tablename__)
    }
    assert {"uq_concept_glossary_term_link_pair", "uq_concept_glossary_term_link_sequence"} <= {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(ConceptGlossaryTermLink.__tablename__)
    }
    engine.dispose()
