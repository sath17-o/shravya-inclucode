from dataclasses import fields, is_dataclass

import pytest

from app.api.v1.routes.curriculum import student_chapters
from app.contracts.enums import TeacherReviewStatus
from app.contracts.teacher_review import DomainError
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
from app.repositories.curriculum import CurriculumRepository
from app.services.student_curriculum import StudentCurriculumService
from tests.integration.factories import (
    approved_material,
    complete_photosynthesis_context,
    course,
    question_item,
)

MAPPED_MODELS = (
    Course,
    CourseContextVersion,
    Chapter,
    Lesson,
    LearningObjective,
    ApprovedMaterial,
    GlossaryTerm,
    TermAlias,
    ASRMisrecognition,
    Concept,
    ConceptRelationship,
    QuestionItem,
)


def assert_scalar_only(value: object) -> None:
    assert not isinstance(value, MAPPED_MODELS)
    assert not hasattr(value, "_sa_instance_state")
    if is_dataclass(value):
        for field in fields(value):
            assert_scalar_only(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:
            assert_scalar_only(item)


def test_student_service_projection_selects_only_approved_context_and_children(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        approved = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        draft = complete_photosynthesis_context(
            session,
            course_model=approved.course,
            version_number=2,
            status=TeacherReviewStatus.DRAFT,
        )
        session.add_all(
            [
                approved_material(
                    lesson=approved.lesson,
                    title="Draft material",
                    sequence=2,
                    teacher_review_status=TeacherReviewStatus.DRAFT,
                ),
                question_item(
                    lesson=approved.lesson,
                    question_text="Draft question",
                    sequence=2,
                    teacher_review_status=TeacherReviewStatus.DRAFT,
                ),
            ]
        )
        other = complete_photosynthesis_context(
            session,
            course_model=course(title="Other course"),
            status=TeacherReviewStatus.APPROVED,
        )
        session.commit()

        projection = StudentCurriculumService(
            CurriculumRepository(session)
        ).get_curriculum_projection(approved.course.id)
        approved_id = approved.context.id
        draft_id = draft.context.id
        other_id = other.context.id

    assert projection.context is not None and projection.context.id == approved_id
    assert projection.context.id != draft_id
    assert projection.context.id != other_id
    lesson = projection.chapters[0].lessons[0]
    assert [material.title for material in lesson.approved_materials] == ["Teacher-approved source"]
    assert [question.question_text for question in lesson.questions] == [
        "What do plants need for photosynthesis?"
    ]
    assert not hasattr(lesson, "lesson")
    assert not hasattr(lesson, "teacher_review_status")
    assert_scalar_only(projection)
    serialized = [
        chapter.model_dump(mode="json") for chapter in student_chapters(projection.chapters)
    ]
    assert (
        serialized[0]["lessons"][0]["approved_materials"][0]["title"] == "Teacher-approved source"
    )


def test_student_service_selects_highest_approved_and_handles_not_ready_and_unknown(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        first = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        second = complete_photosynthesis_context(
            session,
            course_model=first.course,
            version_number=2,
            status=TeacherReviewStatus.APPROVED,
        )
        no_approval = course(title="No approval")
        session.add(no_approval)
        session.commit()
        service = StudentCurriculumService(CurriculumRepository(session))
        selected = service.get_curriculum_projection(first.course.id)
        not_ready = service.get_curriculum_projection(no_approval.id)

        assert selected.context is not None and selected.context.id == second.context.id
        assert selected.context.id != first.context.id
        assert not_ready.context is None and not_ready.chapters == ()
        with pytest.raises(DomainError, match="course_not_found"):
            service.get_curriculum_projection("missing")
