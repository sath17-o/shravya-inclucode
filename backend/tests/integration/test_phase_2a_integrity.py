from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.contracts.enums import (
    ConceptRelationshipType,
    ContentLanguage,
    ContextReviewEventType,
    MaterialType,
    QuestionSourceType,
    TeacherReviewStatus,
)
from app.models import ContextReviewEvent
from app.models.foundation import (
    ApprovedMaterial,
    ASRMisrecognition,
    Chapter,
    Concept,
    ConceptRelationship,
    Course,
    CourseContextVersion,
    GlossaryTerm,
    LearningObjective,
    Lesson,
    QuestionItem,
    TermAlias,
)


def migration_config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@dataclass
class CurriculumGraph:
    course: Course
    context: CourseContextVersion
    chapter: Chapter
    lesson: Lesson
    objective: LearningObjective
    material: ApprovedMaterial
    glossary_term: GlossaryTerm
    alias: TermAlias
    misrecognition: ASRMisrecognition
    concept_a: Concept
    concept_b: Concept
    relationship: ConceptRelationship
    question: QuestionItem
    review_event: ContextReviewEvent


def create_curriculum_graph(session: Session) -> CurriculumGraph:
    """Create one complete, valid curriculum graph without product fixtures."""
    course = Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
    context = CourseContextVersion(
        course=course,
        version_number=1,
        teacher_review_status=TeacherReviewStatus.DRAFT,
    )
    chapter = Chapter(context_version=context, title="Plants", sequence=1)
    lesson = Lesson(
        chapter=chapter,
        title="How plants make food",
        sequence=1,
        primary_language="bilingual",
        description="Teacher-prepared curriculum context.",
    )
    session.add_all([course, context, chapter, lesson])
    session.flush()

    objective = LearningObjective(
        lesson=lesson,
        objective_text="Identify the inputs a plant uses.",
        malayalam_text="സസ്യത്തിന് ആവശ്യമായ ഘടകങ്ങൾ തിരിച്ചറിയുക.",
        sequence=1,
    )
    material = ApprovedMaterial(
        lesson=lesson,
        title="Teacher-approved source text",
        material_type=MaterialType.TEXTBOOK_EXCERPT,
        source_label="Teacher source",
        content="Plants use light, water, and air to make food.",
        reference="r" * 500,
        language=ContentLanguage.BILINGUAL,
        sequence=1,
        teacher_review_status=TeacherReviewStatus.APPROVED,
    )
    glossary_term = GlossaryTerm(
        lesson=lesson,
        canonical_term="Plant food",
        malayalam_support_label="സസ്യാഹാരം",
        definition="Food produced by a plant.",
        malayalam_explanation="സസ്യം ഉണ്ടാക്കുന്ന ആഹാരം.",
        sequence=1,
    )
    concept_a = Concept(
        lesson=lesson,
        concept_key="plant-inputs",
        title="Plant inputs",
        malayalam_title="സസ്യത്തിന്റെ ഘടകങ്ങൾ",
        definition="Plants need inputs before they can make food.",
        malayalam_definition="ആഹാരം ഉണ്ടാക്കാൻ സസ്യത്തിന് ഘടകങ്ങൾ വേണം.",
        sequence=1,
    )
    concept_b = Concept(
        lesson=lesson,
        concept_key="plant-food",
        title="Plant food",
        definition="Plants make food from their inputs.",
        sequence=2,
    )
    session.add_all([objective, material, glossary_term, concept_a, concept_b])
    session.flush()

    alias = TermAlias(
        glossary_term=glossary_term,
        alias="plant-made food",
        normalized_alias="plant made food",
    )
    misrecognition = ASRMisrecognition(
        glossary_term=glossary_term,
        detected_text="plant foot",
        normalized_text="plant food",
        source_note="Teacher-observed speech recognition variant.",
    )
    relationship = ConceptRelationship(
        lesson=lesson,
        source_concept_id=concept_a.id,
        target_concept_id=concept_b.id,
        relationship_type=ConceptRelationshipType.PREREQUISITE_OF,
        teacher_note="Teach inputs before outcomes.",
        sequence=1,
    )
    question = QuestionItem(
        lesson=lesson,
        related_concept_id=concept_b.id,
        source_type=QuestionSourceType.AI_GENERATED_PRACTICE,
        source_label="Teacher practice prompt",
        question_text="What does a plant need to make food?",
        malayalam_question_text="സസ്യത്തിന് ആഹാരം ഉണ്ടാക്കാൻ എന്ത് വേണം?",
        sequence=1,
        year=2026,
        marks=2,
        teacher_review_status=TeacherReviewStatus.NEEDS_REVIEW,
    )
    review_event = ContextReviewEvent(
        context_version_id=context.id,
        event_type=ContextReviewEventType.SUBMITTED_FOR_REVIEW,
        actor_role="teacher",
        note="Ready for review.",
    )
    session.add_all([alias, misrecognition, relationship, question, review_event])
    session.commit()
    return CurriculumGraph(
        course=course,
        context=context,
        chapter=chapter,
        lesson=lesson,
        objective=objective,
        material=material,
        glossary_term=glossary_term,
        alias=alias,
        misrecognition=misrecognition,
        concept_a=concept_a,
        concept_b=concept_b,
        relationship=relationship,
        question=question,
        review_event=review_event,
    )


