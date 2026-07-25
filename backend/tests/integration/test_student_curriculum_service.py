from dataclasses import fields, is_dataclass
from datetime import datetime

import pytest

from app.api.v1.routes.curriculum import student_chapters
from app.contracts.enums import QualityStatus, SourceStatus, TeacherReviewStatus
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
    GlossaryTerm,
    LearningObjective,
    LectureAudio,
    Lesson,
    QuestionItem,
    TermAlias,
    TranscriptQualityAssessment,
    TranscriptRevision,
    TranscriptSegment,
)
from app.repositories.curriculum import CurriculumRepository
from app.services.student_curriculum import StudentCurriculumService
from app.services.transcript_provenance import (
    DETERMINISTIC_DEMO_PROVENANCE,
    DETERMINISTIC_DEMO_PROVIDER,
    PHASE_3B_PROVIDER_VERSION,
    TEACHER_ENTERED_PROVENANCE,
    TEACHER_ENTERED_PROVIDER,
)
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
                ConceptGlossaryTermLink(
                    context_version=approved.context,
                    concept=approved.concepts[1],
                    glossary_term=approved.glossary_terms[0],
                    sequence=2,
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
    assert lesson.glossary_terms[0].concept_ids == (
        lesson.concepts[0].id,
        lesson.concepts[1].id,
    )
    assert lesson.glossary_terms[1].canonical_term == "Chlorophyll"
    assert not hasattr(lesson.glossary_terms[1], "misrecognitions")
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


def test_student_revision_service_scopes_each_approved_context_and_current_marker(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        first = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        first.context.approved_at = datetime(2026, 7, 18)
        second = complete_photosynthesis_context(
            session,
            course_model=first.course,
            version_number=2,
            status=TeacherReviewStatus.APPROVED,
        )
        second.context.approved_at = datetime(2026, 7, 15)
        draft = complete_photosynthesis_context(
            session,
            course_model=first.course,
            version_number=3,
            status=TeacherReviewStatus.DRAFT,
        )
        session.commit()
        service = StudentCurriculumService(CurriculumRepository(session))
        library = service.get_revision_library(first.course.id)
        detail = service.get_approved_revision_projection(first.course.id, first.context.id)
        with pytest.raises(DomainError, match="student_revision_not_found"):
            service.get_approved_revision_projection(first.course.id, draft.context.id)
        first_id = first.context.id
        second_id = second.context.id

    assert [item.context_id for item in library.revisions] == [first_id, second_id]
    assert [item.is_current for item in library.revisions] == [False, True]
    assert detail.context is not None and detail.context.id == first.context.id
    assert detail.chapters[0].lessons[0].title == "Plants make food"
    assert_scalar_only(library)


def test_student_revision_library_uses_the_first_chapter_that_contains_a_lesson(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        complete = complete_photosynthesis_context(
            session, version_number=1, status=TeacherReviewStatus.APPROVED
        )
        complete.context.approved_at = datetime(2026, 7, 18)
        complete.chapter.sequence = 2
        session.add(
            Chapter(
                context_version=complete.context,
                title="Empty introduction",
                sequence=1,
            )
        )
        session.commit()
        service = StudentCurriculumService(CurriculumRepository(session))
        library = service.get_revision_library(complete.course.id)
        detail = service.get_approved_revision_projection(complete.course.id, complete.context.id)
        expected_chapter_title = complete.chapter.title
        expected_lesson_title = complete.lesson.title

    assert len(library.revisions) == 1
    assert library.revisions[0].chapter_title == expected_chapter_title
    assert library.revisions[0].lesson_title == expected_lesson_title
    assert detail.chapters[0].lessons == ()
    assert detail.chapters[1].lessons[0].title == expected_lesson_title


def _transcript_revision(
    lesson: Lesson,
    *,
    revision_number: int,
    status: TeacherReviewStatus,
    quality: QualityStatus,
    source_status: SourceStatus = SourceStatus.DEMO,
    recording: LectureAudio | None = None,
) -> TranscriptRevision:
    audio = recording or LectureAudio(
        lesson=lesson,
        storage_path=f"/safe/{revision_number}.wav",
        original_filename="recording.wav",
        mime_type="audio/wav",
        byte_size=10,
        sha256=(str(revision_number) * 64)[:64],
        duration_ms=1000,
        source_status=source_status,
    )
    deterministic = source_status is SourceStatus.DEMO
    revision = TranscriptRevision(
        lecture_audio=audio,
        revision_number=revision_number,
        source_status=source_status,
        provider_name=DETERMINISTIC_DEMO_PROVIDER if deterministic else TEACHER_ENTERED_PROVIDER,
        provider_version=PHASE_3B_PROVIDER_VERSION,
        provenance_label=(
            DETERMINISTIC_DEMO_PROVENANCE if deterministic else TEACHER_ENTERED_PROVENANCE
        ),
        teacher_review_status=status,
    )
    revision.segments = [
        TranscriptSegment(sequence=1, start_ms=0, end_ms=1000, text=f"Revision {revision_number}")
    ]
    revision.quality_assessments = [TranscriptQualityAssessment(quality_status=quality)]
    return revision


@pytest.mark.parametrize(
    ("latest_status", "latest_quality"),
    [
        (TeacherReviewStatus.DRAFT, QualityStatus.VERIFIED),
        (TeacherReviewStatus.APPROVED, QualityStatus.FAILED),
        (TeacherReviewStatus.NEEDS_REVIEW, QualityStatus.VERIFIED),
    ],
)
def test_student_projection_never_falls_back_from_latest_revision(
    migrated_api, latest_status, latest_quality
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.APPROVED)
        first = _transcript_revision(
            context.lesson,
            revision_number=1,
            status=TeacherReviewStatus.APPROVED,
            quality=QualityStatus.VERIFIED,
        )
        second = _transcript_revision(
            context.lesson,
            recording=first.lecture_audio,
            revision_number=2,
            status=latest_status,
            quality=latest_quality,
        )
        session.add_all([first, second])
        session.commit()
        projection = StudentCurriculumService(
            CurriculumRepository(session)
        ).get_curriculum_projection(context.course.id)
        assert projection.chapters[0].lessons[0].approved_transcript is None


def test_student_projection_uses_latest_verified_revision_per_recording(migrated_api) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.APPROVED)
        first = _transcript_revision(
            context.lesson,
            revision_number=1,
            status=TeacherReviewStatus.APPROVED,
            quality=QualityStatus.VERIFIED,
        )
        latest = _transcript_revision(
            context.lesson,
            recording=first.lecture_audio,
            revision_number=2,
            status=TeacherReviewStatus.APPROVED,
            quality=QualityStatus.VERIFIED,
        )
        session.add_all([first, latest])
        session.commit()
        projection = StudentCurriculumService(
            CurriculumRepository(session)
        ).get_curriculum_projection(context.course.id)
        transcript = projection.chapters[0].lessons[0].approved_transcript
        assert transcript is not None and transcript.id == latest.id


def test_multiple_recordings_never_select_an_older_revision_from_one_recording(
    migrated_api,
) -> None:
    with migrated_api.session_factory() as session:
        context = complete_photosynthesis_context(session, status=TeacherReviewStatus.APPROVED)
        first = _transcript_revision(
            context.lesson,
            revision_number=1,
            status=TeacherReviewStatus.APPROVED,
            quality=QualityStatus.VERIFIED,
        )
        newer_unapproved = _transcript_revision(
            context.lesson,
            recording=first.lecture_audio,
            revision_number=2,
            status=TeacherReviewStatus.DRAFT,
            quality=QualityStatus.VERIFIED,
        )
        second_audio = LectureAudio(
            lesson=context.lesson,
            storage_path="/safe/second.wav",
            original_filename="second.wav",
            mime_type="audio/wav",
            byte_size=10,
            sha256="b" * 64,
            duration_ms=1000,
            source_status=SourceStatus.DEMO,
        )
        second_recording = _transcript_revision(
            context.lesson,
            recording=second_audio,
            revision_number=1,
            status=TeacherReviewStatus.APPROVED,
            quality=QualityStatus.VERIFIED,
        )
        session.add_all([first, newer_unapproved, second_recording])
        session.commit()
        projection = StudentCurriculumService(
            CurriculumRepository(session)
        ).get_curriculum_projection(context.course.id)
        transcript = projection.chapters[0].lessons[0].approved_transcript
        assert transcript is not None and transcript.id == second_recording.id
