from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.contracts.enums import (
    ArtifactStatus,
    ConceptRelationshipType,
    ContentLanguage,
    MaterialType,
    QualityStatus,
    QuestionSourceType,
    SourceStatus,
    TeacherReviewStatus,
    UncertaintyStatus,
)
from app.contracts.teacher_review import DomainError
from app.models.foundation import (
    ApprovedMaterial,
    ASRMisrecognition,
    Chapter,
    Concept,
    ConceptGlossaryTermLink,
    ConceptRelationship,
    Course,
    CourseContextVersion,
    GeneratedArtifact,
    GlossaryTerm,
    LearningObjective,
    Lesson,
    QuestionItem,
    TermAlias,
)
from app.repositories.curriculum import CurriculumRepository
from app.services.context_completeness import (
    ContextCompletenessService,
    LockedPhotosynthesisCompletenessPolicy,
)
from app.services.context_versioning import ContextVersioningService
from app.services.student_curriculum import StudentCurriculumService
from app.services.teacher_review import TeacherReviewService, assert_context_mutable


def migration_config(database_path: Path) -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@pytest.fixture()
def session(tmp_path):
    database_path = tmp_path / "phase-2b.db"
    command.upgrade(migration_config(database_path), "head")
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    database_session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield database_session
    finally:
        database_session.close()
        engine.dispose()