@pytest.fixture()
def migrated_session(tmp_path) -> Generator[Session, None, None]:
    database_path = tmp_path / "phase-2a-integrity.db"
    command.upgrade(migration_config(database_path), "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_representative_curriculum_graph_and_review_event_shape(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)

    assert graph.review_event.created_at is not None
    assert "updated_at" not in ContextReviewEvent.__table__.c
    assert ContextReviewEvent.__tablename__ == "context_review_events"
    assert graph.material.reference == "r" * 500


def test_phase_2a_enums_round_trip_as_values(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)
    expected_values = (
        ("approved_materials", "material_type", graph.material.id, MaterialType.TEXTBOOK_EXCERPT),
        ("approved_materials", "language", graph.material.id, ContentLanguage.BILINGUAL),
        (
            "approved_materials",
            "teacher_review_status",
            graph.material.id,
            TeacherReviewStatus.APPROVED,
        ),
        (
            "concept_relationships",
            "relationship_type",
            graph.relationship.id,
            ConceptRelationshipType.PREREQUISITE_OF,
        ),
        (
            "question_items",
            "source_type",
            graph.question.id,
            QuestionSourceType.AI_GENERATED_PRACTICE,
        ),
        (
            "question_items",
            "teacher_review_status",
            graph.question.id,
            TeacherReviewStatus.NEEDS_REVIEW,
        ),
        (
            "context_review_events",
            "event_type",
            graph.review_event.id,
            ContextReviewEventType.SUBMITTED_FOR_REVIEW,
        ),
    )
    for table_name, column_name, row_id, enum_member in expected_values:
        stored_value = migrated_session.execute(
            text(f"SELECT {column_name} FROM {table_name} WHERE id = :row_id"),
            {"row_id": row_id},
        ).scalar_one()
        assert stored_value == enum_member.value

    migrated_session.expire_all()
    assert (
        migrated_session.get(ApprovedMaterial, graph.material.id).material_type
        is MaterialType.TEXTBOOK_EXCERPT
    )
    assert (
        migrated_session.get(ApprovedMaterial, graph.material.id).language
        is ContentLanguage.BILINGUAL
    )
    assert (
        migrated_session.get(ApprovedMaterial, graph.material.id).teacher_review_status
        is TeacherReviewStatus.APPROVED
    )
    assert (
        migrated_session.get(ConceptRelationship, graph.relationship.id).relationship_type
        is ConceptRelationshipType.PREREQUISITE_OF
    )
    assert (
        migrated_session.get(QuestionItem, graph.question.id).source_type
        is QuestionSourceType.AI_GENERATED_PRACTICE
    )
    assert (
        migrated_session.get(QuestionItem, graph.question.id).teacher_review_status
        is TeacherReviewStatus.NEEDS_REVIEW
    )
    assert (
        migrated_session.get(ContextReviewEvent, graph.review_event.id).event_type
        is ContextReviewEventType.SUBMITTED_FOR_REVIEW
    )


@pytest.mark.parametrize(
    ("table_name", "column_name", "record_name"),
    [
        ("approved_materials", "material_type", "material"),
        ("approved_materials", "language", "material"),
        ("approved_materials", "teacher_review_status", "material"),
        ("concept_relationships", "relationship_type", "relationship"),
        ("question_items", "source_type", "question"),
        ("question_items", "teacher_review_status", "question"),
        ("context_review_events", "event_type", "review_event"),
    ],
)
def test_phase_2a_enum_checks_reject_invalid_raw_values(
    migrated_session: Session,
    table_name: str,
    column_name: str,
    record_name: str,
) -> None:
    graph = create_curriculum_graph(migrated_session)
    record = getattr(graph, record_name)

    with pytest.raises(IntegrityError):
        migrated_session.execute(
            text(f"UPDATE {table_name} SET {column_name} = :value WHERE id = :row_id"),
            {"value": "invalid_raw_enum", "row_id": record.id},
        )
    migrated_session.rollback()


InvalidFactory = Callable[[CurriculumGraph], object]


@pytest.mark.parametrize(
    ("invalid_factory"),
    [
        lambda graph: LearningObjective(
            lesson_id=graph.lesson.id, objective_text="Invalid order", sequence=0
        ),
        lambda graph: LearningObjective(
            lesson_id=graph.lesson.id, objective_text="Duplicate order", sequence=1
        ),
        lambda graph: ApprovedMaterial(
            lesson_id=graph.lesson.id,
            title="Invalid material",
            material_type=MaterialType.TEACHER_NOTE,
            source_label="Teacher",
            content="Text",
            language=ContentLanguage.EN,
            sequence=0,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        ),
        lambda graph: ApprovedMaterial(
            lesson_id=graph.lesson.id,
            title="Duplicate material order",
            material_type=MaterialType.TEACHER_NOTE,
            source_label="Teacher",
            content="Text",
            language=ContentLanguage.EN,
            sequence=1,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        ),
        lambda graph: GlossaryTerm(
            lesson_id=graph.lesson.id,
            canonical_term="No definition",
            definition=None,
            sequence=2,
        ),
        lambda graph: GlossaryTerm(
            lesson_id=graph.lesson.id,
            canonical_term="Invalid glossary order",
            definition="Definition",
            sequence=0,
        ),
        lambda graph: GlossaryTerm(
            lesson_id=graph.lesson.id,
            canonical_term=graph.glossary_term.canonical_term,
            definition="Duplicate term",
            sequence=2,
        ),
        lambda graph: GlossaryTerm(
            lesson_id=graph.lesson.id,
            canonical_term="Duplicate glossary order",
            definition="Definition",
            sequence=1,
        ),
        lambda graph: TermAlias(
            glossary_term_id=graph.glossary_term.id,
            alias="Another alias",
            normalized_alias=graph.alias.normalized_alias,
        ),
        lambda graph: ASRMisrecognition(
            glossary_term_id=graph.glossary_term.id,
            detected_text="Another detected text",
            normalized_text=graph.misrecognition.normalized_text,
        ),
        lambda graph: Concept(
            lesson_id=graph.lesson.id,
            concept_key=None,
            title="No key",
            definition="Definition",
            sequence=3,
        ),
        lambda graph: Concept(
            lesson_id=graph.lesson.id,
            concept_key="no-definition",
            title="No definition",
            definition=None,
            sequence=3,
        ),
        lambda graph: Concept(
            lesson_id=graph.lesson.id,
            concept_key="invalid-order",
            title="Invalid order",
            definition="Definition",
            sequence=0,
        ),
        lambda graph: Concept(
            lesson_id=graph.lesson.id,
            concept_key=graph.concept_a.concept_key,
            title="Duplicate key",
            definition="Definition",
            sequence=3,
        ),
        lambda graph: Concept(
            lesson_id=graph.lesson.id,
            concept_key="duplicate-order",
            title="Duplicate order",
            definition="Definition",
            sequence=1,
        ),
        lambda graph: ConceptRelationship(
            lesson_id=graph.lesson.id,
            source_concept_id=graph.concept_a.id,
            target_concept_id=graph.concept_a.id,
            relationship_type=ConceptRelationshipType.RELATED_TO,
            sequence=2,
        ),
        lambda graph: ConceptRelationship(
            lesson_id=graph.lesson.id,
            source_concept_id=graph.concept_a.id,
            target_concept_id=graph.concept_b.id,
            relationship_type=ConceptRelationshipType.PREREQUISITE_OF,
            sequence=2,
        ),
        lambda graph: ConceptRelationship(
            lesson_id=graph.lesson.id,
            source_concept_id=graph.concept_b.id,
            target_concept_id=graph.concept_a.id,
            relationship_type=ConceptRelationshipType.RELATED_TO,
            sequence=1,
        ),
        lambda graph: QuestionItem(
            lesson_id=graph.lesson.id,
            source_type=QuestionSourceType.TEACHER_QUESTION,
            source_label="Teacher",
            question_text="Invalid order?",
            sequence=0,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        ),
        lambda graph: QuestionItem(
            lesson_id=graph.lesson.id,
            source_type=QuestionSourceType.TEACHER_QUESTION,
            source_label="Teacher",
            question_text="Duplicate order?",
            sequence=1,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        ),
        lambda graph: QuestionItem(
            lesson_id=graph.lesson.id,
            source_type=QuestionSourceType.TEACHER_QUESTION,
            source_label="Teacher",
            question_text="Invalid year?",
            sequence=2,
            year=0,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        ),
        lambda graph: QuestionItem(
            lesson_id=graph.lesson.id,
            source_type=QuestionSourceType.TEACHER_QUESTION,
            source_label="Teacher",
            question_text="Invalid marks?",
            sequence=2,
            marks=0,
            teacher_review_status=TeacherReviewStatus.DRAFT,
        ),
        lambda graph: ContextReviewEvent(
            context_version_id=graph.context.id,
            event_type=ContextReviewEventType.APPROVED,
            actor_role=None,
        ),
    ],
    ids=[
        "objective-sequence-zero",
        "objective-duplicate-sequence",
        "material-sequence-zero",
        "material-duplicate-sequence",
        "glossary-missing-definition",
        "glossary-sequence-zero",
        "glossary-duplicate-term",
        "glossary-duplicate-sequence",
        "alias-duplicate-normalized-value",
        "misrecognition-duplicate-normalized-value",
        "concept-missing-key",
        "concept-missing-definition",
        "concept-sequence-zero",
        "concept-duplicate-key",
        "concept-duplicate-sequence",
        "relationship-self-reference",
        "relationship-duplicate-tuple",
        "relationship-duplicate-sequence",
        "question-sequence-zero",
        "question-duplicate-sequence",
        "question-invalid-year",
        "question-invalid-marks",
        "review-event-missing-actor-role",
    ],
)
def test_phase_2a_constraints_reject_invalid_orm_rows(
    migrated_session: Session, invalid_factory: InvalidFactory
) -> None:
    graph = create_curriculum_graph(migrated_session)
    migrated_session.add(invalid_factory(graph))

    with pytest.raises(IntegrityError):
        migrated_session.flush()
    migrated_session.rollback()


def test_concept_key_is_scoped_to_the_lesson(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)
    second_lesson = Lesson(
        chapter_id=graph.chapter.id,
        title="A different lesson",
        sequence=2,
        primary_language="en",
    )
    migrated_session.add(second_lesson)
    migrated_session.flush()
    migrated_session.add(
        Concept(
            lesson_id=second_lesson.id,
            concept_key=graph.concept_a.concept_key,
            title="Same scoped key",
            definition="A key can be reused in a different lesson.",
            sequence=1,
        )
    )
    migrated_session.commit()


def test_lesson_deletion_cascades_to_owned_curriculum_records(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)
    migrated_session.execute(
        text("DELETE FROM lessons WHERE id = :lesson_id"), {"lesson_id": graph.lesson.id}
    )
    migrated_session.commit()

    for table_name in (
        "learning_objectives",
        "approved_materials",
        "glossary_terms",
        "term_aliases",
        "asr_misrecognitions",
        "concepts",
        "concept_relationships",
        "question_items",
    ):
        assert (
            migrated_session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() == 0
        )


def test_glossary_deletion_cascades_only_to_its_children(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)
    unrelated_term = GlossaryTerm(
        lesson_id=graph.lesson.id,
        canonical_term="Unrelated term",
        definition="This term remains.",
        sequence=2,
    )
    migrated_session.add(unrelated_term)
    migrated_session.commit()

    migrated_session.execute(
        text("DELETE FROM glossary_terms WHERE id = :term_id"), {"term_id": graph.glossary_term.id}
    )
    migrated_session.commit()

    assert migrated_session.execute(text("SELECT COUNT(*) FROM term_aliases")).scalar_one() == 0
    assert (
        migrated_session.execute(text("SELECT COUNT(*) FROM asr_misrecognitions")).scalar_one() == 0
    )
    assert migrated_session.get(GlossaryTerm, unrelated_term.id) is not None


def test_concept_deletion_cascades_to_relationships_only(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)
    migrated_session.execute(
        text("DELETE FROM concepts WHERE id = :concept_id"), {"concept_id": graph.concept_a.id}
    )
    migrated_session.commit()

    assert (
        migrated_session.execute(text("SELECT COUNT(*) FROM concept_relationships")).scalar_one()
        == 0
    )
    assert migrated_session.get(Concept, graph.concept_b.id) is not None


def test_context_deletion_cascades_graph_and_review_events(migrated_session: Session) -> None:
    graph = create_curriculum_graph(migrated_session)
    migrated_session.execute(
        text("DELETE FROM course_context_versions WHERE id = :context_id"),
        {"context_id": graph.context.id},
    )
    migrated_session.commit()

    for table_name in ("chapters", "lessons", "learning_objectives", "context_review_events"):
        assert (
            migrated_session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() == 0
        )


def test_copied_context_is_retained_and_set_null_when_source_is_deleted(
    migrated_session: Session,
) -> None:
    graph = create_curriculum_graph(migrated_session)
    copied_context = CourseContextVersion(
        course_id=graph.course.id,
        version_number=2,
        teacher_review_status=TeacherReviewStatus.DRAFT,
        copied_from_context_version_id=graph.context.id,
    )
    migrated_session.add(copied_context)
    migrated_session.commit()

    migrated_session.execute(
        text("DELETE FROM course_context_versions WHERE id = :context_id"),
        {"context_id": graph.context.id},
    )
    migrated_session.commit()
    migrated_session.expire_all()

    retained_context = migrated_session.get(CourseContextVersion, copied_context.id)
    assert retained_context is not None
    assert retained_context.copied_from_context_version_id is None


def test_generated_artifact_context_lookup_index_exists(migrated_session: Session) -> None:
    create_curriculum_graph(migrated_session)
    index_columns = {
        index["name"]: index["column_names"]
        for index in inspect(migrated_session.get_bind()).get_indexes("generated_artifacts")
    }
    assert index_columns["ix_artifacts_context"] == ["course_context_version_id"]