def services(session: Session):
    repository = CurriculumRepository(session)
    completeness = ContextCompletenessService(repository)
    review = TeacherReviewService(
        session,
        repository,
        completeness,
        now=lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return repository, completeness, review


def complete_context(session: Session, version: int = 1, course: Course | None = None):
    course = course or Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
    context = CourseContextVersion(course=course, version_number=version)
    chapter = Chapter(context_version=context, title="Plants", sequence=1)
    lesson = Lesson(chapter=chapter, title="Plant food", sequence=1)
    session.add_all([course, context, chapter, lesson])
    session.flush()
    session.add(LearningObjective(lesson=lesson, objective_text="Explain plant food.", sequence=1))
    session.add(
        ApprovedMaterial(
            lesson=lesson,
            title="Teacher source",
            material_type=MaterialType.TEACHER_NOTE,
            source_label="Teacher",
            content="Plants make food.",
            language=ContentLanguage.BILINGUAL,
            sequence=1,
            teacher_review_status=TeacherReviewStatus.APPROVED,
        )
    )
    labels = {"photosynthesis": "പ്രകാശസംശ്ലേഷണം", "chlorophyll": "ക്ലോറോഫിൽ"}
    terms = (
        "Photosynthesis",
        "Chlorophyll",
        "Chloroplast",
        "Stomata",
        "Carbon dioxide",
        "Water",
        "Sunlight",
        "Glucose",
        "Oxygen",
        "Leaf",
    )
    glossary_terms = []
    for sequence, term in enumerate(terms, 1):
        glossary = GlossaryTerm(
            lesson=lesson,
            canonical_term=term,
            malayalam_support_label=labels.get(term.casefold()),
            definition=f"Definition of {term}.",
            sequence=sequence,
        )
        session.add(glossary)
        glossary_terms.append(glossary)
    concepts = []
    for sequence, key in enumerate(
        (
            "plant-inputs",
            "inputs-reach-leaf",
            "sunlight-chlorophyll",
            "glucose-production",
            "oxygen-release",
        ),
        1,
    ):
        concept = Concept(
            lesson=lesson,
            concept_key=key,
            title=key,
            definition=f"Definition {key}.",
            sequence=sequence,
        )
        session.add(concept)
        concepts.append(concept)
    session.flush()
    session.add(
        TermAlias(
            glossary_term_id=glossary_terms[0].id,
            alias="food",
            normalized_alias="food",
        )
    )
    session.add(
        ASRMisrecognition(
            glossary_term_id=glossary_terms[0].id,
            detected_text="fud",
            normalized_text="fud",
        )
    )
    session.add(
        ConceptRelationship(
            lesson=lesson,
            source_concept_id=concepts[0].id,
            target_concept_id=concepts[1].id,
            relationship_type=ConceptRelationshipType.PREREQUISITE_OF,
            sequence=1,
        )
    )
    session.add(
        QuestionItem(
            lesson=lesson,
            related_concept_id=concepts[0].id,
            source_type=QuestionSourceType.TEACHER_QUESTION,
            source_label="Teacher",
            question_text="What do plants need?",
            sequence=1,
            teacher_review_status=TeacherReviewStatus.APPROVED,
        )
    )
    session.add_all(
        [
            ConceptGlossaryTermLink(
                context_version_id=context.id,
                concept_id=concept.id,
                glossary_term_id=glossary_terms[index].id,
                sequence=1,
            )
            for index, concept in enumerate(concepts)
        ]
    )
    session.commit()
    return course, context, lesson


def test_completeness_is_structured_deterministic_and_case_insensitive(session: Session) -> None:
    course = Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
    empty = CourseContextVersion(course=course, version_number=1)
    session.add_all([course, empty])
    session.commit()
    _, completeness, _ = services(session)
    first = completeness.evaluate(empty.id)
    second = completeness.evaluate(empty.id)
    assert [issue.code for issue in first.issues] == [issue.code for issue in second.issues]
    assert "missing_chapter" in {issue.code for issue in first.issues}
    _, complete, _ = complete_context(session, version=2, course=course)
    assert completeness.evaluate(complete.id).is_complete


def test_review_transitions_are_atomic_and_approved_is_immutable(session: Session) -> None:
    _, context, _ = complete_context(session)
    repository, _, review = services(session)
    assert (
        review.submit_for_review(context.id).teacher_review_status
        is TeacherReviewStatus.NEEDS_REVIEW
    )
    assert (
        review.return_to_draft(
            context.id, reviewer_note="Please check wording."
        ).teacher_review_status
        is TeacherReviewStatus.DRAFT
    )
    review.submit_for_review(context.id)
    assert review.approve(context.id).teacher_review_status is TeacherReviewStatus.APPROVED
    events = repository.list_review_events(context.id)
    assert [event.created_at for event in events] == sorted(event.created_at for event in events)
    assert {event.event_type.value for event in events} == {
        "submitted_for_review",
        "returned_to_draft",
        "approved",
    }
    with pytest.raises(DomainError, match="approved_context_immutable"):
        assert_context_mutable(context)


def test_incomplete_review_operation_has_no_event(session: Session) -> None:
    course = Course(title="Science", subject="Science", class_level=7, grade_band="5-7")
    context = CourseContextVersion(course=course, version_number=1)
    session.add_all([course, context])
    session.commit()
    repository, _, review = services(session)
    with pytest.raises(DomainError, match="context_incomplete"):
        review.submit_for_review(context.id)
    assert repository.list_review_events(context.id) == []
    assert context.teacher_review_status is TeacherReviewStatus.DRAFT


def test_approved_context_copy_remaps_all_owned_references(session: Session) -> None:
    _, source, _ = complete_context(session)
    _, _, review = services(session)
    review.submit_for_review(source.id)
    review.approve(source.id)
    repository = CurriculumRepository(session)
    copied = ContextVersioningService(session, repository).create_draft_from_approved(source.id)
    source_graph = repository.get_context_with_graph(source.id)
    copied_graph = repository.get_context_with_graph(copied.id)
    assert copied.version_number == 2
    assert copied.teacher_review_status is TeacherReviewStatus.DRAFT
    assert copied.copied_from_context_version_id == source.id
    assert {
        lesson.id for chapter in source_graph.chapters for lesson in chapter.lessons
    }.isdisjoint({lesson.id for chapter in copied_graph.chapters for lesson in chapter.lessons})
    copied_relationship = copied_graph.chapters[0].lessons[0].concept_relationships[0]
    copied_concepts = {concept.id for concept in copied_graph.chapters[0].lessons[0].concepts}
    assert {
        copied_relationship.source_concept_id,
        copied_relationship.target_concept_id,
    } <= copied_concepts
    source_links = source_graph.concept_glossary_term_links
    copied_links = copied_graph.concept_glossary_term_links
    copied_glossary_ids = {
        glossary.id
        for lesson in copied_graph.chapters[0].lessons
        for glossary in lesson.glossary_terms
    }
    assert len(copied_links) == len(source_links)
    assert {link.context_version_id for link in copied_links} == {copied.id}
    assert {link.concept_id for link in copied_links} <= copied_concepts
    assert {link.glossary_term_id for link in copied_links} <= copied_glossary_ids
    assert {link.concept_id for link in copied_links}.isdisjoint(
        {link.concept_id for link in source_links}
    )
    assert {link.glossary_term_id for link in copied_links}.isdisjoint(
        {link.glossary_term_id for link in source_links}
    )
    assert [event.event_type.value for event in repository.list_review_events(copied.id)] == [
        "copied_to_new_draft"
    ]


def test_approval_stales_only_older_approved_artifacts_and_student_sees_highest_approved(
    session: Session,
) -> None:
    course, old_context, old_lesson = complete_context(session)
    _, _, review = services(session)
    review.submit_for_review(old_context.id)
    review.approve(old_context.id)
    old_artifact = GeneratedArtifact(
        lesson_id=old_lesson.id,
        course_context_version_id=old_context.id,
        artifact_type="notes",
        provider_name="test",
        source_status=SourceStatus.DEMO,
        quality_status=QualityStatus.VERIFIED,
        uncertainty_status=UncertaintyStatus.CONFIRMED,
    )
    session.add(old_artifact)
    session.commit()
    _, new_context, _ = complete_context(session, version=2, course=course)
    review.submit_for_review(new_context.id)
    review.approve(new_context.id)
    assert old_artifact.generation_status is ArtifactStatus.STALE
    assert old_artifact.stale_reason == "course_context_superseded"
    student = StudentCurriculumService(CurriculumRepository(session))
    assert student.get_current_context(course.id).id == new_context.id
    assert {lesson.title for lesson in student.list_current_lessons(course.id)} == {"Plant food"}


def test_duplicate_glossary_terms_accept_a_label_from_any_matching_lesson(session: Session) -> None:
    _, context, _ = complete_context(session)
    photosynthesis = session.scalar(
        select(GlossaryTerm).where(GlossaryTerm.canonical_term == "Photosynthesis")
    )
    photosynthesis.malayalam_support_label = "incorrect"
    chapter = Chapter(context_version_id=context.id, title="Second chapter", sequence=2)
    lesson = Lesson(chapter=chapter, title="Second lesson", sequence=1)
    session.add_all([chapter, lesson])
    session.flush()
    session.add(
        GlossaryTerm(
            lesson=lesson,
            canonical_term="PHOTOSYNTHESIS",
            malayalam_support_label=LockedPhotosynthesisCompletenessPolicy().required_malayalam_labels[
                0
            ][1],
            definition="A second valid label.",
            sequence=1,
        )
    )
    session.commit()
    session.expire_all()

    _, completeness, _ = services(session)
    assert not any(
        issue.code == "missing_required_malayalam_label" and issue.field == "photosynthesis"
        for issue in completeness.evaluate(context.id).issues
    )


def test_approval_query_failure_rolls_back_status_timestamp_and_event(
    session: Session, monkeypatch
) -> None:
    _, context, _ = complete_context(session)
    repository, _, review = services(session)
    review.submit_for_review(context.id)

    def stale_lookup_failure(*_args, **_kwargs):
        raise SQLAlchemyError("injected stale lookup failure")

    monkeypatch.setattr(
        repository, "find_non_stale_artifacts_from_older_approved_contexts", stale_lookup_failure
    )
    with pytest.raises(SQLAlchemyError, match="injected"):
        review.approve(context.id)
    session.expire_all()
    restored = session.get(CourseContextVersion, context.id)
    assert restored.teacher_review_status is TeacherReviewStatus.NEEDS_REVIEW
    assert restored.approved_at is None
    assert [event.event_type.value for event in repository.list_review_events(context.id)] == [
        "submitted_for_review"
    ]


def test_version_allocation_conflict_is_classified_and_rolls_back(
    session: Session, monkeypatch
) -> None:
    _, source, _ = complete_context(session)
    _, _, review = services(session)
    review.submit_for_review(source.id)
    review.approve(source.id)
    repository = CurriculumRepository(session)

    def allocation_conflict() -> None:
        raise IntegrityError("INSERT", {}, Exception("unique context version"))

    monkeypatch.setattr(repository, "flush", allocation_conflict)
    with pytest.raises(DomainError, match="version_conflict"):
        ContextVersioningService(session, repository).create_draft_from_approved(source.id)
    assert repository.list_context_versions(source.course_id) == [source]
